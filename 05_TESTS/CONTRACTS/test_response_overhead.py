"""Functional overhead-removal contracts; no model calls or speed benchmark."""
import hashlib
import io
import json
import logging
import os
import threading
from contextlib import closing

import pytest
from semantic_runtime import observability as obs
from semantic_runtime.request_report import capture_events, _LiveLog, _scrub
from semantic_runtime.navigation_agent import _verified_json
from semantic_runtime.term_index import cached_serving_index
from semantic_runtime.storage import Store
from semantic_runtime.contracts import Contracts, sha
from test_document_navigation_serving import generation


def test_disabled_details_do_not_sanitize_and_errors_still_reach_capture(monkeypatch):
    logger = obs.get_logger('quiet-contract')
    monkeypatch.setattr(logger, 'level', logging.INFO)
    scans = []
    monkeypatch.setattr(obs, '_secret_values', lambda: scans.append(1) or ())
    with capture_events('quiet') as events, obs.context(request_id='quiet'):
        with obs.step(logger, 'successful.work'):
            obs.event(logger, 'catalogue.cache.hit', cache_hit=True)
        assert events == [] and scans == []
        with pytest.raises(ValueError):
            with obs.step(logger, 'failed.work'):
                raise ValueError('fixture')
    assert [event['event'] for event in events] == ['step.failed']
    assert events[0]['exc_type'] == 'ValueError'


def test_all_output_handlers_share_one_safe_snapshot_and_new_event_sees_rotation(monkeypatch):
    first = 'credential-fixture-first'
    second = 'credential-fixture-second'
    monkeypatch.setenv('GENOS_LLM_KEY', first)
    scans = []
    collect = obs._secret_values
    monkeypatch.setattr(obs, '_secret_values', lambda: scans.append(1) or collect())
    stream = io.StringIO()
    target = logging.StreamHandler(stream)
    target.setFormatter(obs.JsonFormatter())
    writer = obs.AsyncHandler(target)
    capture_logger = logging.getLogger(obs.ROOT)
    capture_logger.addHandler(writer)
    logger = obs.get_logger('snapshot-contract')
    try:
        with capture_events('snapshot') as events, obs.context(request_id='snapshot'):
            obs.event(logger, 'fixture.first', detail=first, rows=[{'detail': first, 'api_key': first}])
            monkeypatch.setenv('GENOS_LLM_KEY', second)
            obs.event(logger, 'fixture.second', detail=second)
        assert writer.drain(2)
        assert len(scans) == 2
        assert first not in stream.getvalue() and second not in stream.getvalue()
        assert first not in json.dumps(events) and second not in json.dumps(events)
        assert events[0]['rows'] == [{'detail': '[REDACTED]'}]
    finally:
        capture_logger.removeHandler(writer)
        writer.close(); writer.worker.join(2)


def test_report_redaction_scans_environment_once_per_tree(monkeypatch):
    monkeypatch.setenv('GENOS_LLM_KEY', 'report-fixture-secret')
    scans=[]; collect=obs._secret_values
    monkeypatch.setattr(obs, '_secret_values', lambda: scans.append(1) or collect())
    result=_scrub({'items':[{'text':'report-fixture-secret','answer':'report-fixture-secret'}]*20})
    assert scans == [1]
    assert 'report-fixture-secret' not in json.dumps(result)


def test_question_trace_does_not_wait_for_shared_writer_and_still_redacts(monkeypatch):
    monkeypatch.setenv('GENOS_LLM_KEY', 'live-fixture-secret')
    entered, release = threading.Event(), threading.Event()
    class Blocked(io.StringIO):
        def write(self, value):
            entered.set()
            assert release.wait(3)
            return super().write(value)
    stream=Blocked(); handler=_LiveLog('queued-question', stream)
    try:
        handler.queue_detail('RAG INPUT / QUESTION', {'question':'Q live-fixture-secret'})
        assert entered.wait(2)
        handler.queue_detail('SECOND DETAIL', {'question':'second'})
        assert handler.writer.queue  # caller returned while writer is blocked
        release.set(); assert handler.writer.drain(2)
        assert 'RAG INPUT / QUESTION' in stream.getvalue()
        assert 'second' in stream.getvalue()
        assert 'live-fixture-secret' not in stream.getvalue()
    finally:
        release.set(); handler.writer.close(); handler.writer.worker.join(2)


def test_pinned_receipt_reuse_preserves_mutation_isolation_and_rejects_drift(tmp_path, monkeypatch):
    path=tmp_path/'receipt.json'; path.write_text('{"binding":{"version":1}}')
    expected=sha(path)
    original=type(path).read_bytes; reads=[]
    def read(p):
        if p == path: reads.append(1)
        return original(p)
    monkeypatch.setattr(type(path), 'read_bytes', read)
    value=_verified_json(path, expected); value['binding']['version']=999
    assert _verified_json(path, expected)['binding']['version'] == 1
    assert reads == [1]
    with pytest.raises(ValueError, match='receipt mismatch'):
        _verified_json(path, '0'*64)
    path.write_text('{"binding":{"version":2}}')
    state=path.stat()
    os.utime(path, ns=(state.st_atime_ns, state.st_mtime_ns+1000000))
    with pytest.raises(ValueError, match='receipt mismatch'):
        _verified_json(path, expected)


