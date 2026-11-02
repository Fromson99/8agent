# SRCH_ROW 진단 R2 — Dataiku/Jupyter 새 셀에 전체 복사 후 실행.
# 입력: 저장된 준비 명세 JSON 한 개. DB 접속/쓰기/적재/상태 변경 없음.
OLD_JOB_DIR = ''  # 기존 적재에서 직접 지정했다면 그 OLD_JOB_DIR과 같은 값.

import hashlib
import html
import json
from pathlib import Path
import tempfile

_SRCH_CANDIDATES = (
    ('navigation/navigation.sqlite', 'occurrence_keys', '내부 키 관계 중복'),
    ('glossary/dictionary.sqlite', 'entry_corpus_link', '사전–원문 조인 결과'),
    ('glossary/dictionary.sqlite', 'entry_definition_link', '사전–정의 조인 결과'),
)


def _srch_read(job):
    path = Path(job) / 'projection-descriptor-r7.json'
    with path.open('rb') as stream:
        raw = stream.read(32 * 1024**2 + 1)
    if len(raw) > 32 * 1024**2:
        raise ValueError('DESCRIPTOR_SIZE_LIMIT')
    saved = json.loads(raw)
    if not isinstance(saved, dict):
        raise ValueError('DESCRIPTOR_SCHEMA')
    body = {k: v for k, v in saved.items() if k != 'checksum'}
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True,
                           separators=(',', ':'), allow_nan=False).encode()
    if saved.get('checksum') != hashlib.sha256(canonical).hexdigest():
        raise ValueError('PROJECTION_DESCRIPTOR_CHECKSUM')
    tables, binding = body.get('tables'), body.get('binding')
    if not isinstance(tables, dict) or not tables or not isinstance(binding, dict):
        raise ValueError('DESCRIPTOR_SCHEMA')
    source = binding.get('source')
    if not isinstance(source, str) or len(source) != 64 or any(c not in '0123456789abcdef' for c in source):
        raise ValueError('SOURCE_BINDING_SCHEMA')
    items = []
    for kind, spec in tables.items():
        if not isinstance(spec, dict):
            raise ValueError('DESCRIPTOR_SCHEMA')
        count = spec.get('rows')
        asset, name = spec.get('asset', ''), spec.get('table', '')
        storage = spec.get('storage', 'derived')
        if type(count) is not int or count < 0 or not all(isinstance(v, str) for v in (kind, asset, name, storage)):
            raise ValueError('INVALID_PLANNED_ROW_COUNT_OR_SCHEMA')
        items.append({'kind': kind, 'asset': asset, 'table': name, 'storage': storage, 'rows': count})
    candidates = []
    for asset, name, label in _SRCH_CANDIDATES:
        found = [i for i in items if (i['asset'], i['table']) == (asset, name)]
        candidates.append({'table': name, 'label': label, 'found': bool(found),
                           'rows': sum(i['rows'] for i in found)})
    total = sum(i['rows'] for i in items)
    candidate_rows = sum(i['rows'] for i in candidates)
    return {'status': 'OK', 'scope': 'saved plan; not committed DB rows or current input revalidation',
            'descriptor_sha256': hashlib.sha256(raw).hexdigest(), 'source_release_id': source,
            'planned_rows': total, 'candidate_rows': candidate_rows,
            'conditional_remaining_rows': total - candidate_rows, 'candidates': candidates,
            'items': sorted(items, key=lambda i: (-i['rows'], i['kind']))}


def _srch_text(report):
    lines = ['SRCH_ROW 행 수 진단 R2 | ' + ('완료 · 준비계획 기준' if report['status'] == 'OK' else '확인 필요')]
    if report['status'] != 'OK':
        return '\n'.join(lines + [report['message'], report['hint'], 'DB 접속·적재·기존 상태 변경 없음'])
    total = report['planned_rows']
    percent = 100 * report['candidate_rows'] / total if total else 0
    lines += [f"전체 예정 {total:,}행 | 제외 검토 {report['candidate_rows']:,}행 ({percent:.1f}%)",
              f"후보 전부 제외 시 가정 {report['conditional_remaining_rows']:,}행",
              '아래는 제거 확정량이 아닙니다. 검색 기능 확인이 먼저입니다.', '제외 검토 후보 3개']
    lines += [f"{c['table']}: {c['rows']:,}행" if c['found'] else c['table'] + ': 명세에서 미발견'
              for c in report['candidates']]
    lines += ['큰 항목 5개 (위 후보와 중복 가능; 합산하지 않음)']
    lines += [f"{i['table'] or i['kind']}: {i['rows']:,}행" for i in report['items'][:5]]
    lines += [f"명세 {report['descriptor_sha256'][:12]} | 원문 릴리스 {report['source_release_id'][:12]}",
              '저장된 계획의 행 수입니다. 실제 DB 저장량·용량은 아닙니다.']
    return '\n'.join(lines)


