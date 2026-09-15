"""Offline field-repair contract: only persist after an actual non-empty reply."""
import json
import sys
import types
import zipfile
from pathlib import Path

import httpx
import pytest
import requests

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM/WORKSPACE.json').is_file())
SCRIPT = ROOT / 'genos_llm_reply_fix.sh'


@pytest.mark.parametrize('transport', ['requests', 'httpx'])
@pytest.mark.parametrize('case', ['success', 'post_error', 'empty', 'auth_error'])
def test_reply_repair_without_network(tmp_path, monkeypatch, capsys, transport, case):
    if transport == 'httpx':
        original = (ROOT / '02_BACKEND/semantic_runtime/genos.py').read_text()
    else:
        with zipfile.ZipFile(ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-unified-dev-root-20260908.zip') as archive:
            original = archive.read('02_BACKEND/semantic_runtime/genos.py').decode()
    target_file = tmp_path / '02_BACKEND/semantic_runtime/genos.py'
    target_file.parent.mkdir(parents=True)
    target_file.write_text(original)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GENOS_QWEN_KEY', 'dummy-secret')
    monkeypatch.setattr('signal.signal', lambda *args: None)
    monkeypatch.setattr('signal.alarm', lambda *args: None)
    target = types.SimpleNamespace(headers={'Authorization': 'Bearer dummy-secret'},
                                   url=lambda path: 'http://genos.invalid/api/gateway/rep/serving/226/v1' + path)
    genos = types.SimpleNamespace(from_env=lambda kind: (target, ''))
    package = types.ModuleType('semantic_runtime')
    package.genos = genos
    monkeypatch.setitem(sys.modules, 'semantic_runtime', package)
    calls = []

    class Response:
        def __init__(self, status, value):
            self.status_code = status
            self.value = value
            self.text = json.dumps(value)
        def json(self):
            return self.value

    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            if method == 'GET':
                if case == 'auth_error':
                    return Response(401, {'error': 'Invalid token dummy-secret'})
                return Response(200, {'data': [{'id': 'advertised-model-not-serving-id'}]})
            assert kwargs['json']['model'] == 'advertised-model-not-serving-id'
            assert kwargs['json']['max_tokens'] == 256
            assert kwargs['json']['chat_template_kwargs']['enable_thinking'] is False
            if case == 'post_error':
                return Response(400, {'error': 'invalid request dummy-secret'})
            if case == 'empty':
                return Response(200, {'choices': [{'message': {'content': '', 'reasoning_content': 'thought'}, 'finish_reason': 'length'}]})
            return Response(200, {'choices': [{'message': {'content': 'OK'}, 'finish_reason': 'stop'}]})

    monkeypatch.setattr(requests, 'Session', Client)
    monkeypatch.setattr(httpx, 'Client', Client)
    source = SCRIPT.read_text().split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
    status = 0
    try:
        exec(compile(source, 'field-repair', 'exec'), {'__name__': '__main__'})
    except SystemExit as exc:
        status = exc.code
    output = capsys.readouterr().out
    assert 'dummy-secret' not in output
    assert all('/serving/226/v1/' in c[1] for c in calls)
    assert len([c for c in calls if c[0] == 'POST']) == (0 if case == 'auth_error' else 1)
    if case == 'success':
        assert status == 0 and target_file.read_text() != original
        assert list(target_file.parent.glob('*.bak'))[0].read_text() == original
        assert 'LLM 실제 답변: OK' in output
    else:
        assert status != 0 and target_file.read_text() == original
        assert not list(target_file.parent.glob('*.bak'))
