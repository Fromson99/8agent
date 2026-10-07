"""Ordinary synthetic status contracts; no source ingestion or provider calls."""
import csv
import importlib.util
import io
import json
from pathlib import Path
import sqlite3

import pytest

from lawrag.pipeline.genos_status import (DATABASE, Ledger, export_report, read_report,
                                         render_console, validate_run_id)


def rows():
    return [{'document_id': 'abc', 'relative': 'law/법령/본문.xml', 'name': '법령 제목', 'source': 'external'},
            {'document_id': 'def', 'relative': 'law/법령/별표/표.hwp', 'name': '별표 제목',
             'source': 'external', 'folder': '외규/법령/별표', 'doc_type': 'hwp-form', 'engine': ''}]


def test_phase_states_success_is_not_entire_pipeline(tmp_path):
    ledger = Ledger(tmp_path).start(rows(), 'all')
    ledger.update('abc', 'structure', 'RUNNING', route='parser:xml')
    ledger.update('abc', 'structure', 'PASSED', mode='NEW', elapsed_seconds=164.25,
                  output_path='/workspace/01_DATA/STRUCTURE/key', route_record='ACTUAL')
    ledger.update('def', 'structure', 'FAILED', error='빈 구조')
    ledger.update('def', 'index', 'BLOCKED', error='구조화 실패')
    report = read_report(tmp_path)
    assert report['counts']['structure']['PASSED'] == 1
    assert report['counts']['structure']['FAILED'] == 1
    assert report['counts']['index']['PASSED'] == 0
    assert report['counts']['index']['PENDING'] == 1
    assert report['documents'][0]['phases']['structure']['elapsed_seconds'] == 164.25
    assert report['documents'][0]['route_record'] == 'ACTUAL'
    assert report['documents'][1]['route'] == 'registered:hwp-form'
    ledger.finish()
    assert read_report(tmp_path)['attempt']['status'] == 'COMPLETED_WITH_FAILURES'
    ledger.close()


def test_resume_attempt_preserved_reused_explicit(tmp_path):
    ledger = Ledger(tmp_path).start(rows(), 'structure')
    first = ledger.attempt
    ledger.update('abc', 'structure', 'PASSED', mode='NEW')
    ledger.update('def', 'structure', 'RUNNING')
    ledger.close()  # Simulate termination with no lifecycle cleanup.
    previous = read_report(tmp_path)
    assert previous['attempt']['status'] == 'RUNNING'
    assert '프로세스' in previous['note']
    ledger = Ledger(tmp_path).start(rows(), 'structure')
    current = read_report(tmp_path)
    assert current['counts']['structure']['PENDING'] == 2
    assert current['counts']['structure']['PASSED'] == 0
    assert current['counts']['index']['NOT_REQUESTED'] == 2
    old = ledger.db.execute('SELECT status FROM attempts WHERE id=?', (first,)).fetchone()
    assert old[0] == 'INTERRUPTED'
    old_doc = json.loads(ledger.db.execute('SELECT data FROM documents WHERE attempt=? AND id=?', (first, 'def')).fetchone()[0])
    assert old_doc['phases']['structure']['state'] == 'INTERRUPTED'
    ledger.update('abc', 'structure', 'RUNNING')
    ledger.update('abc', 'structure', 'PASSED', mode='REUSED')
    assert read_report(tmp_path)['counts']['structure']['REUSED'] == 1
    assert ledger.db.execute('SELECT count(*) FROM events').fetchone()[0] >= 6
    ledger.finish('INTERRUPTED')
    ledger.close()


def test_interrupt_never_turns_pending_success(tmp_path):
    ledger = Ledger(tmp_path).start(rows(), 'all')
    ledger.update('abc', 'structure', 'RUNNING')
    ledger.finish('INTERRUPTED', error='사용자 중단')
    report = read_report(tmp_path)
    assert report['attempt']['status'] == 'INTERRUPTED'
    assert report['counts']['structure']['INTERRUPTED'] == 1
    assert report['counts']['structure']['PENDING'] == 1
    assert report['counts']['index']['PENDING'] == 2
    with pytest.raises(ValueError, match='finished attempt'):
        ledger.update('abc', 'structure', 'PASSED')
    ledger.finish('FAILED')  # Idempotent cleanup cannot rewrite earlier interruption.
    assert read_report(tmp_path)['attempt']['status'] == 'INTERRUPTED'
    ledger.close()


def test_excluded_separate_from_selected_denominator_and_raw(tmp_path):
    errors = [{'source': 'internal', 'item': '파일.gul', 'error': '지원하지 않는 형식', 'scope': 'document'},
              {'source': 'law', 'item': 'manifest', 'error': '없음', 'scope': 'source'}]
    ledger = Ledger(tmp_path).start(rows(), 'all', excluded=errors,
                                   ignored=[{'source': 'law', 'path': '대체.html', 'reason': 'alternate'}])
    report = read_report(tmp_path)
    assert report['selection_counts'] == {'SELECTED': 2, 'INPUT_FAILED': 1, 'EXCLUDED': 1}
    assert report['counts']['structure']['PENDING'] == 2
    assert sum(report['counts']['structure'][s] for s in ('PENDING', 'BLOCKED')) == 2
    assert report['documents'][2]['phases']['structure']['state'] == 'BLOCKED'
    assert report['documents'][3]['phases']['structure']['state'] == 'NOT_REQUESTED'
    ledger.finish('INTERRUPTED')
    ledger.start(rows(), 'raw', excluded=errors)
    ledger.finish()
    report = read_report(tmp_path)
    assert report['counts']['structure']['NOT_REQUESTED'] == 2
    assert report['counts']['structure']['PASSED'] == 0
    ledger.close()


