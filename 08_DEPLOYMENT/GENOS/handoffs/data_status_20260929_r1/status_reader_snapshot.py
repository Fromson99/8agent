from collections import Counter
import json
import os
from pathlib import Path
import re
import sqlite3

def safe(value):
    """Take one credential snapshot per report, not per nested field."""
    secrets = sorted({v for k, v in os.environ.items()
                      if v and k.upper() != 'STRUCTURE_RECIPE_MAX_TOKENS'
                      and any(s in k.upper() for s in ('KEY', 'TOKEN', 'PASSWORD', 'SECRET'))},
                     key=len, reverse=True)
    def redact(item):
        if isinstance(item, str):
            for secret in secrets:
                item = item.replace(secret, '[REDACTED]')
            return item
        if isinstance(item, dict):
            return {k: redact(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [redact(v) for v in item]
        return item
    return redact(value)

DATABASE = 'term-document-status.sqlite'

PHASES = ('structure', 'index')

STATES = ('PENDING', 'RUNNING', 'PASSED', 'FAILED', 'BLOCKED', 'NOT_REQUESTED', 'INTERRUPTED')

BAD_STATES = {'FAILED', 'BLOCKED', 'INTERRUPTED'}

LABELS = {'structure': '구조화', 'index': '용어·정의·참조·DRAFT',
          'PENDING': '대기', 'RUNNING': '진행 중 기록', 'PASSED': '완료', 'FAILED': '실패',
          'BLOCKED': '선행 단계 실패로 보류', 'NOT_REQUESTED': '이번 실행 대상 아님',
          'INTERRUPTED': '중단', 'NEW': '신규', 'REUSED': '재사용'}

NOTE = '현재 실행 차수의 마지막 저장 상태입니다. RUNNING은 프로세스가 지금 살아 있다는 뜻이 아닙니다.'

def _plain(path):
    path = Path(path).absolute()
    if '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('상태 경로의 심볼릭 링크/상위 이동은 허용되지 않습니다: ' + str(path))
    return path

def validate_run_id(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value):
        raise ValueError('run-id는 영문/숫자/._- 1~80자여야 합니다')
    return value

def read_report(directory):
    """One coherent read-only transaction. Old runs are explicitly unsupported."""
    directory = _plain(directory)
    path = _plain(directory / DATABASE)
    if not path.is_file():
        return {'recorded': False, 'run_id': directory.name,
                'note': '문서별 상태 원장이 없습니다. 이전 실행의 완료 여부를 추정하지 않습니다.',
                'documents': [], 'counts': {}}
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        if db.execute('SELECT version FROM status_meta').fetchone()[0] != 1:
            raise ValueError('지원되지 않는 문서 상태 원장 버전')
        attempt = db.execute('SELECT * FROM attempts ORDER BY rowid DESC LIMIT 1').fetchone()
        if attempt is None:
            return {'recorded': False, 'run_id': directory.name, 'note': '상태 원장에 실행 기록이 없습니다.',
                    'documents': [], 'counts': {}}
        docs = [json.loads(r[0]) for r in db.execute('SELECT data FROM documents WHERE attempt=? ORDER BY ordinal',
                                                   (attempt['id'],))]
        counts = {p: {s: sum(d['phases'][p]['state'] == s for d in docs if d['selection'] == 'SELECTED')
                      for s in STATES} for p in PHASES}
        for phase in PHASES:
            counts[phase].update({mode: sum(d['phases'][phase]['state'] == 'PASSED' and
                                           d['phases'][phase].get('mode') == mode for d in docs
                                           if d['selection'] == 'SELECTED') for mode in ('NEW', 'REUSED')})
        return safe({'recorded': True, 'run_id': directory.name, 'attempt': dict(attempt), 'note': NOTE,
                     'selection_counts': dict(Counter(d['selection'] for d in docs)),
                     'counts': counts, 'documents': docs})
    finally:
        db.close()

def _failed(row):
    return row['input_state'] == 'FAILED' or any(row['phases'][p]['state'] in BAD_STATES for p in PHASES)

def _cell(row, phase):
    entry = row['phases'][phase]
    value = LABELS[entry['state']]
    if entry.get('mode'):
        value += '/' + LABELS[entry['mode']]
    if 'elapsed_seconds' in entry:
        value += '/' + str(entry['elapsed_seconds']) + '초'
    return value

def _error(row):
    return ' | '.join(filter(None, [row.get('input_error', ''),
                      *(LABELS[p] + ': ' + row['phases'][p]['error'] for p in PHASES if row['phases'][p].get('error'))]))

def render_console(report, *, failures_only=False, limit=30):
    if limit < 0:
        raise ValueError('limit must be nonnegative')
    if not report['recorded']:
        return report['note'] + '\n'
    attempt = report['attempt']
    lines = [f"실행 {report['run_id']} | 단계 {attempt['stage']} | 종료 상태 {attempt['status']}",
             f"마지막 기록: {attempt['updated_at']} | 차수: {attempt['id']}", report['note']]
    c = report['selection_counts']
    lines.append(f"선택 문서 {c.get('SELECTED', 0)} | 입력 실패 제외 {c.get('INPUT_FAILED', 0)} | 의도적 제외 {c.get('EXCLUDED', 0)}")
    for phase in PHASES:
        v = report['counts'][phase]
        lines.append(f"{LABELS[phase]}: 완료 {v['PASSED']} (신규 {v['NEW']}/재사용 {v['REUSED']}) · 실패 {v['FAILED']} · "
                     f"보류 {v['BLOCKED']} · 중단 {v['INTERRUPTED']} · 대기 {v['PENDING']} · 진행 중 기록 {v['RUNNING']} · 대상 아님 {v['NOT_REQUESTED']}")
    lines.extend(['', '번호 | 문서(상대 경로) | 구조화 | 용어·정의·참조·DRAFT | 사유'])
    docs = [d for d in report['documents'] if not failures_only or _failed(d)]
    shown = docs if not limit else docs[:limit]
    for row in shown:
        lines.append(' | '.join([str(row['number']), row['relative'], *(_cell(row, p) for p in PHASES), _error(row)]))
        lines.append('  구조화 경로: ' + row['route'] + ' [' + row['route_record'] + ']' +
                     (' | 태그: ' + row['doc_type'] if row['doc_type'] else ''))
    lines.append(f'표시 {len(shown)}/{len(docs)}문서' + (' (--limit 0: 전체)' if len(shown) < len(docs) else ''))
    return '\n'.join(lines) + '\n'
