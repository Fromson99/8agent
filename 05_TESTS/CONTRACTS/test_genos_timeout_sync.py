"""Timeout propagation and error boundaries; synthetic calls with a virtual clock."""
import asyncio
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import urllib.error

import pytest

ROOT = Path(__file__).resolve().parents[2]


def workflow():
    spec = importlib.util.spec_from_file_location('timeout_workflow', ROOT / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_profiles_and_all_consumers_have_thirty_minute_budget():
    pipeline = json.loads((ROOT / '00_SYSTEM/PIPELINE.json').read_text())
    checked = 0
    for profile in pipeline['profiles'].values():
        for node in profile.get('nodes', []):
            term = node.get('parameters', {}).get('term_agent', {})
            if 'limits' in term:
                assert term['limits']['wall_seconds'] == 1800
            binding = term.get('legal_agent', {}).get('profile')
            if binding:
                raw = (ROOT / binding['path']).read_bytes()
                assert hashlib.sha256(raw).hexdigest() == binding['sha256']
                assert json.loads(raw)['wall_seconds'] == 1800
                checked += 1
    assert checked >= 5


@pytest.mark.parametrize('operation', [{'API_TYPE': 'WORKFLOW_SETTINGS'}, {'question': 'WORKFLOW_SETTINGS'}])
@pytest.mark.parametrize('timeout', [600, 2100])
def test_settings_reports_actual_configuration_without_network_or_secrets(monkeypatch, operation, timeout):
    module = workflow()
    monkeypatch.setenv('GENOS_BASE_URL', 'http://fixture.invalid')
    monkeypatch.setenv('GENOS_CODESERVING_ID', 'fixture')
    monkeypatch.setenv('GENOS_CODESERVING_TOKEN', 'private-fixture-token')
    monkeypatch.setenv('GENOS_CODESERVING_TIMEOUT_SECONDS', str(timeout))
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio-final')
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('No network for settings'))
    result = asyncio.run(module.run(operation))
    assert result['answer_status'] == 'diagnostics'
    settings = result['workflow_settings']
    assert settings['json_socket_timeout_seconds'] == settings['stream_socket_timeout_seconds'] == timeout
    assert settings['route_with_socket_id'] == '/stream'
    assert settings['route_without_socket_id'] == '/stream'
    assert 'private-fixture-token' not in json.dumps(result)
    assert 'fixture.invalid' not in json.dumps(result)


@pytest.mark.parametrize('socket', [False, True])
@pytest.mark.parametrize('timeout', [600, 2100])
def test_http_500_at_three_hundred_seconds_is_distinct_from_client_timeout(monkeypatch, socket, timeout, capsys):
    module = workflow()
    monkeypatch.setattr(module, '_settings', lambda: ('http://fixture.invalid/json', 'fixture-token', timeout))
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio-final')
    clock = [100.0]
    monkeypatch.setattr(module.time, 'perf_counter', lambda: clock[0])
    calls = []
    def send(request, timeout):
        calls.append((request.full_url, timeout))
        clock[0] = 400.0
        raise urllib.error.HTTPError(request.full_url, 500, 'synthetic upstream timeout', {},
                                     io.BytesIO(b'{"detail":"synthetic timeout"}'))
    monkeypatch.setattr(module.urllib.request, 'urlopen', send)
    data = {'question': 'synthetic'}
    if socket:
        data['socketIOClientId'] = 'synthetic-socket'
    result = asyncio.run(module.run(data))
    assert len(calls) == 1
    assert calls[0][1] == timeout
    assert calls[0][0].endswith('/stream')
    assert result['answer_status'] == 'failed' and result['http_status'] == 500
    assert result['failure_kind'] == 'http_error' and result['tm_total'] == 300
    assert result['workflow_revision'] == 'sse-transport-20260928-r1'
    assert '코드서빙 응답 500' in result['text']
    logs = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert any(row.get('http_status') == 500 and row.get('duration_ms') == 300000 for row in logs)


def test_client_timeout_returns_its_own_error_class(monkeypatch):
    module = workflow()
    monkeypatch.setattr(module, '_settings', lambda: ('http://fixture/json', 'fixture', 2100))
    def timeout(*args, **kwargs):
        raise TimeoutError('synthetic socket wait')
    monkeypatch.setattr(module.urllib.request, 'urlopen', timeout)
    result = asyncio.run(module.run({'question': 'synthetic'}))
    assert result['failure_kind'] == 'client_exception'
    assert result['error_type'] == 'TimeoutError'
    assert 'http_status' not in result
