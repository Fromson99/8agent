"""Cold/stalled/failed preparation remains observable without loading real data."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.error

import pytest

from semantic_runtime import oracle_dp_io as io
from semantic_runtime.preparation_progress import Progress

ROOT = Path(__file__).resolve().parents[2]


def workflow():
    spec = importlib.util.spec_from_file_location('preparation_workflow_test', ROOT / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_blocked_sql_has_live_wait_time_and_keeps_secrets_out(tmp_path):
    entered, release = threading.Event(), threading.Event()
    progress = Progress()
    progress.update('source.download', table='document', rows_done=0, rows_total=1)
    class Client:
        SQL_PATH = '/sql'
        def request(self, *args, **kwargs):
            entered.set()
            assert release.wait(3)
            return {'items': [{'resultSet': {'items': [], 'offset': 0, 'hasMore': False}}]}
    sql = io.SQL(Client(), journal=tmp_path/'calls.jsonl', binding='synthetic', progress=progress)
    failures = []
    def work():
        try:
            sql.query('SELECT secret_column FROM private_table', [('v', 'private-value', 'VARCHAR2')])
        except BaseException as exc:
            failures.append(exc)
    thread = threading.Thread(target=work)
    thread.start()
    try:
        assert entered.wait(2)
        state = progress.snapshot()
        assert state['sql_in_flight'] and state['sql_calls'] == 1
        assert state['rows_done'] == 0
        assert 'private' not in json.dumps(state)
    finally:
        release.set()
        thread.join(3)
    assert not failures and not thread.is_alive()
    assert not progress.snapshot()['sql_in_flight']
    assert 'private-value' not in (tmp_path/'calls.jsonl').read_text()


def test_sql_failure_retains_journal_without_retry_or_false_progress(tmp_path):
    class Client:
        SQL_PATH = '/sql'
        def request(self, *args, **kwargs):
            raise TimeoutError('credential=private-secret')
    progress = Progress()
    progress.update('source.download', rows_done=0, rows_total=9)
    sql = io.SQL(Client(), journal=tmp_path/'calls.jsonl', binding='synthetic', progress=progress)
    with pytest.raises(io.DPError, match='READ_FAILED: TimeoutError'):
        sql.query('SELECT x FROM synthetic')
    state = progress.snapshot()
    assert state['sql_calls'] == 1 and state['sql_status'] == 'READ_FAILED'
    assert state['rows_done'] == 0 and not state['sql_in_flight']
    assert 'private-secret' not in (tmp_path/'calls.jsonl').read_text()


def test_stalled_warmup_status_bypasses_ad_and_logs_heartbeat(monkeypatch):
    import service
    from semantic_runtime.preparation_progress import current
    entered, release = threading.Event(), threading.Event()
    events = []
    monkeypatch.setattr(service.obs, 'event', lambda logger, event, **fields: events.append((event, fields)))
    monkeypatch.setattr(service, '_WARMUP_HEARTBEAT_SECONDS', .01)
    monkeypatch.setattr(service, '_WARMUP_STATE', {'state': 'NOT_STARTED'})
    monkeypatch.setattr(service, '_ad_control', lambda: pytest.fail('status must not touch AD/SQL/NFS'))
    def prepare():
        current.update('oracle.connect')
        entered.set()
        assert release.wait(3)
        return {'generation_path': '/synthetic', 'document_count': 1}
    monkeypatch.setattr(service, '_warm_resources', prepare)
    first = asyncio.run(service.service({}, {'API_TYPE': 'WARMUP', 'request_id': 'control-1'}))
    try:
        assert entered.wait(1)
        assert first['body']['state'] == 'RUNNING'
        for _ in range(100):
            if any(e == 'warmup.progress' for e, _ in events):
                break
            time.sleep(.005)
        status = asyncio.run(service.service({}, {'API_TYPE': 'WARMUP_STATUS', 'request_id': 'control-2'}))
        assert status['body']['state'] == 'RUNNING'
        assert status['body']['progress']['phase'] == 'oracle.connect'
        assert any(e == 'warmup.progress' for e, _ in events)
    finally:
        release.set()
        for _ in range(100):
            if service._WARMUP_STATE['state'] != 'RUNNING':
                break
            time.sleep(.005)
    assert service._WARMUP_STATE['state'] == 'READY'
    assert any(e == 'warmup.finished' and f['state'] == 'READY' for e, f in events)
    count = sum(e == 'warmup.progress' for e, _ in events)
    time.sleep(.025)
    assert count == sum(e == 'warmup.progress' for e, _ in events)


def test_workflow_control_uses_short_timeout_and_retains_unknown_backend_state(monkeypatch, capsys):
    w = workflow()
    monkeypatch.setattr(w, '_settings', lambda: ('http://synthetic/json', 'private-token', 2100))
    timeouts = []
    def request(req, *, timeout):
        timeouts.append(timeout)
        raise urllib.error.URLError(TimeoutError('private-token'))
    monkeypatch.setattr(w.urllib.request, 'urlopen', request)
    out = asyncio.run(w.run({'question': 'WARMUP_STATUS', 'request_id': 'status-test'}))
    assert timeouts == [30]
    assert out['answer_status'] == 'failed'
    assert out['failure_kind'] == 'warmup_status_transport_timeout'
    assert '종료 여부는 확인되지 않았습니다' in out['text']
    assert 'workflow.entry.received' in capsys.readouterr().out
    assert 'private-token' not in out['text']


def test_status_progress_reaches_workflow_display_without_model(monkeypatch):
    w = workflow()
    monkeypatch.setattr(w, '_post_code_serving', lambda body: {
        'state': 'RUNNING', 'worker_id': 'synthetic', 'ad_worker_recovery': {'state': 'FAILED'},
        'progress': {'phase': 'source.download', 'rows_done': 100, 'rows_total': 400,
                     'elapsed_seconds': 20, 'last_progress_age_seconds': 8,
                     'sql_in_flight': True, 'sql_elapsed_seconds': 8}})
    out = asyncio.run(w.run({'question': 'WARMUP_STATUS'}))
    assert '100/400' in out['text'] and 'Oracle 응답 대기: 8초' in out['text']
    assert out['warmup']['state'] == 'RUNNING'
    assert '예약 작업 복구: FAILED' in out['text']


def test_legal_request_keeps_original_timeout(monkeypatch):
    w = workflow()
    monkeypatch.setattr(w, '_settings', lambda: ('http://synthetic/json', 'fixture', 2100))
    def request(req, *, timeout):
        assert timeout == 2100
        raise TimeoutError('synthetic')
    monkeypatch.setattr(w.urllib.request, 'urlopen', request)
    with pytest.raises(TimeoutError):
        w._post_code_serving({'API_TYPE': 'LEGAL_AGENT', 'request_id': 'legal-test'})


def test_service_import_and_control_do_not_wait_for_ad_storage(tmp_path):
    script = '''import asyncio, threading, os, time
import semantic_runtime.ad_gateway as ad
entered, release = threading.Event(), threading.Event()
def blocked(*args):
 entered.set()
 assert release.wait(4)
ad.start_worker=blocked
os.environ['AD_WORKER_ENABLED']='1'
os.environ['GENOS_GENERATION']='/synthetic-generation'
import service
try:
 deadline=time.monotonic()+1
 while service._AD_WORKER_RECOVERY['state']=='RUNNING' and time.monotonic()<deadline:time.sleep(.01)
 assert not entered.is_set()
 result=asyncio.run(service.service({}, {'API_TYPE':'WARMUP_STATUS'}))
 assert result['body']['state']=='NOT_STARTED'
 assert result['body']['ad_worker_recovery']['state']=='DISABLED'
 print('IMPORT_AND_CONTROL_RESPONSIVE')
finally:release.set()
'''
    env={**os.environ, 'GENOS_AUTO_WARMUP':'0', 'AD_WORKER_ENABLED':'0',
         'GENOS_SYSTEM_LOG_ENABLED':'0', 'PYTHONPATH':str(ROOT)+':'+str(ROOT/'02_BACKEND')}
    done=subprocess.run([sys.executable,'-c',script],cwd=ROOT,env=env,capture_output=True,text=True,timeout=8)
    assert done.returncode==0,done.stdout+done.stderr
    assert 'IMPORT_AND_CONTROL_RESPONSIVE' in done.stdout


def test_ad_startup_failure_stays_separate_from_data_readiness(monkeypatch):
    import service
    from types import SimpleNamespace
    def failed(*args):raise OSError('synthetic storage failure')
    monkeypatch.setattr(service, '_AD_WORKER_RECOVERY', {'state':'DISABLED'})
    monkeypatch.setattr(service, '_ad_control', lambda:SimpleNamespace(start_worker=failed))
    monkeypatch.setattr(service, '_WARMUP_STATE', {'state':'NOT_STARTED'})
    service._recover_ad_worker()
    out=asyncio.run(service.service({}, {'API_TYPE':'WARMUP_STATUS'}))
    assert out['body']['state']=='NOT_STARTED'
    assert out['body']['ad_worker_recovery']=={'state':'FAILED','error_type':'OSError'}
