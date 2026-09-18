"""Persistent document-phase status; never reads corpus bodies or calls a model.

Each event is a small SQLite transaction (no per-event full report rendering).
Attempts are retained. The latest attempt is a recorded snapshot, not a process
liveness claim. Reports contain only an allowlist of operational metadata.
"""
from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import html
import io
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import uuid

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


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def _text(value, limit=4000):
    return ''.join(ch if ch.isprintable() else ' ' for ch in safe(str('' if value is None else value)))[:limit]


def _plain(path):
    path = Path(path).absolute()
    if '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('상태 경로의 심볼릭 링크/상위 이동은 허용되지 않습니다: ' + str(path))
    return path


def validate_run_id(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value):
        raise ValueError('run-id는 영문/숫자/._- 1~80자여야 합니다')
    return value


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _requested(stage):
    if stage not in {'raw', 'structure', 'index', 'all'}:
        raise ValueError('unknown stage: ' + str(stage))
    return PHASES if stage == 'all' else (() if stage == 'raw' else
           (('structure',) if stage == 'structure' else ('structure', stage)))


def _route(row):
    if row.get('source_parser'):
        return 'source:' + _text(row['source_parser'])
    if row.get('doc_type'):
        return 'registered:' + _text(row['doc_type'])
    if row.get('engine'):
        return 'engine:' + _text(row['engine'])
    return '형식 기본 파서 (명시 태그 없음)'


