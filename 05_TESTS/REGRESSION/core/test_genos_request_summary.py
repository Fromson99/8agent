import asyncio
from concurrent.futures import ProcessPoolExecutor
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import pytest

from semantic_runtime import request_report as reports
from semantic_runtime import request_summary as summary


START = datetime(2026, 9, 28, 15, 1, tzinfo=timezone.utc)


def row_for(directory, ident, team='risk_team'):
    return summary.make_row(
        {'question': f'질문 {ident}\n예외도 설명해 주세요.', 'team_id': team, 'user_id': '검토자'},
        {'status': 200, 'body': {'run_id': ident, 'answer': {'text': '답변\n승인 예외를 확인합니다.'}}},
        [{'event': 'request.returning', 'duration_ms': 1250}],
        request_id=ident, started_at=START, directory=directory,
        log_path=directory / (ident + '.log'), report_path=directory / (ident + '.json'))


def publish_worker(directory, number):
    directory = Path(directory)
    summary.write_row(directory, f'req-{number}', row_for(directory, f'req-{number}'))
    summary.refresh(directory)


def test_processes_merge_without_overwriting_rows_and_excel_has_text_and_filters(tmp_path):
    directory = summary.report_directory(tmp_path, 'risk_team', START)
    with ProcessPoolExecutor(max_workers=4) as workers:
        list(workers.map(publish_worker, [directory] * 12, range(12)))
    with (directory / '질문답변.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 12 and len({row['요청 ID'] for row in rows}) == 12
    assert all(row['최종 답변'] == '답변\n승인 예외를 확인합니다.' for row in rows)
    assert all(row['소요시간(초)'] == '1.25' for row in rows)
    assert directory.parts[-2:] == ('2026-09-29', 'risk_team')
    assert (directory / '질문답변.csv').read_bytes().startswith(b'\xef\xbb\xbf')
    with zipfile.ZipFile(directory / '질문답변.xlsx') as archive:
        sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        ns = {'s': summary.NS}
        assert len(sheet.findall('s:sheetData/s:row', ns)) == 13
        assert sheet.find('s:autoFilter', ns).get('ref') == 'A1:M13'
        assert sheet.find('s:sheetViews/s:sheetView/s:pane', ns).get('state') == 'frozen'
    assert (directory / '질문답변.xlsx').stat().st_mode & 0o777 == 0o640


def test_formula_characters_long_answers_and_idempotency(tmp_path):
    directory = summary.report_directory(tmp_path, 'risk_team', START)
    row = row_for(directory, 'req-safe')
    row['question'] = '=HYPERLINK("https://example.invalid")'
    row['answer'] = '😀' * 20000
    summary.write_row(directory, 'req-safe', row)
    summary.write_row(directory, 'req-safe', row)
    summary.refresh(directory)
    with pytest.raises(ValueError): summary.write_row(directory, 'req-safe', {**row, 'answer': '다른 답변'})
    with (directory / '질문답변.csv').open(encoding='utf-8-sig', newline='') as stream:
        data = list(csv.DictReader(stream))
    assert len(data) == 1 and data[0]['질문'].startswith("'=")
    assert data[0]['최종 답변'] == row['answer']
    with zipfile.ZipFile(directory / '질문답변.xlsx') as archive:
        sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
    ns = {'s': summary.NS}
    question = sheet.find('.//s:c[@r="D2"]', ns)
    assert question.get('t') == 'inlineStr' and question.find('s:f', ns) is None
    assert question.find('s:is/s:t', ns).text == row['question']
    answer = sheet.find('.//s:c[@r="E2"]/s:is/s:t', ns).text
    assert len(answer.encode('utf-16-le')) <= 65534 and 'JSON 보고서' in answer
    assert list((directory / '_qa').glob('*.row'))[0].read_text().count('😀') == 20000


def test_gateway_reports_two_teams_in_separate_folders_without_waiting_for_summary(tmp_path, monkeypatch):
    import service
    reports._FINALIZER_QUEUE.join()
    monkeypatch.setenv('GENOS_SHARED_LOG_DIR', str(tmp_path / 'nfs'))
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path / 'runtime'))
    monkeypatch.setenv('GENOS_LLM_KEY', 'fixture-private-key')

    async def dispatch(config, data):
        if data['team_id'] == 'financial_team':
            return {'status': 503, 'body': {'error': '근거 준비 실패 fixture-private-key'}}
        return {'status': 200, 'body': {'answer': {'text': '모의 승인 답변'}}}

    monkeypatch.setattr(service, '_dispatch', dispatch)
    for team in ['risk_team', 'financial_team']:
        result = asyncio.run(service.service({}, {'API_TYPE': 'LEGAL_AGENT', 'question': '승인 요건?',
                          'request_id': 'same-request-id', 'team_id': team, 'user_id': '내부검토자'}))
        assert result['status'] == (200 if team == 'risk_team' else 503)
    reports._FINALIZER_QUEUE.join()
    files = list((tmp_path / 'nfs').rglob('질문답변.xlsx'))
    assert {path.parent.name for path in files} == {'risk_team', 'financial_team'}
    for path in files:
        with path.with_suffix('.csv').open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 1 and rows[0]['팀'] == path.parent.name
        log = path.parent / rows[0]['상세 로그']
        report = path.parent / rows[0]['JSON 보고서']
        assert log.exists() and report.exists() and report.with_suffix('.txt').exists()
        assert log.stem == report.stem
        assert 'fixture-private-key' not in path.with_suffix('.csv').read_text(encoding='utf-8-sig')
        assert rows[0]['처리 상태'] == ('답변 완료' if path.parent.name == 'risk_team' else '실패')
    before = {path: path.read_bytes() for path in (tmp_path / 'nfs').rglob('*') if path.suffix in {'.log', '.json'}}
    summary.rebuild(tmp_path / 'nfs')
    assert all(path.read_bytes() == raw for path, raw in before.items())


