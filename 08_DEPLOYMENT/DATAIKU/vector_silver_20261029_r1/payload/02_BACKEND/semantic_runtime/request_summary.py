"""Team/date QA overviews; compact immutable rows and atomic CSV/XLSX snapshots."""
from contextlib import contextmanager
import argparse
import csv
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile

KST = timezone(timedelta(hours=9))
HEADERS = ('요청 시각(한국)', '팀', '사용자', '질문', '최종 답변', '처리 상태',
           'HTTP', '소요시간(초)', '오류', '요청 ID', '실행 ID', '상세 로그', 'JSON 보고서')
KEYS = ('requested_at', 'team', 'user', 'question', 'answer', 'status',
        'http_status', 'seconds', 'error', 'request_id', 'run_id', 'log', 'report')
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
ET.register_namespace('', NS)
ET.register_namespace('r', REL)


def request_fields(request):
    if not isinstance(request, dict): return {}
    inner = request.get('json')
    return {**request, **inner} if isinstance(inner, dict) else request


def team_name(request):
    team = request_fields(request).get('team_id')
    return team if isinstance(team, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}_team', team) else 'unassigned'


def report_directory(root, team='unassigned', started_at=None, *, component='legal_agent'):
    root = Path(root)
    if not root.is_absolute(): raise ValueError('GENOS_SHARED_LOG_DIR must be an absolute path')
    if team != 'unassigned' and not re.fullmatch(r'[A-Za-z0-9_-]{1,64}_team', team):
        raise ValueError('invalid report team')
    started_at = started_at or datetime.now(timezone.utc)
    directory = root / started_at.astimezone(KST).date().isoformat() / team
    if component not in (None, 'legal_agent', 'ad_mode'):
        raise ValueError('invalid report component')
    if component is not None:
        directory /= component
    directory.mkdir(parents=True, exist_ok=True, mode=0o750)
    return directory


def make_row(request, result, events, *, request_id, started_at, directory, log_path=None, report_path=None):
    fields = request_fields(request)
    question = fields.get('question') or fields.get('q')
    if not isinstance(question, str) or not question.strip(): return None
    result = result if isinstance(result, dict) else {}
    body = result.get('body') if isinstance(result.get('body'), dict) else {}
    answer = body.get('answer') if isinstance(body.get('answer'), dict) else {}
    http = result.get('status', 200)
    http = http if isinstance(http, int) else 500
    duration = next((r.get('duration_ms') for r in reversed(events)
                     if r.get('event') in {'request.returning', 'request.finished'}), None)
    text = answer.get('text') or body.get('text') or ''
    error = body.get('detail') or body.get('error') or body.get('error_type') or ''
    def relative(path):
        return os.path.relpath(path, directory) if path is not None else ''
    return {'requested_at': started_at.astimezone(KST).isoformat(timespec='seconds'),
            'team': team_name(request), 'user': str(fields.get('user_id') or ''),
            'question': question, 'answer': str(text),
            'status': '실패' if http >= 400 or body.get('answer_status') in ('error', 'failed') else '처리 중' if body.get('answer_status') == 'pending' else '답변 완료' if text else '답변 없음',
            'http_status': http, 'seconds': round(duration/1000, 3) if isinstance(duration, (int, float)) else '',
            'request_id': request_id, 'run_id': str(body.get('run_id') or ''),
            'log': relative(log_path), 'report': relative(report_path), 'error': str(error)}


@contextmanager
def atomic_file(target, mode='w', **kwargs):
    """Readers see a complete old or new snapshot; never a partially written file."""
    fd, temporary = tempfile.mkstemp(prefix='.qa-', dir=target.parent)
    try:
        os.fchmod(fd, 0o640)
        with os.fdopen(fd, mode, **kwargs) as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def write_row(directory, record_id, row):
    """One tiny row per unique request record; full journal JSON is never rescanned live."""
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', record_id) or record_id in {'.', '..'}:
        raise ValueError('invalid summary record ID')
    rows = directory / '_qa'
    rows.mkdir(parents=True, exist_ok=True, mode=0o750)
    target = rows / (record_id + '.row')
    encoded = json.dumps(row, ensure_ascii=False, sort_keys=True)
    if target.exists():
        if target.read_text() != encoded: raise ValueError('summary record already has different content')
    else:
        # Linking the finished temporary file keeps this record append-only.
        fd, temporary = tempfile.mkstemp(prefix='.row-', dir=rows)
        try:
            os.fchmod(fd, 0o640)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
            try: os.link(temporary, target)
            except FileExistsError:
                if target.read_text() != encoded: raise ValueError('summary record conflict')
        finally: os.unlink(temporary)
    return target


@contextmanager
def summary_lock(directory):
    flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(directory / '.qa.lock', flags, 0o640)
    os.fchmod(fd, 0o640)
    with os.fdopen(fd, 'r+') as stream:
        deadline = time.monotonic() + 10
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline: raise TimeoutError('QA summary lock busy; compact row is preserved')
                time.sleep(0.05)
        try: yield
        finally: fcntl.flock(stream, fcntl.LOCK_UN)


def csv_cell(value):
    text = str(value if value is not None else '')
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text


