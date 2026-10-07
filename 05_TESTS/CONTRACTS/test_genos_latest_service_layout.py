"""GENOS latest service/service.py entry shares the actual v6 runtime."""
import asyncio
import importlib
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]

def test_package_and_nested_import_share_cache_and_function_globals(monkeypatch):
    monkeypatch.setenv('GENOS_AUTO_WARMUP', '0')
    sys.modules.pop('service', None)
    root = importlib.import_module('service')
    nested = importlib.import_module('service.service')
    assert root is nested
    assert root._ROOT == ROOT
    assert Path(root.__file__) == ROOT / 'service.py'
    assert root.service.__globals__ is root.__dict__

def test_platform_file_loader_preserves_root_and_lazy_ping(monkeypatch):
    monkeypatch.setenv('GENOS_AUTO_WARMUP', '0')
    spec = importlib.util.spec_from_file_location('platform_file_fixture', ROOT / 'service/service.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._runtime._ROOT == ROOT
    out = asyncio.run(module.service({}, {'API_TYPE': 'PING'}))
    assert out['ok'] is True

def test_nested_service_reaches_real_unified_v6(unified, monkeypatch):
    client, send, transport, principal, runtime = unified
    module = importlib.import_module('service.service')
    monkeypatch.setattr(module, '_bootstrap_application', lambda: client.app)
    out = asyncio.run(module.service({}, {
        'API_TYPE': 'LEGAL_AGENT', 'question': '모의승인규정 제1조의 승인 대상은?',
        'session_id': 's', 'request_id': 'nested-entry-v6',
        'memory_authorization': {'issued_at': 1, 'signature': 'fixture'},
    }))
    assert out['status'] == 200, out
    assert out['body']['answer']['text']

# Reuse the existing v6 model/data fixture; no external model calls.
from test_unified_legal_agent import unified
from test_structure_first_search import structured_generation
