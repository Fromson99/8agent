"""HTTP startup and probes must be independent of data/model initialization."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import httpx

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_app_import_with_generation_does_not_start_resource_initialization():
    code = '''
import importlib.util, json, sys, threading
started = []
threading.Thread.start = lambda self: started.append(self.name)
spec = importlib.util.spec_from_file_location('startup_fixture', '08_DEPLOYMENT/GENOS/stream_app.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps({'service_imported': 'service' in sys.modules, 'threads': started}))
'''
    env = {**os.environ, 'GENOS_GENERATION': '/synthetic/unavailable-generation',
           'GENOS_AUTO_WARMUP': '1'}
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env,
                            text=True, capture_output=True, timeout=10, check=True)
    facts = json.loads(result.stdout.splitlines()[-1])
    assert not facts['service_imported']
    assert 'genos-resource-warmup' not in facts['threads']


def test_http_health_and_sse_probe_do_not_load_backend(monkeypatch):
    app = load('startup_probes', '08_DEPLOYMENT/GENOS/stream_app.py')
    async def forbidden(*args):
        raise AssertionError('HTTP readiness must not initialize the backend')
    monkeypatch.setattr(app, 'service', forbidden)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app),
                                    base_url='http://synthetic') as client:
            for path in ('/', '/health'):
                response = await client.get(path)
                assert response.status_code == 200
                assert response.json()['readiness_scope'] == 'http'
                assert response.json()['data_readiness'] == 'NOT_CHECKED'
            probe = await client.post('/stream', json={'API_TYPE': 'SSE_CHECK'})
            assert probe.status_code == 200 and '"sse_ready":true' in probe.text
    asyncio.run(check())


def test_start_command_does_not_inherit_multiple_workers(monkeypatch):
    import uvicorn
    start = load('single_worker_start', '08_DEPLOYMENT/GENOS/start_sse.py')
    monkeypatch.setenv('WEB_CONCURRENCY', '4')
    monkeypatch.setattr(start, 'dependencies', lambda: {'fastapi': 'fixture', 'uvicorn': 'fixture'})
    called = []
    monkeypatch.setattr(uvicorn, 'run', lambda app, **kwargs: called.append((app, kwargs)))
    monkeypatch.chdir(ROOT)
    start.main(['--port', '8017'])
    assert len(called) == 1
    assert uvicorn.Config(called[0][0], **called[0][1]).workers == 1


def test_deferred_backend_keeps_json_single_execution(monkeypatch):
    from types import SimpleNamespace
    calls = []
    async def backend(config, data):
        calls.append(data)
        return {'status': 200, 'body': {'answer': {'text': 'synthetic answer'}}}
    monkeypatch.setitem(sys.modules, 'service', SimpleNamespace(service=backend))
    app = load('deferred_backend', '08_DEPLOYMENT/GENOS/stream_app.py')
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app),
                                    base_url='http://synthetic') as client:
            response = await client.post('/json', json={'API_TYPE': 'LEGAL_AGENT', 'question': 'synthetic'})
            assert response.json()['body']['answer']['text'] == 'synthetic answer'
    asyncio.run(check())
    assert len(calls) == 1