class Ledger:
    """Writer used under the pipeline run lock. Readers never open this class."""

    def __init__(self, directory):
        self.directory = _plain(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = _plain(self.directory / DATABASE)
        for suffix in ('-journal', '-wal', '-shm'):
            _plain(str(path) + suffix)
        existed = path.exists()
        if not existed:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        self.db = sqlite3.connect(path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.attempt = None
        try:
            if existed:
                version = self.db.execute('SELECT version FROM status_meta').fetchone()
                if not version or version[0] != 1:
                    raise ValueError('지원되지 않는 문서 상태 원장 버전')
            else:
                self.db.executescript('''
                    CREATE TABLE status_meta(version INTEGER NOT NULL);
                    INSERT INTO status_meta VALUES(1);
                    CREATE TABLE attempts(id TEXT PRIMARY KEY, stage TEXT, status TEXT,
                        started_at TEXT, updated_at TEXT, finished_at TEXT, error TEXT);
                    CREATE TABLE documents(attempt TEXT, id TEXT, ordinal INTEGER, data TEXT,
                        PRIMARY KEY(attempt,id));
                    CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
                        attempt TEXT, document_id TEXT, phase TEXT, state TEXT,
                        at TEXT, data TEXT);
                ''')
            # Rollback journal is intentional: no WAL/shared-memory on GENOS NFS.
            self.db.execute('PRAGMA journal_mode=DELETE')
            self.db.execute('PRAGMA synchronous=FULL')
        except BaseException:
            self.db.close()
            raise

    def start(self, rows, stage, *, excluded=(), ignored=()):
        requested = _requested(stage)
        now = _now()
        attempt = now.replace(':', '').replace('+', '-') + '-' + uuid.uuid4().hex[:8]
        records = []
        seen = set()
        for ordinal, row in enumerate(rows, 1):
            did = str(row['document_id'])
            if did in seen:
                raise ValueError('상태 원장의 중복 문서 ID: ' + did)
            seen.add(did)
            relative = _text(row['relative'])
            records.append({'document_id': did, 'number': ordinal, 'relative': relative,
                'title': _text(row.get('name') or Path(relative).stem),
                'folder': _text(row.get('folder') or Path(relative).parent),
                'extension': Path(relative).suffix.lower(),
                'source': _text(row.get('external_source') or row.get('source')),
                'selection': 'SELECTED', 'input_state': 'PASSED', 'input_error': '',
                'route': _text(row.get('route')) or _route(row), 'route_record': 'PLANNED',
                'doc_type': _text(row.get('doc_type')), 'engine': _text(row.get('engine')),
                'phases': {p: {'state': 'PENDING' if p in requested else 'NOT_REQUESTED',
                               'mode': '', 'updated_at': now} for p in PHASES}})
        for selection, items in (('INPUT_FAILED', excluded), ('EXCLUDED', ignored)):
            for item in items:
                if item.get('scope', 'document') != 'document':
                    continue
                name = _text(item.get('item') or item.get('path') or '(입력 경로 없음)')
                source = _text(item.get('source'))
                did = selection.lower() + ':' + hashlib.sha256((source + '\0' + name).encode()).hexdigest()[:20]
                if did in seen:
                    continue
                seen.add(did)
                reason = _text(item.get('error') or item.get('reason'))
                records.append({'document_id': did, 'number': len(records) + 1,
                    'relative': name, 'title': Path(name).name, 'folder': str(Path(name).parent),
                    'extension': Path(name).suffix.lower(), 'source': source,
                    'selection': selection, 'input_state': 'FAILED' if selection == 'INPUT_FAILED' else 'NOT_REQUESTED',
                    'input_error': reason, 'route': '입력 제외: 파서 미실행', 'route_record': 'NOT_RUN',
                    'doc_type': '', 'engine': '',
                    'phases': {p: {'state': 'BLOCKED' if p in requested and selection == 'INPUT_FAILED'
                                   else 'NOT_REQUESTED', 'mode': '', 'error': reason if selection == 'INPUT_FAILED' else '',
                                   'updated_at': now} for p in PHASES}})
        with self.db:
            # The caller holds the exclusive run lock; an unfinished previous
            # attempt can be recorded as interrupted without claiming when it died.
            unfinished = self.db.execute("SELECT id FROM attempts WHERE status='RUNNING'").fetchall()
            for old in unfinished:
                self._finish(old['id'], 'INTERRUPTED', '새 실행 시작 시 이전 실행 종료 기록 없음 확인', now)
            self.db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?)',
                            (attempt, stage, 'RUNNING', now, now, None, ''))
            self.db.executemany('INSERT INTO documents VALUES(?,?,?,?)',
                                ((attempt, r['document_id'], r['number'], _json(r)) for r in records))
            self.db.execute('INSERT INTO events(attempt,document_id,phase,state,at,data) VALUES(?,?,?,?,?,?)',
                            (attempt, None, None, 'STARTED', now, _json({'stage': stage, 'documents': len(records)})))
        self.attempt = attempt
        return self

    def update(self, document_id, phase, state, **metadata):
        if not self.attempt or phase not in PHASES or state not in STATES:
            raise ValueError('invalid document status update')
        allowed = {'mode', 'error', 'output_path', 'route', 'route_record', 'doc_type', 'engine',
                   'elapsed_seconds', 'detail'}
        if set(metadata) - allowed:
            raise ValueError('unsupported status metadata: ' + ','.join(sorted(set(metadata) - allowed)))
        if metadata.get('mode', '') not in {'', 'NEW', 'REUSED'}:
            raise ValueError('mode must be NEW or REUSED')
        if 'elapsed_seconds' in metadata:
            elapsed = metadata['elapsed_seconds']
            if type(elapsed) not in (float, int) or not math.isfinite(elapsed) or elapsed < 0:
                raise ValueError('invalid elapsed seconds')
        now = _now()
        with self.db:
            lifecycle = self.db.execute('SELECT status FROM attempts WHERE id=?', (self.attempt,)).fetchone()
            if lifecycle['status'] != 'RUNNING':
                raise ValueError('finished attempt cannot be updated')
            stored = self.db.execute('SELECT data FROM documents WHERE attempt=? AND id=?',
                                     (self.attempt, document_id)).fetchone()
            if stored is None:
                raise ValueError('unknown status document: ' + str(document_id))
            row = json.loads(stored['data'])
            entry = row['phases'][phase]
            if state == 'RUNNING':
                entry = {'started_at': now, 'mode': '', 'error': ''}
            entry.update(state=state, updated_at=now)
            for key, value in metadata.items():
                if key in {'route', 'route_record', 'doc_type', 'engine'}:
                    row[key] = _text(value)
                else:
                    entry[key] = round(value, 3) if key == 'elapsed_seconds' else _text(value)
            if state in {'PASSED', *BAD_STATES}:
                entry['finished_at'] = now
                if entry.get('started_at') and 'elapsed_seconds' not in metadata:
                    entry['elapsed_seconds'] = max(0, round((datetime.fromisoformat(now) -
                                                           datetime.fromisoformat(entry['started_at'])).total_seconds(), 3))
            row['phases'][phase] = entry
            self._save(self.attempt, row, phase, state, now)
            self.db.execute('UPDATE attempts SET updated_at=? WHERE id=?', (now, self.attempt))

    def _save(self, attempt, row, phase, state, now):
        self.db.execute('UPDATE documents SET data=? WHERE attempt=? AND id=?',
                        (_json(row), attempt, row['document_id']))
        self.db.execute('INSERT INTO events(attempt,document_id,phase,state,at,data) VALUES(?,?,?,?,?,?)',
                        (attempt, row['document_id'], phase, state, now, _json(row['phases'][phase])))

    def _finish(self, attempt, status, error, now):
        rows = self.db.execute('SELECT data FROM documents WHERE attempt=?', (attempt,)).fetchall()
        states = []
        input_failed = False
        for stored in rows:
            row = json.loads(stored['data'])
            input_failed = input_failed or row['input_state'] == 'FAILED'
            for phase in PHASES:
                entry = row['phases'][phase]
                if entry['state'] == 'RUNNING':
                    entry.update(state='INTERRUPTED' if status != 'FAILED' else 'FAILED',
                                 error=_text(error or '실행 종료 시 단계 완료 기록 없음'),
                                 finished_at=now, updated_at=now)
                    self._save(attempt, row, phase, entry['state'], now)
                states.append(entry['state'])
        if status == 'COMPLETED':
            if input_failed or any(s in BAD_STATES for s in states):
                status = 'COMPLETED_WITH_FAILURES'
            elif 'PENDING' in states:
                status = 'COMPLETED_WITH_PENDING'
        self.db.execute('UPDATE attempts SET status=?,updated_at=?,finished_at=?,error=? WHERE id=?',
                        (status, now, now, _text(error), attempt))
        self.db.execute('INSERT INTO events(attempt,document_id,phase,state,at,data) VALUES(?,?,?,?,?,?)',
                        (attempt, None, None, status, now, _json({'error': _text(error)})))

    def finish(self, status='COMPLETED', *, error=''):
        if status not in {'COMPLETED', 'FAILED', 'INTERRUPTED'}:
            raise ValueError('invalid run lifecycle status')
        if self.attempt:
            with self.db:
                stored = self.db.execute('SELECT status FROM attempts WHERE id=?', (self.attempt,)).fetchone()
                if stored and stored['status'] == 'RUNNING':
                    self._finish(self.attempt, status, error, _now())

    def close(self):
        # Closing is not evidence of completion, e.g. abrupt termination handling.
        self.db.close()


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


