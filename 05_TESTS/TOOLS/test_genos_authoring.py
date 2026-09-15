"""Synthetic, network-free durability checks; not model/semantic evaluation."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / '06_TOOLS/OFFLINE/genos_authoring.py'
spec = importlib.util.spec_from_file_location('genos_authoring', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SCHEMA = {'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': ['text'], 'additionalProperties': False}


def response(value, finish='stop'):
    return json.dumps({'model': 'fixture-model', 'choices': [{'finish_reason': finish, 'message': {'content': json.dumps(value)}}],
                       'usage': {'prompt_tokens': 10, 'completion_tokens': 5}})


@pytest.fixture
def q(tmp_path):
    src = tmp_path / 'source.sqlite'
    with sqlite3.connect(src) as c:
        c.execute('create table authoring_job(job_id text,document_id text,state text,input_json text)')
        c.executemany('insert into authoring_job values(?,?,?,?)', [('a', 'd', 'PENDING_EXTRACTION', '{"blocks":[]}'),
                                                                ('held', 'd', 'NEEDS_SEGMENTATION', '{"blocks":[]}')])
    return m.prepare(tmp_path / 'queue', src, 'fixture', SCHEMA, model='fixture-model', revision='fixture-rev', endpoint='http://localhost:8000/v1')


def call(q, answers, **kwargs):
    calls = []
    def factory():
        def provider(request):
            calls.append(request)
            value = answers.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value
        return provider
    result = m.run(q, execute=True, max_calls=kwargs.pop('max_calls', 10), provider_factory=factory, **kwargs)
    return calls, result


def test_no_network_by_default(q):
    def forbidden():
        raise AssertionError('provider constructed')
    assert m.run(q, provider_factory=forbidden)['jobs']['READY'] == 1


def test_extract_checkpoint_resumes_review_and_skips_completed(q):
    calls, _ = call(q, [response({'text': 'candidate'})], max_calls=1)
    assert len(calls) == 1
    q = m.Queue(q.directory)
    calls, result = call(q, [response({'passed': True, 'issues': []})])
    assert calls[0]['response_format']['json_schema']['name'] == 'authoring_review'
    assert result['jobs']['REVIEW_PASSED_CANDIDATE'] == 1
    assert len(call(q, [])[0]) == 0
    assert result['jobs']['NEEDS_SEGMENTATION'] == 1


def test_saved_response_does_not_recall_after_restart(q):
    with m.exclusive(q.directory):
        a = q.claim()
        q.received(a, response({'text': 'saved'}), 1.5)
    calls, result = call(m.Queue(q.directory), [response({'passed': True, 'issues': []})])
    assert len(calls) == 1
    assert result['attempts']['VALIDATED'] == 2


def test_process_exit_with_started_attempt(q):
    code = 'import runpy,sys,os; m=runpy.run_path(sys.argv[1]); q=m["Queue"](sys.argv[2]); q.claim(); os._exit(91)'
    proc = subprocess.run([sys.executable, '-c', code, str(SCRIPT), str(q.directory)])
    assert proc.returncode == 91
    calls, result = call(q, [response({'text': 'resumed'}), response({'passed': True, 'issues': []})])
    assert len(calls) == 2
    assert result['attempts']['INTERRUPTED_UNKNOWN'] == 1
    assert result['usage']['unknown_usage_attempts'] == 1


def test_invalid_and_truncated_outputs_hit_persistent_cap(q):
    calls, result = call(q, [response({'text': 'partial'}, 'length'), 'not JSON', response({'wrong': 3})])
    assert len(calls) == 3
    assert result['jobs']['FAILED'] == 1
    assert len(call(m.Queue(q.directory), [])[0]) == 0


def test_rejected_review_is_preserved(q):
    _, result = call(q, [response({'text': 'candidate'}), response({'passed': False, 'issues': ['missing condition']})])
    assert result['jobs']['NEEDS_REVIEW'] == 1
    assert len(call(q, [])[0]) == 0


def test_exclusive_runner(q):
    with m.exclusive(q.directory):
        with pytest.raises(RuntimeError, match='owns'):
            call(q, [])


def test_frozen_identity_tamper_refused(q):
    with q.connect() as c:
        d = dict(q.identity, model='changed')
        c.execute('update meta set value=? where key="identity"', (m.packed(d),))
    with pytest.raises(ValueError, match='identity hash'):
        m.Queue(q.directory)


def test_input_tamper_refused(q):
    with q.connect() as c:
        c.execute('update job set input_json=? where id="a"', ('{"tampered":true}',))
    with pytest.raises(ValueError, match='Input hash'):
        call(q, [])


def test_schema_remote_ref_is_offline(q):
    with pytest.raises(ValueError, match='local schema'):
        m.check_schema({'$ref': 'https://example.com/schema'})


def test_server_failure_stops_and_keeps_candidate(q):
    calls, result = call(q, [response({'text': 'candidate'}), RuntimeError('HTTP_STATUS_503')])
    assert len(calls) == 2
    with q.connect() as c:
        row = c.execute('select stage,candidate from job where id="a"').fetchone()
        assert row['stage'] == 'review' and row['candidate']
        c.execute('update job set next_at=0 where id="a"')
    calls, _ = call(q, [response({'passed': True, 'issues': []})])
    assert len(calls) == 1


def test_global_budget_under_concurrency(q):
    with q.connect() as c:
        for i in range(20):
            c.execute('insert into job(id,document_id,input_json,input_hash,stage,state) values(?,?,?,?,?,?)',
                      (str(i), 'd', '{}', m.digest({}), 'extract', 'READY'))
    calls, result = call(q, [response({'text': 'x'})] * 3, max_calls=3, workers=4)
    assert len(calls) == 3
    assert sum(result['attempts'].values()) == 3


def test_export_is_candidate_only_and_preserves_inputs(q, tmp_path):
    call(q, [response({'text': 'candidate'}), response({'passed': True, 'issues': []})])
    p = tmp_path / 'out.jsonl'
    q.export(p)
    rows = [json.loads(s) for s in p.read_text().splitlines()]
    assert rows[0]['production_approved'] is False
    assert rows[1]['input_hash']
    with pytest.raises(FileExistsError):
        q.export(p)


def test_prepare_failure_does_not_publish_queue(tmp_path):
    src = tmp_path / 'bad.sqlite'
    with sqlite3.connect(src) as c:
        c.execute('create table authoring_job(job_id text,document_id text,state text,input_json text)')
        c.execute('insert into authoring_job values("a","d","UNEXPECTED","{}")')
    target = tmp_path / 'queue'
    with pytest.raises(ValueError, match='Unknown source state'):
        m.prepare(target, src, 'fixture', SCHEMA, model='m', revision='r', endpoint='http://localhost')
    assert not (target / 'queue.sqlite').exists()


def test_graceful_stop_does_not_start_next_stage(q):
    stop = threading.Event()
    def factory():
        def provider(_):
            stop.set()
            return response({'text': 'saved before stop'})
        return provider
    result = m.run(q, execute=True, max_calls=10, provider_factory=factory, stop=stop)
    assert result['attempts'] == {'VALIDATED': 1}
    assert result['jobs']['READY'] == 1


def test_explicit_retry_preserves_history_and_completed_extract(q):
    call(q, [response({'text': 'candidate'}), 'bad', 'bad', 'bad'])
    q.retry('a', 'Transient malformed output; retry same frozen input', 1)
    calls, result = call(q, [response({'passed': True, 'issues': []})])
    assert len(calls) == 1
    assert calls[0]['response_format']['json_schema']['name'] == 'authoring_review'
    assert result['attempts']['INVALID'] == 3
    assert result['attempts']['VALIDATED'] == 2
    with pytest.raises(ValueError, match='Only FAILED'):
        q.retry('a', 'cannot rerun completed job')


def test_real_exit_after_receipt_commit(q):
    code = '''import runpy,sys,os
m=runpy.run_path(sys.argv[1]); q=m['Queue'](sys.argv[2])
with m['exclusive'](q.directory):
 a=q.claim(); q.received(a,sys.argv[3],0.1); os._exit(92)
'''
    proc = subprocess.run([sys.executable, '-c', code, str(SCRIPT), str(q.directory), response({'text': 'durable'})])
    assert proc.returncode == 92
    calls, result = call(q, [response({'passed': True, 'issues': []})])
    assert len(calls) == 1
    assert result['attempts'] == {'VALIDATED': 2}


def test_transport_disables_redirects_proxy_and_discovery(q, monkeypatch):
    import requests
    captures = []
    class Session:
        headers = {}
        trust_env = True
        def post(self, url, **kwargs):
            captures.append((url, kwargs, self.trust_env))
            class Result:
                status_code = 200
                content = b'{}'
            return Result()
    monkeypatch.setattr(requests, 'Session', Session)
    p = m.HTTPProvider(q.identity, 10)
    p({'model': 'fixture-model'})
    assert len(captures) == 1
    url, kw, trust = captures[0]
    assert url == 'http://localhost:8000/v1/chat/completions'
    assert kw['allow_redirects'] is False and trust is False


def test_changed_revision_blocks_before_network(q, monkeypatch):
    monkeypatch.setenv('GENOS_LLM_REVISION', 'another-revision')
    with pytest.raises(ValueError, match='REVISION'):
        m.run(q, execute=True, max_calls=1)
    assert q.status()['attempts'] == {}


def test_http_error_body_is_durable(q):
    _, result = call(q, [m.TransportError(503, '{"error":"server unavailable"}')])
    assert result['attempts']['TRANSPORT_ERROR'] == 1
    with q.connect() as c:
        row = c.execute('select response,response_hash from attempt').fetchone()
        assert json.loads(row['response'])['error'] == 'server unavailable'
        assert row['response_hash']