def test_old_run_is_no_record_and_read_only(tmp_path):
    (tmp_path / 'result-old.json').write_text('{"ok":true}')
    before = list(tmp_path.iterdir())
    report = read_report(tmp_path)
    assert report['recorded'] is False
    assert '추정하지' in render_console(report)
    assert list(tmp_path.iterdir()) == before
    with pytest.raises(ValueError, match='상태 원장이 없습니다'):
        export_report(tmp_path)


def test_escaped_html_formula_csv_secret_redaction_and_no_event_exports(tmp_path, monkeypatch):
    monkeypatch.setenv('GENOS_TEST_KEY', 'hidden-api-key')
    source = rows()
    source[0]['name'] = '<script>alert(1)</script>'
    source[0]['folder'] = '=1+1'
    source[0]['relative'] = 'law/<img src=x onerror=alert(1)>.xml'
    source[0]['request'] = 'this unapproved field must not be copied'
    ledger = Ledger(tmp_path).start(source, 'structure')
    ledger.update('abc', 'structure', 'FAILED', error='hidden-api-key <script>evil()</script>')
    assert not (tmp_path / 'doc-status.html').exists()
    report = read_report(tmp_path)
    db_before = (tmp_path / DATABASE).read_bytes()
    exported = export_report(tmp_path, report)
    assert (tmp_path / DATABASE).read_bytes() == db_before
    html = Path(exported['html']).read_text()
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert '<img src=x' not in html and '&lt;img src=x' in html
    assert 'hidden-api-key' not in html
    assert 'this unapproved field' not in html
    assert 'data-failed="1"' in html and 'addEventListener' in html
    assert 'http://' not in html and 'https://' not in html
    csv_data = list(csv.reader(io.StringIO(Path(exported['csv']).read_text(encoding='utf-8-sig'))))
    assert "'=1+1" in csv_data[1]
    assert 'hidden-api-key' not in Path(exported['csv']).read_text()
    assert '[REDACTED]' in Path(exported['csv']).read_text()
    ledger.finish('INTERRUPTED')
    ledger.close()


def test_filter_limit_and_route_metadata(tmp_path):
    ledger = Ledger(tmp_path).start(rows(), 'structure')
    ledger.update('abc', 'structure', 'PASSED', mode='REUSED')
    ledger.update('def', 'structure', 'FAILED', error='형식 오류')
    report = read_report(tmp_path)
    text = render_console(report, failures_only=True, limit=0)
    assert 'law/법령/본문.xml' not in text
    assert 'law/법령/별표/표.hwp' in text
    assert '표시 1/1문서' in text
    assert '완료 1 (신규 0/재사용 1)' in text
    with pytest.raises(ValueError):
        render_console(report, limit=-1)
    ledger.finish()
    ledger.close()


@pytest.mark.parametrize('run_id', ['../x', 'x/y', '.', '..', '', 'a' * 81, '한글'])
def test_invalid_run_ids(run_id):
    with pytest.raises(ValueError):
        validate_run_id(run_id)


def test_symlink_paths_and_output_refused(tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    link = tmp_path / 'link'
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError):
        Ledger(link)
    with pytest.raises(ValueError):
        read_report(link)
    ledger = Ledger(real).start(rows(), 'raw')
    target = tmp_path / 'outside.txt'
    target.write_text('preserve')
    (real / 'doc-status.html').symlink_to(target)
    with pytest.raises(ValueError):
        export_report(real)
    assert target.read_text() == 'preserve'
    ledger.close()


def test_unknown_fields_states_and_duplicate_rejected(tmp_path):
    ledger = Ledger(tmp_path)
    with pytest.raises(ValueError, match='중복'):
        ledger.start([rows()[0], rows()[0]], 'all')
    ledger.start(rows(), 'structure')
    with pytest.raises(ValueError, match='unsupported status metadata'):
        ledger.update('abc', 'structure', 'PASSED', request={'api_key': 'x'})
    with pytest.raises(ValueError):
        ledger.update('abc', 'structure', 'PASSED', mode='MAYBE')
    with pytest.raises(ValueError):
        ledger.update('abc', 'structure', 'PASSED', elapsed_seconds=float('nan'))
    with pytest.raises(ValueError, match='unknown status document'):
        ledger.update('missing', 'structure', 'PASSED')
    with pytest.raises(ValueError):
        ledger.update('abc', 'structure', 'WHATEVER')
    ledger.close()


def test_cli_read_and_export(tmp_path, monkeypatch, capsys):
    from lawrag.pipeline import genos_stages
    root = Path(__file__).resolve().parents[3]
    path = root / '06_TOOLS/COMMANDS/genos_data_status.py'
    spec = importlib.util.spec_from_file_location('test_status_cli', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(genos_stages, 'offline_data_root', lambda _: tmp_path)
    assert module.main(['--run-id', 'no-record']) == 2
    assert '상태 원장이 없습니다' in capsys.readouterr().out
    logs = tmp_path / 'LOGS/demo'
    ledger = Ledger(logs).start(rows(), 'structure')
    ledger.update('abc', 'structure', 'PASSED', mode='NEW')
    ledger.finish('INTERRUPTED')
    ledger.close()
    assert module.main(['--run-id', 'demo', '--export', '--limit', '0']) == 0
    output = capsys.readouterr().out
    assert 'HTML:' in output and '구조화: 완료 1' in output
    assert (logs / 'doc-status.html').is_file()
