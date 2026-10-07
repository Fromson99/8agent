"""Warmup starts once and returns while resource verification is still running."""
import asyncio
import threading
import time
import importlib.util
from pathlib import Path


def test_explicit_generation_starts_one_background_warmup_on_worker_import(monkeypatch):
    import service
    started = []
    monkeypatch.setenv('GENOS_GENERATION', '/fixture/generation')
    monkeypatch.delenv('GENOS_AUTO_WARMUP', raising=False)
    monkeypatch.setattr(threading.Thread, 'start', lambda self: started.append(self.name))
    spec = importlib.util.spec_from_file_location('service_auto_warmup_fixture', Path(service.__file__))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert started == ['genos-resource-warmup']
    assert module._WARMUP_STATE['state'] == 'RUNNING'


def test_warmup_is_background_deduplicated_and_status_never_starts_it(monkeypatch):
    import service
    entered, release = threading.Event(), threading.Event()
    calls = []

    def load():
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return {'generation_path': '/synthetic/generation', 'document_count': 2}

    monkeypatch.setattr(service, '_WARMUP_STATE', {'state': 'NOT_STARTED'})
    monkeypatch.setattr(service, '_warm_resources', load)
    # Control calls must not touch even an unusable NFS reporting path.
    monkeypatch.setenv('GENOS_SHARED_LOG_DIR', '/invalid/nfs/for/test')
    status = asyncio.run(service.service({}, {'API_TYPE': 'WARMUP_STATUS'}))
    assert status['body']['state'] == 'NOT_STARTED' and not calls
    try:
        first = asyncio.run(service.service({}, {'API_TYPE': 'WARMUP'}))
        assert entered.wait(2)
        assert first['status'] == 202
        second = asyncio.run(service.service({}, {'API_TYPE': 'WARMUP'}))
        assert second['body']['state'] == 'RUNNING' and calls == [1]
    finally:
        release.set()
    deadline = time.monotonic() + 3
    while service._WARMUP_STATE['state'] == 'RUNNING' and time.monotonic() < deadline:
        time.sleep(.01)
    final = asyncio.run(service.service({}, {'API_TYPE': 'WARMUP_STATUS'}))
    assert final['body']['state'] == 'READY'
    assert final['body']['generation_path'] == '/synthetic/generation'
    assert final['body']['process_local'] is True


def test_warmup_failure_is_visible_without_internal_error_text(monkeypatch):
    import service

    def fail():
        raise ValueError('private failure text')

    monkeypatch.setattr(service, '_WARMUP_STATE', {'state': 'RUNNING'})
    monkeypatch.setattr(service, '_warm_resources', fail)
    service._run_warmup()
    result = service._warmup()
    assert result['body']['state'] == 'FAILED'
    assert result['body']['error_type'] == 'ValueError'
    assert 'private failure text' not in str(result)