def test_index_reuse_never_bypasses_new_manifest_pin(generation, monkeypatch):
    import semantic_runtime.term_index as module
    with closing(Store(generation)) as store:
        path=generation/'navigation'; expected=sha(path/'manifest.json')
        original=module.sha; reads=[]
        def counted(p):
            reads.append(str(p))
            return original(p)
        monkeypatch.setattr(module, 'sha', counted)
        a=cached_serving_index(path, store, expected_manifest_sha256=expected)
        reads.clear()
        assert cached_serving_index(path, store, expected_manifest_sha256=expected) is a
        assert reads == []
        with pytest.raises(ValueError, match='manifest mismatch'):
            cached_serving_index(path, store, expected_manifest_sha256='0'*64)
        manifest=path/'manifest.json'
        manifest.write_bytes(manifest.read_bytes()+b' ')
        with pytest.raises(ValueError, match='manifest mismatch'):
            cached_serving_index(path, store, expected_manifest_sha256=expected)


def test_reused_validator_still_rejects_invalid_requests():
    contracts=Contracts('.')
    valid={'question':'fixture','document_ids':[],'use_llm':False}
    assert contracts.validate_port('runtime.request', valid) is valid
    with pytest.raises(Exception) as error:
        contracts.validate_port('runtime.request', {**valid, 'question':None})
    from jsonschema import ValidationError
    assert isinstance(error.value, ValidationError)
    assert contracts.validate_port('runtime.request', valid) is valid


def test_stage_keeps_code_binding_when_reusing_cached_proofs(tmp_path):
    from types import SimpleNamespace
    from semantic_runtime.stage_runner import StageRunner
    code=tmp_path/'engine.py'
    code.write_text('def run(inputs, parameters, context):\n    return {"out": inputs["value"]}\n')
    schema=tmp_path/'00_SYSTEM/schema.json'; schema.parent.mkdir()
    schema.write_text('{"type":"integer"}')
    manifest=tmp_path/'engine.json'
    manifest.write_text(json.dumps({'kind':'TEST','inputs':{'value':'number'},'outputs':{'out':'number'},
        'files':{'engine.py':sha(code)},'entrypoint':{'path':'engine.py','function':'run'},
        'parameters_schema':{'type':'object'}}))
    config={'contracts':{'number':{'schema_path':'00_SYSTEM/schema.json','schema_sha256':sha(schema)}},
        'engines':{'fixture':{'manifest':'engine.json','sha256':sha(manifest)}},
        'slots':{'fixture':{'kind':'TEST','inputs':{'value':'number'},'outputs':{'out':'number'}}}}
    (tmp_path/'00_SYSTEM/PIPELINE.json').write_text(json.dumps(config))
    runner=StageRunner(SimpleNamespace(contracts=Contracts(tmp_path)))
    step={'id':'fixture','engine':'fixture','slot':'fixture','bindings':{'value':'input'},'parameters':{}}
    assert runner.execute(step,{'input':1}) == {'out':1}
    assert runner.execute(step,{'input':2}) == {'out':2}
    code.write_text('def run(inputs, parameters, context):\n    return {"out": 999}\n')
    with pytest.raises(ValueError, match='engine code hash mismatch'):
        runner.execute(step,{'input':3})


_REPORT_VARIANTS = list((__import__('pathlib').Path(__file__).resolve().parents[2] /
    '08_DEPLOYMENT/GENOS/patches/response_overhead_20260928_r1/variants').glob(
        '*/02_BACKEND/semantic_runtime/request_report.py'))

@pytest.mark.parametrize('variant', _REPORT_VARIANTS, ids=lambda p:p.parts[-4][:12])
def test_installed_log_versions_keep_answer_and_audit_when_open_stalls(variant, tmp_path, monkeypatch):
    import importlib.util
    from datetime import datetime, timezone
    from contextlib import contextmanager
    module_name='semantic_runtime._overhead_variant_'+variant.parts[-4][:12]
    spec=importlib.util.spec_from_file_location(module_name, variant)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    entered,release=threading.Event(),threading.Event()
    original=module.live_log
    @contextmanager
    def blocked(*args,**kwargs):
        entered.set();assert release.wait(3)
        with original(*args,**kwargs) as opened:yield opened
    monkeypatch.setattr(module, 'live_log', blocked)
    events=[{'event':'request.started','ts':datetime.now(timezone.utc).isoformat(),
             'level':'INFO','logger':'genos.test','request_id':'variant-test'}]
    result={'status':200,'body':{'run_id':'a'*32,'answer':{'text':'fixture completed answer'}}}
    try:
        with module.DeferredReport(tmp_path/'shared',tmp_path/'runtime',request_id='variant-test',
                api_type='LEGAL_AGENT',request={'question':'fixture'},events=events) as report:
            assert entered.wait(2)
            report.complete(result)
        assert report.result == result and not report._live_ready.is_set()
    finally:
        release.set();module._FINALIZER_QUEUE.join()
    saved=[json.loads(path.read_text()) for path in (tmp_path/'shared').rglob('*.json')]
    assert any(item.get('result') == result for item in saved)
    assert report.handler.stream.closed
    assert report.handler.run_id == 'a'*32
