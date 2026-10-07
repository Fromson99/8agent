"""HTTP error response evidence is visible without credentials or request echoes."""
import asyncio
import importlib.util
import io
import json
from pathlib import Path
import urllib.error

import pytest

ROOT = Path(__file__).resolve().parents[2]


def workflow():
    spec = importlib.util.spec_from_file_location('http_origin_workflow', ROOT / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('socket', [False, True])
def test_http_500_exposes_error_origin_and_retains_single_send(monkeypatch, socket):
    module = workflow()
    monkeypatch.setattr(module, '_settings', lambda: ('http://fixture.invalid/json', 'fixture-private-token', 2100))
    monkeypatch.setenv('GENOS_CODESERVING_TOKEN', 'fixture-private-token')
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI', 'socketio-final')
    calls = []
    payload = json.dumps({'error': {'type': 'TimeoutError', 'message': 'aiohttp upstream timed out'}}, ensure_ascii=False).encode()
    def send(request, timeout):
        calls.append((request.full_url, timeout))
        raise urllib.error.HTTPError(request.full_url, 500, 'failed',
            {'Server': 'uvicorn', 'Set-Cookie': 'fixture-private-token'}, io.BytesIO(payload))
    monkeypatch.setattr(module.urllib.request, 'urlopen', send)
    data = {'question': 'synthetic public question'}
    if socket: data['socketIOClientId'] = 'synthetic-socket'
    result = asyncio.run(module.run(data))
    assert result['failure_kind'] == 'http_error' and result['http_status'] == 500
    evidence = result['http_error_diagnostics']
    assert evidence['response_headers'] == {'server': 'uvicorn'}
    assert evidence['error_fields']['type'] == 'TimeoutError'
    assert evidence['error_body_excerpt'] == 'aiohttp upstream timed out'
    assert evidence['socket_timeout_seconds'] == 2100
    assert {'aiohttp', 'timed out', 'upstream'} <= set(evidence['error_hints'])
    assert len(calls) == 1 and calls[0][1] == 2100
    assert 'fixture-private-token' not in json.dumps(result)


def test_request_echo_credentials_and_non_error_fields_are_omitted(monkeypatch):
    module = workflow()
    monkeypatch.setenv('GENOS_LLM_KEY', 'private-model-key')
    question = 'internal example question'
    payload = json.dumps({'error': {'message': 'TimeoutError Authorization: Bearer private-model-key'},
                          'data': {'question': question, 'answer': 'private source text'}}).encode()
    exc = urllib.error.HTTPError('http://fixture', 500, 'failed', {}, None)
    evidence = module._http_error_diagnostics(exc, payload, question)
    text = json.dumps(evidence)
    assert 'private-model-key' not in text and question not in text and 'private source text' not in text
    assert 'TimeoutError' in evidence['error_body_excerpt']


def test_plain_body_question_and_credentials_are_redacted(monkeypatch):
    module = workflow()
    monkeypatch.setenv('GENOS_CODESERVING_TOKEN', 'private-serving-token')
    question = 'internal example question'
    payload = f'upstream timeout; {question}; Bearer private-serving-token'.encode()
    exc = urllib.error.HTTPError('http://fixture', 500, 'failed', {}, None)
    evidence = module._http_error_diagnostics(exc, payload, question)
    assert question not in evidence['error_body_excerpt']
    assert 'private-serving-token' not in json.dumps(evidence)
    assert evidence['body_format'] == 'text' and 'timeout' in evidence['error_hints']


def test_response_body_capture_is_bounded(monkeypatch):
    module = workflow()
    monkeypatch.setattr(module, '_settings', lambda: ('http://fixture/json', 'fixture', 2100))
    def fail(*args, **kwargs):
        raise urllib.error.HTTPError('http://fixture', 500, 'failed', {}, io.BytesIO(b'upstream timeout ' + b'x' * 20000))
    monkeypatch.setattr(module.urllib.request, 'urlopen', fail)
    result = asyncio.run(module.run({'question': 'synthetic'}))
    evidence = result['http_error_diagnostics']
    assert evidence['captured_body_bytes'] == 16384 and evidence['capture_limit_reached']
    assert len(evidence['error_body_excerpt']) <= 1500


def test_existing_service_error_text_redacts_credentials(monkeypatch):
    module = workflow()
    monkeypatch.setattr(module, '_settings', lambda: ('http://fixture/json', 'fixture', 2100))
    monkeypatch.setenv('GENOS_LLM_KEY', 'private-model-key')
    payload = json.dumps({'status': 500, 'body': {'code': 'SOURCE_TOOL_ERROR',
        'detail': 'stage=source.fetch Authorization: Bearer private-model-key'}}).encode()
    def fail(*args, **kwargs):
        raise urllib.error.HTTPError('http://fixture', 500, 'failed', {}, io.BytesIO(payload))
    monkeypatch.setattr(module.urllib.request, 'urlopen', fail)
    result = asyncio.run(module.run({'question': 'synthetic'}))
    assert 'SOURCE_TOOL_ERROR' in result['text'] and 'stage=source.fetch' in result['text']
    assert 'private-model-key' not in json.dumps(result)