def _xml_text(value):
    text = str(value if value is not None else '')
    text = ''.join(ch for ch in text if ch in '\t\n\r' or
                   0x20 <= ord(ch) <= 0xD7FF or 0xE000 <= ord(ch) <= 0xFFFD or 0x10000 <= ord(ch) <= 0x10FFFF)
    # Excel's limit is 32,767 UTF-16 code units, including surrogate pairs.
    encoded = text.encode('utf-16-le')
    if len(encoded) > 65000:
        text = encoded[:65000].decode('utf-16-le', errors='ignore') + '\n… 전체 내용은 JSON 보고서에서 확인'
    return text


def write_xlsx(path, rows):
    """Small dependency-free OOXML workbook: text cells, filters and a frozen header."""
    def tag(name): return '{' + NS + '}' + name
    sheet = ET.Element(tag('worksheet'))
    views = ET.SubElement(sheet, tag('sheetViews'))
    view = ET.SubElement(views, tag('sheetView'), workbookViewId='0')
    ET.SubElement(view, tag('pane'), ySplit='1', topLeftCell='A2', activePane='bottomLeft', state='frozen')
    cols = ET.SubElement(sheet, tag('cols'))
    widths = [24, 20, 20, 65, 90, 16, 10, 16, 45, 35, 35, 45, 45]
    for i, width in enumerate(widths, 1):
        ET.SubElement(cols, tag('col'), min=str(i), max=str(i), width=str(width), customWidth='1')
    data = ET.SubElement(sheet, tag('sheetData'))
    for i, cells in enumerate([HEADERS, *[[row.get(key, '') for key in KEYS] for row in rows]], 1):
        row = ET.SubElement(data, tag('row'), r=str(i), ht='24' if i == 1 else '90', customHeight='1')
        for j, value in enumerate(cells):
            cell = ET.SubElement(row, tag('c'), r=f'{chr(65+j)}{i}', s='1' if i == 1 else '0')
            if isinstance(value, (int, float)):
                ET.SubElement(cell, tag('v')).text = str(value)
            else:
                cell.set('t', 'inlineStr')
                text = ET.SubElement(ET.SubElement(cell, tag('is')), tag('t'), {'{http://www.w3.org/XML/1998/namespace}space': 'preserve'})
                text.text = _xml_text(value)
    ET.SubElement(sheet, tag('autoFilter'), ref=f'A1:M{len(rows)+1}')
    styles = '''<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''
    with atomic_file(path, 'wb') as stream, zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>''')
        archive.writestr('_rels/.rels', f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', f'<workbook xmlns="{NS}" xmlns:r="{REL}"><sheets><sheet name="질문답변" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="{REL}/styles" Target="styles.xml"/></Relationships>')
        archive.writestr('xl/styles.xml', styles)
        archive.writestr('xl/worksheets/sheet1.xml', ET.tostring(sheet, encoding='utf-8', xml_declaration=True))


def refresh(directory):
    directory = Path(directory)
    with summary_lock(directory):
        paths = sorted((directory / '_qa').glob('*.row'))
        signature = hashlib.sha256('\n'.join(p.name for p in paths).encode()).hexdigest()
        receipt = directory / '.qa.snapshot'
        if receipt.exists() and receipt.read_text() == signature and all(
                (directory / name).is_file() for name in ('질문답변.csv', '질문답변.xlsx')):
            return
        rows = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
        rows.sort(key=lambda row: (row['requested_at'], row['request_id'], row.get('log', '')), reverse=True)
        with atomic_file(directory / '질문답변.csv', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(HEADERS)
            writer.writerows([csv_cell(row.get(key, '')) for key in KEYS] for row in rows)
        write_xlsx(directory / '질문답변.xlsx', rows)
        with atomic_file(receipt, encoding='utf-8') as stream: stream.write(signature)


def rebuild(root, day=None, team=None):
    """Read existing reports without moving logs or changing their historical bytes."""
    root = Path(root).resolve()
    if day is not None: datetime.strptime(day, '%Y-%m-%d')
    scan = root / day if day else root
    directories = set()
    for path in sorted(scan.rglob('*.json')):
        report = json.loads(path.read_text(encoding='utf-8'))
        if report.get('schema_version') != 'genos-request-report-v1': continue
        request = report.get('request') or {}
        selected_team = team_name(request)
        if team and team != selected_team: continue
        first_event = next((event.get('ts') for event in report.get('service_events', [])
                            if event.get('event') == 'request.started'), None)
        started = datetime.fromisoformat(report.get('requested_at') or first_event or report['created_at'])
        if started.tzinfo is None: started = started.replace(tzinfo=timezone.utc)
        directory = report_directory(root, selected_team, started, component=report.get('component'))
        log = report.get('live_log_path')
        row = make_row(request, report.get('result'), report.get('service_events') or [],
                       request_id=report.get('request_id', ''), started_at=started,
                       directory=directory, log_path=Path(log) if log else None, report_path=path)
        if row:
            write_row(directory, path.stem, row)
            directories.add(directory)
    # Also recover snapshots after a previous refresh failed, even before a full report was written.
    for path in scan.rglob('_qa'):
        if path.is_dir() and (not team or path.parent.name == team or
                             (path.parent.name in ('legal_agent', 'ad_mode') and path.parent.parent.name == team)):
            directories.add(path.parent)
    for directory in sorted(directories): refresh(directory)
    return sorted(directories)


def main():
    parser = argparse.ArgumentParser(description='Rebuild team/date Excel QA overviews from saved request reports.')
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--date')
    parser.add_argument('--team')
    args = parser.parse_args()
    for directory in rebuild(args.root, args.date, args.team): print(directory / '질문답변.xlsx')


if __name__ == '__main__': main()
