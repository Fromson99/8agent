"""Optional numeric finalizer timing includes cleanup without delaying callers."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json, threading
import pytest
from semantic_runtime import request_report as report_module

@pytest.mark.parametrize('fail_trace',[False,True])
def test_worker_finished_follows_cleanup_and_preserves_status(tmp_path,monkeypatch,fail_trace):
    monkeypatch.setenv('GENOS_FUNCTION_TIMING','1')
    seen=[];finished=threading.Event();cleanup=threading.Event()
    original_event=report_module.obs.event
    def event(logger,name,**fields):
        if name.startswith('timing.report.'):
            seen.append((name,fields,cleanup.is_set()))
            if name=='timing.report.worker_finished':finished.set()
        return original_event(logger,name,**fields)
    monkeypatch.setattr(report_module.obs,'event',event)
    original_log=report_module.safe_live_log
    @contextmanager
    def log(*args,**kwargs):
        try:
            with original_log(*args,**kwargs) as opened:yield opened
        finally:cleanup.set()
    monkeypatch.setattr(report_module,'safe_live_log',log)
    if fail_trace:
        def fail(*args):raise OSError('private fixture path')
        monkeypatch.setattr(report_module,'write_readable_report',fail)
    events=[{'event':'request.started','ts':datetime.now(timezone.utc).isoformat(),'level':'INFO','logger':'genos.test','request_id':'timing-test'}]
    with report_module.DeferredReport(tmp_path/'shared',tmp_path/'runtime',request_id='timing-test',api_type='LEGAL_AGENT',request={'question':'PRIVATE_QUESTION'},events=events) as report:
        report.complete({'status':200,'body':{'answer':{'text':'PRIVATE_ANSWER'}}})
    assert finished.wait(5)
    names=[x[0] for x in seen]
    assert names==['timing.report.enqueued','timing.report.worker_started','timing.report.worker_finished']
    last=seen[-1]
    assert last[2] is True
    assert last[1]['status']==('FAILED' if fail_trace else 'COMPLETE')
    assert last[1]['finalize_ms']>=0 and seen[1][1]['queue_ms']>=0
    assert seen[0][1]['enqueued_ns']<=seen[1][1]['worker_started_ns']<=last[1]['worker_finished_ns']
    assert 'PRIVATE' not in json.dumps(seen) and 'private fixture' not in json.dumps(seen)
    assert report.result['status']==200