def _srch_panel(report):
    esc = html.escape
    start = ('<section style="box-sizing:border-box;max-width:860px;padding:12px 16px;'
             'border:1px solid #bbc9d7;border-radius:8px;background:#fff;color:#152638;'
             'font:14px/1.4 Arial,\'Malgun Gothic\',sans-serif;text-align:left">'
             '<div style="font-size:19px;font-weight:700;margin-bottom:6px">SRCH_ROW 행 수 진단 R2</div>')
    if report['status'] != 'OK':
        return (start + '<div style="color:#a52620;font-weight:700">확인 필요</div><p>' +
                esc(report['message']) + '</p><p>' + esc(report['hint']) +
                '</p><div>DB 접속·적재·기존 상태 변경 없음</div></section>')
    total = report['planned_rows']
    percent = 100 * report['candidate_rows'] / total if total else 0
    stats = [('전체 예정', f'{total:,}'), ('제외 검토 후보', f"{report['candidate_rows']:,} ({percent:.1f}%)"),
             ('후보 전부 제외 시 가정', f"{report['conditional_remaining_rows']:,}")]
    cards = '<div style="display:flex;gap:8px;margin:6px 0">' + ''.join(
        '<div style="flex:1;min-width:0;padding:7px;background:#eff4f9;border-radius:5px">' +
        esc(label) + '<div style="font-size:21px;font-weight:700;white-space:nowrap">' +
        esc(value) + '<span style="font-size:12px"> 행</span></div></div>' for label, value in stats) + '</div>'
    def table(headers, rows):
        return ('<table style="width:100%;border-collapse:collapse;margin:2px 0 7px;font-size:13px;line-height:1.35">'
                '<thead><tr>' + ''.join('<th style="padding:3px 6px;text-align:left;border-bottom:1px solid #cbd5df">' +
                                      esc(h) + '</th>' for h in headers) + '</tr></thead><tbody>' +
                ''.join('<tr>' + ''.join('<td style="padding:3px 6px;text-align:left;border-bottom:1px solid #e8edf2;overflow-wrap:anywhere">' +
                                       esc(str(v)) + '</td>' for v in row) + '</tr>' for row in rows) + '</tbody></table>')
    candidate_table = table(['제외 검토 항목', '행 수', '의미'], [
        [c['table'], f"{c['rows']:,}" if c['found'] else '미발견', c['label']] for c in report['candidates']])
    largest_table = table(['큰 항목 5개', '행 수', '자산'], [
        [i['table'] or i['kind'], f"{i['rows']:,}", '/'.join(Path(i['asset']).parts[-2:])]
        for i in report['items'][:5]])
    return (start + '<div style="color:#31546f">완료 · 저장된 준비계획 기준 · DB 접속 없음</div>' + cards +
            '<div style="font-size:12px;margin:4px 0">제외 후보는 제거 확정량이 아닙니다. 검색 기능 확인이 먼저입니다.</div>' +
            candidate_table + '<div style="font-size:12px">아래 큰 항목은 위 후보와 중복될 수 있어 합산하지 않습니다.</div>' +
            largest_table + '<div style="font-size:11px;color:#526474">명세 ' + report['descriptor_sha256'][:12] +
            ' · 원문 릴리스 ' + report['source_release_id'][:12] +
            '<br>계획상 행 수이며 실제 DB 저장량·용량 또는 현재 입력 재검증 결과가 아닙니다.</div></section>')


def _srch_main(job):
    try:
        report = _srch_read(job)
    except Exception as exc:
        if isinstance(exc, FileNotFoundError):
            message, hint = '준비 명세 파일을 찾지 못했습니다.', '기존 적재와 같은 노트북에서 실행하고 OLD_JOB_DIR 값을 확인하세요.'
        elif isinstance(exc, PermissionError):
            message, hint = '준비 명세 파일을 읽을 권한이 없습니다.', '기존 적재를 실행한 계정·노트북에서 확인하세요.'
        elif str(exc) == 'PROJECTION_DESCRIPTOR_CHECKSUM':
            message, hint = '준비 명세 checksum이 일치하지 않습니다.', '명세나 state를 수정하지 말고 이 화면을 전달하세요.'
        else:
            message, hint = '준비 명세를 해석하지 못했습니다 (' + type(exc).__name__ + ').', '파일이 완전한지 확인하세요. 상세 오류는 SRCH_ROW_DIAG_R2_REPORT 변수에 보관됩니다.'
        report = {'status': 'ERROR', 'message': message, 'hint': hint, 'error_type': type(exc).__name__, 'error_detail': str(exc)}
    panel = _srch_panel(report)
    try:
        from IPython.display import HTML, clear_output, display
    except ImportError:
        print(_srch_text(report))
    else:
        clear_output(wait=True)
        display(HTML(panel))
    return report


_srch_job = Path(OLD_JOB_DIR) if OLD_JOB_DIR else (
    Path(tempfile.gettempdir()) / 'legal-existing-nfs-20261029-r1' /
    'financial-risk-success-20261005-schema-r2' / 'oracle-import-r2')
SRCH_ROW_DIAG_R2_REPORT = _srch_main(_srch_job)