def _atomic_text(path, content):
    path = _plain(path)
    temp = _plain(path.with_name('.' + path.name + '-' + uuid.uuid4().hex + '.tmp'))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        _plain(path)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _csv_safe(value):
    value = _text(value, 20000)
    # Spreadsheet exports must not interpret document names/errors as formulas.
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


def export_report(directory, report=None):
    """Explicit/end-of-run export only; never rewrites or updates the ledger."""
    directory = _plain(directory)
    report = read_report(directory) if report is None else report
    if not report['recorded']:
        raise ValueError(report['note'])
    report = safe(report)
    from .genos_structure_report import export_images
    image_reports = export_images(directory, report)
    columns = ['번호', '문서 ID', '제목', '폴더', '상대 경로', '확장자', '출처', '선택 상태', '입력 상태',
               '구조화 경로', '경로 기록', '등록 태그', '엔진',
               *(f'{LABELS[p]} {field}' for p in PHASES for field in ('상태', '처리 방식', '초', '저장 경로', '상세')),
               '실패 사유']
    csv_stream = io.StringIO(newline='')
    writer = csv.writer(csv_stream)
    writer.writerow(columns)
    body = []
    for row in report['documents']:
        values = [row['number'], row['document_id'], row['title'], row['folder'], row['relative'],
                  row['extension'], row['source'], row['selection'], row['input_state'], row['route'],
                  row['route_record'], row['doc_type'], row['engine']]
        for phase in PHASES:
            e = row['phases'][phase]
            values.extend([LABELS[e['state']], LABELS.get(e.get('mode'), ''), e.get('elapsed_seconds', ''),
                           e.get('output_path', ''), e.get('detail', '')])
        values.append(_error(row))
        writer.writerow([_csv_safe(v) for v in values])
        flags = ' '.join(sorted({row['phases'][p]['state'] for p in PHASES} | {row['input_state']}))
        esc = lambda v: html.escape(str(v))
        details = '<details><summary>저장 위치·상세</summary><dl><dt>문서 ID</dt><dd>' + esc(row['document_id']) + '</dd>'
        details += '<dt>폴더 태그</dt><dd>' + esc(row['folder']) + '</dd>'
        for phase in PHASES:
            entry = row['phases'][phase]
            details += '<dt>' + esc(LABELS[phase]) + '</dt><dd>' + esc(entry.get('output_path', '저장 경로 기록 없음'))
            details += '<br>' + esc(entry.get('detail', '')) + '</dd>'
        details += '</dl></details>'
        visual = image_reports.get(row['document_id'], {})
        if visual.get('status') == 'ready':
            details += '<p><a href="' + esc(visual['href']) + '">구조화 이미지 · ' + str(visual['pages']) + '쪽</a></p>'
        elif visual.get('status') == 'error':
            details += '<p>' + esc(visual['note']) + '</p>'
        cells = [esc(row['number']), '<strong>' + esc(row['title']) + '</strong><br>' + esc(row['relative']) +
                 '<br><small>' + esc(row['extension']) + ' · ' + esc(row['source']) + '</small>',
                 esc(row['selection']) + '<br>' + esc(row['route']) + '<br><small>' + esc(row['route_record']) +
                 (' · 태그 ' + esc(row['doc_type']) if row['doc_type'] else '') + '</small>',
                 *('<span class="' + row['phases'][p]['state'].lower() + '">' + esc(_cell(row, p)) + '</span>' for p in PHASES),
                 esc(_error(row)) + details]
        body.append('<tr data-states="' + flags + '" data-failed="' + str(int(_failed(row))) + '">' +
                    ''.join('<td>' + v + '</td>' for v in cells) + '</tr>')
    title = html.escape('GENOS 문서별 처리 현황 — ' + report['run_id'])
    summary = html.escape(render_console(report, limit=1).split('\n\n')[0])
    document = '''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>''' + title + '''</title><style>
body{font:14px system-ui,sans-serif;margin:24px;color:#18202b;background:#f7f9fc}h1{font-size:23px}
pre{white-space:pre-wrap;line-height:1.65;background:white;padding:16px;border:1px solid #d6dee8}
input,select{padding:9px;margin:4px}input[type=search]{width:330px}.table{overflow:auto;max-height:70vh}
table{border-collapse:collapse;background:white;width:100%}td,th{padding:8px;border:1px solid #dde2eb;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{position:sticky;top:0;background:#e8edf7}tr[data-failed="1"]{background:#fff3ef}td:nth-child(2){min-width:200px;max-width:340px}td:nth-child(3){max-width:200px}td:last-child{max-width:370px}
.passed{color:#176735}.failed,.interrupted{color:#a6200f}.pending,.not_requested{color:#657080}details{margin-top:8px}dd{margin:4px 0 12px}dt{font-weight:600}small{color:#596476}
</style><h1>''' + title + '''</h1><pre>''' + summary + '''</pre>
<p>이 HTML은 내보낸 시점의 스냅샷입니다. 최신 상태는 상태 명령을 다시 실행해 확인하세요. 본문·키·모델 응답은 포함하지 않습니다.</p>
<p><a href="structure-images.html">구조화 이미지 목록</a> — 연결된 이미지 보고서에는 원본 페이지와 본문이 포함됩니다.</p>
<label>검색 <input id="q" type="search" placeholder="문서명 / 폴더 / 태그 / 오류"></label>
<label>상태 <select id="state"><option value="">전체</option>''' + ''.join(
        '<option value="' + s + '">' + LABELS[s] + '</option>' for s in STATES) + '''</select></label>
<label><input type="checkbox" id="failed">실패·보류·중단만</label><span id="count"></span>
<div class="table"><table><thead><tr>''' + ''.join('<th>' + html.escape(c) + '</th>' for c in
        ('번호', '문서·경로', '선택·구조화 경로', '구조화', '용어·정의·참조·DRAFT', '사유·저장 위치')) + '''</tr></thead><tbody>''' + ''.join(body) + '''</tbody></table></div>
<script>
const rows=[...document.querySelectorAll('tbody tr')],q=document.querySelector('#q'),state=document.querySelector('#state'),failed=document.querySelector('#failed');
function filter(){let count=0;const needle=q.value.toLocaleLowerCase();for(const row of rows){const show=row.textContent.toLocaleLowerCase().includes(needle)&&(!state.value||row.dataset.states.split(' ').includes(state.value))&&(!failed.checked||row.dataset.failed==='1');row.hidden=!show;if(show)count++;}document.querySelector('#count').textContent=`표시 ${count}/${rows.length}문서`;}
for(const control of [q,state,failed])control.addEventListener('input',filter);filter();
</script></html>'''
    paths = {'csv': directory / 'doc-status.csv', 'html': directory / 'doc-status.html',
             'images': directory / 'structure-images.html'}
    _atomic_text(paths['csv'], '\ufeff' + csv_stream.getvalue())
    _atomic_text(paths['html'], document)
    return {k: str(v) for k, v in paths.items()}
