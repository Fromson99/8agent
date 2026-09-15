import io
import json
import pytest
from .test_genos_all_corpus import runner


def test_console_details_snapshot_and_redaction(tmp_path, monkeypatch):
    module = runner(monkeypatch, tmp_path)
    monkeypatch.setenv('GENOS_PRIVATE_KEY', 'do-not-print-key')
    terminal = io.StringIO()
    journal = module.Journal(tmp_path, 'test')
    journal.line('OUT', terminal, '[DOCUMENT] 1/7 law/법령.xml')
    journal.line('OUT', terminal, '[2/5] doc:part-0: review (검토)')
    journal.line('ERR', terminal, 'Traceback: do-not-print-key internal detail')
    journal.line('OUT', terminal, '[QUEUE] '+json.dumps(dict(state='READY',stage='추출',attempt=1,total=5,passed=1,failed=0,pending=4,error='OUTPUT_LENGTH_LIMIT')))
    journal.line('HEARTBEAT', terminal, 'heartbeat')
    status = json.loads((tmp_path / 'current-status.json').read_text())
    assert status['document'] == '1/7 law/법령.xml'
    assert status['stage'] == 'LLM 리뷰'
    assert status['queue']['passed'] == 1
    journal.line('EXIT', terminal, json.dumps(dict(status='COMPLETED_WITH_SKIPS',exit_code=0)))
    journal.close()
    visible = terminal.getvalue()
    assert 'Traceback' not in visible and 'do-not-print-key' not in visible
    assert '검토 통과 1/5' in visible and '응답이 잘렸' in visible
    assert '마지막 로그 이후' in visible and '일부 문서를 건너뛰고 종료' in visible
    detail = (tmp_path / 'progress.log').read_text()
    assert 'Traceback: [REDACTED]' in detail
    assert 'do-not-print-key' not in (tmp_path / 'events.jsonl').read_text()
    assert 'Traceback' not in (tmp_path / 'console.log').read_text()
    assert json.loads((tmp_path / 'current-status.json').read_text())['status'] == 'COMPLETED_WITH_SKIPS'


@pytest.mark.parametrize('verbose',[False,True])
def test_verbose_and_unknown_event(tmp_path, monkeypatch, verbose):
    module = runner(monkeypatch,tmp_path)
    out = io.StringIO()
    journal = module.Journal(tmp_path,'test',verbose=verbose)
    journal.line('ERR',out,'ValueError: raw failure')
    journal.line('OUT',out,'[QUEUE] invalid JSON')
    journal.close()
    assert ('raw failure' in out.getvalue()) == verbose
    assert 'raw failure' in (tmp_path/'progress.log').read_text()
    assert '요약할 수 없는' in (tmp_path/'console.log').read_text()


@pytest.mark.parametrize('error,expected',[
    ('schema path graph: invalid JSON property','스키마'),
    ('EMPTY_CONTENT','비어'),('OUTPUT_LENGTH_LIMIT','잘렸'),
    ('ConnectionError','연결'),('401 Invalid token','인증'),
    ('BadZipFile: File is not a zip file','문서'),
    ('review_issues: unresolved_coverage','리뷰'),('unknown failure','상세 확인')])
def test_actionable_korean_errors(tmp_path,monkeypatch,error,expected):
    assert expected in runner(monkeypatch,tmp_path).explain(error)


@pytest.mark.parametrize('status,code,expected',[
    ('FAILED',1,'실행 실패'),('INTERRUPTED',130,'중단'),('CHECKED',0,'적재 미실행')])
def test_final_status_not_success_for_check_or_interrupt(tmp_path,monkeypatch,status,code,expected):
    module=runner(monkeypatch,tmp_path)
    out=io.StringIO();journal=module.Journal(tmp_path,'test')
    journal.line('EXIT',out,json.dumps(dict(status=status,exit_code=code)))
    journal.close()
    assert expected in out.getvalue()
