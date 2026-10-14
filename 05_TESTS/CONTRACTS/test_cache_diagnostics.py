"""Serving inspection observes existing state; never runs SQL or leaks inputs."""
import asyncio
import ast
import importlib.util
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

from semantic_runtime import cache_diagnostics as diagnostic
from semantic_runtime import resident_data, runtime_cache

ROOT = Path(__file__).resolve().parents[2]


def globals_for(tmp_path):
    entry = tmp_path / 'service.py'
    entry.write_text('# known serving code\n')
    return {'_ROOT': tmp_path, '__file__': str(entry), '_PROCESS_INSTANCE_ID': 'worker-fixed',
            '_warmup': lambda: {'body': {'state': 'READY', 'worker_id': 'worker-fixed'}}}


def test_inspection_does_not_load_new_cache_or_model_and_omits_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv('GENOS_LLM_KEY', 'credential-do-not-return')
    monkeypatch.setenv('GENOS_RESIDENT_DATA', 'off')
    pool = resident_data.ResidentPool(mode='off')
    monkeypatch.setattr(resident_data, 'POOL', pool)
    monkeypatch.setattr(pool, 'connect', lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not open SQL')))
    before = set(sys.modules)
    report = diagnostic.collect(globals_for(tmp_path))
    assert report['worker']['worker_id'] == 'worker-fixed'
    assert report['resident_pools'][0]['effective_mode'] == 'off'
    assert report['resident_pools'][0]['entry_count'] == 0
    assert set(sys.modules) == before
    assert 'credential-do-not-return' not in json.dumps(report)
    assert 'GENOS_LLM_KEY' not in report['environment']


def test_inspection_observes_retained_original_without_reading_sqlite(tmp_path):
    path = tmp_path / 'units.sqlite'
    path.write_bytes(b'dataset-placeholder')
    signature = resident_data.signature(path)
    pool = resident_data.ResidentPool(mode='local')
    pool.entries[(str(path), signature, 'pinned-sha')] = {'storage': 'local'}
    pool.local_bytes = len(b'dataset-placeholder')
    report = diagnostic.resident_snapshot(pool)
    assert report['entries'][0]['original_signature_unchanged'] is True
    assert report['entries'][0]['storage'] == 'local'
    path.write_bytes(b'changed')
    assert diagnostic.resident_snapshot(pool)['entries'][0]['original_signature_unchanged'] is False


def test_result_keys_are_content_free_and_overflow_is_visible():
    cache = runtime_cache.ProcessCache()
    namespace = ('/data', (), 'generation', 'source-sha', 'nav-sha', 'index-sha', 'schema')
    cache.get_or_build(('matches', namespace, ('PRIVATE-QUERY',), frozenset({'PRIVATE-SOURCE'}), 50000),
                       lambda: None, kind='matches')
    report = diagnostic.result_snapshot(cache)
    raw = json.dumps(report)
    assert 'PRIVATE-QUERY' not in raw and 'PRIVATE-SOURCE' not in raw
    assert report['recent_matches'][0]['overflow_marker'] is True
    assert report['recent_matches'][0]['index_sha256'] == 'index-sha'
    assert report['lookup_hit_count'] == 'NOT_INSTRUMENTED'


def test_service_hook_bypasses_ad_and_is_the_same_process(tmp_path):
    tree = ast.parse((ROOT / 'service.py').read_text())
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'service')
    namespace = {'asyncio': asyncio, 'Any': object, **globals_for(tmp_path)}
    # Only the real entry function is executed; production module bootstrap must not run.
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'service.py', 'exec'), namespace)
    report = asyncio.run(namespace['service']({}, {'API_TYPE': 'CACHE_DIAGNOSTICS'}))
    assert report['status'] == 200
    assert report['body']['worker']['worker_id'] == 'worker-fixed'
    assert not (tmp_path / '90_RUNTIME').exists()


def load_script(relative):
    spec = importlib.util.spec_from_file_location('test_' + Path(relative).stem, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_workflow_keeps_server_identity_and_missing_inspector_is_unconfirmed(monkeypatch):
    workflow = load_script('08_DEPLOYMENT/GENOS/workflow/genos_cache_diagnostics.py')
    def call(operation):
        if operation == 'CACHE_DIAGNOSTICS':
            raise ValueError('SECRET-GATEWAY-BODY')
        return {'state': 'READY', 'worker_id': 'worker-from-server'}, 1
    monkeypatch.setattr(workflow, 'call', call)
    report = workflow.run({'question': 'PRIVATE-QUESTION', 'token': 'PRIVATE-TOKEN'})
    assert report['observed_worker_ids'] == ['worker-from-server']
    assert report['live_cache_observed'] is False
    encoded = json.dumps(report)
    assert all(value not in encoded for value in ('SECRET-GATEWAY-BODY', 'PRIVATE-QUESTION', 'PRIVATE-TOKEN'))


def test_log_summary_does_not_double_count_http_and_attempt_and_redacts_contents():
    module = load_script('06_TOOLS/OFFLINE/genos_wait_diagnose.py')
    lines = [
        '2026-10-08T06:46:09 INFO model_http.finished duration_ms=43140 http_status=200 request_id=r\n',
        '2026-10-08T06:46:09 INFO model.attempt.received duration_ms=43157 request_id=r cached_tokens=null completion_tokens=325\n',
        '2026-10-08T06:47:22 INFO model_http.finished duration_ms=72822 http_status=200 request_id=r\n',
        '2026-10-08T06:47:22 INFO model.attempt.received duration_ms=72837 request_id=r cached_tokens=null completion_tokens=600\n',
        'PRIVATE QUESTION and ANSWER\n',
    ]
    report = module.summarize(lines + lines[:1])
    row = report['requests'][0]
    assert row['sum_model_http_ms'] == 115962
    assert row['search_timing_available'] is False
    assert row['max_request_return_ms'] is None
    assert row['model_attempt_receipts'][0]['cached_tokens'] is None
    assert 'PRIVATE' not in json.dumps(report)


def test_cold_inspection_does_not_import_resident_pool(tmp_path, monkeypatch):
    monkeypatch.delitem(sys.modules, 'semantic_runtime.resident_data')
    monkeypatch.delitem(sys.modules, 'semantic_runtime.runtime_cache')
    report = diagnostic.collect(globals_for(tmp_path))
    assert report['resident_pools'] == []
    assert report['result_caches'] == []
    assert 'semantic_runtime.resident_data' not in sys.modules