def test_request_date_stays_fixed_when_report_finishes_after_midnight_and_invalid_team_is_safe(tmp_path):
    start = datetime(2026, 9, 28, 14, 59, tzinfo=timezone.utc)
    with reports.live_log(tmp_path, 'req-date', team_id='risk_team', started_at=start) as (log, handler):
        path = reports.write_report(tmp_path, tmp_path / 'runtime', request_id='req-date', api_type='LEGAL_AGENT',
                                   request={'json': {'team_id': 'risk_team', 'question': '질문'}},
                                   result={'status': 500}, events=[], requested_at=start, live_log_path=log)
    assert path.parent == log.parent == tmp_path / '2026-09-28' / 'risk_team'
    assert summary.team_name({'team_id': '../../outside'}) == 'unassigned'
    with pytest.raises(ValueError): summary.report_directory(tmp_path, '../../outside', start)


def test_export_legacy_flat_reports_preserves_original_files(tmp_path):
    folder = tmp_path / '2026-09-28'
    folder.mkdir()
    path = folder / 'legacy.json'
    report = {'schema_version': 'genos-request-report-v1', 'created_at': '2026-09-28T10:01:00+00:00',
              'request_id': 'legacy', 'request': {'question': '과거 질문', 'team_id': 'financial_team'},
              'service_events': [{'event': 'request.started', 'ts': '2026-09-28T10:00:00+00:00'}],
              'result': {'status': 200, 'body': {'answer': {'text': '과거 답변'}}}}
    path.write_text(json.dumps(report, ensure_ascii=False))
    before = path.read_bytes()
    directories = summary.rebuild(tmp_path, '2026-09-28', 'financial_team')
    assert directories == [folder / 'financial_team'] and path.read_bytes() == before
    with (directories[0] / '질문답변.csv').open(encoding='utf-8-sig', newline='') as stream:
        row = next(csv.DictReader(stream))
    assert row['질문'] == '과거 질문' and row['최종 답변'] == '과거 답변'
    assert row['JSON 보고서'] == '../legacy.json' and '19:00:00' in row['요청 시각(한국)']
