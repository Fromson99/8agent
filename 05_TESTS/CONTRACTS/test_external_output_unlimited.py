"""Current local/research wire policy; mock HTTP only, no external model calls."""
from copy import deepcopy
import json
import os
from pathlib import Path

import httpx
import pytest
from conftest import term_glossary

from lawrag.research.experiment_client import (
    ExperimentClient, ExperimentCallError, ExperimentFormatError, ExperimentProviderError,
    OpenRouterProxyClient,
)
from semantic_runtime.legal_agent import local_gemma
from semantic_runtime.legal_agent.errors import ContractError, TransportError
from semantic_runtime.legal_agent.output_contract import OutputContractError

ROOT = Path(os.environ.get('OUTPUT_LIMIT_TEST_CODE_ROOT', Path(__file__).resolve().parents[2]))
CAPS = {'max_tokens', 'max_completion_tokens', 'max_output_tokens'}
SCHEMA = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
          'required': ['ok'], 'additionalProperties': False}


def reply(*, model='qwen/qwen3.8-27b', provider='Parasail', finish='stop'):
    return {'model': model, 'provider': provider,
            'choices': [{'finish_reason': finish, 'message': {'content': '{"ok":true}'}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 17000, 'total_tokens': 17010}}


@pytest.mark.parametrize('override', [None, 6400, 12800])
@pytest.mark.parametrize('images', [(), ('data:image/png;base64,aW1hZ2U=',)])
def test_text_and_vlm_ignore_legacy_override_on_actual_wire(tmp_path, monkeypatch, override, images):
    monkeypatch.setenv('OPEN_ROUTER', 'synthetic-test-key')
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=reply())
    client = ExperimentClient(ROOT, tmp_path/'calls', max_calls=1,
        max_output_tokens=override, transport=httpx.MockTransport(handler))
    assert client.generate('Return JSON', {'public': 'synthetic'}, SCHEMA, images=images) == {'ok': True}
    assert client.max_output_tokens is None and len(seen) == 1 and not CAPS.intersection(seen[0])
    assert seen[0]['reasoning'] == {'effort': 'none'}
    assert seen[0]['provider']['only'] == ['parasail/fp8']
    assert seen[0]['provider']['allow_fallbacks'] is False
    assert client.usage[0]['output_tokens'] == 17000
    assert json.loads(next((tmp_path/'calls').glob('call-*/request.json')).read_text()) == seen[0]
    with pytest.raises(ExperimentCallError, match='budget_exhausted'):
        client.generate('Return JSON', {}, SCHEMA)
    assert len(seen) == 1


@pytest.mark.parametrize('proxy', [False, True])
def test_raw_chat_removes_all_caps_without_mutating_caller(tmp_path, monkeypatch, proxy):
    monkeypatch.setenv('OPEN_ROUTER', 'synthetic-test-key')
    seen = []
    client_type = OpenRouterProxyClient if proxy else ExperimentClient
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=reply(model=client.model,
            provider=client.proxy['allowed_upstream_providers'][0]))
    client = client_type(ROOT, tmp_path/'calls', max_calls=1, max_output_tokens=6400,
        transport=httpx.MockTransport(handler))
    body = {'model': client.model, 'messages': [{'role': 'user', 'content': 'synthetic'}],
            **{key: 6400 for key in CAPS}}
    original = deepcopy(body)
    client.chat_completions(body)
    assert body == original and not CAPS.intersection(seen[0])
    assert json.loads(next((tmp_path/'calls').glob('call-*/request.json')).read_text()) == seen[0]


@pytest.mark.parametrize('status,finish,error', [(200, 'length', ExperimentFormatError),
                                              (429, 'stop', ExperimentProviderError)])
def test_experiment_incomplete_or_rejected_reply_is_saved_without_hidden_retry(
        tmp_path, monkeypatch, status, finish, error):
    monkeypatch.setenv('OPEN_ROUTER', 'synthetic-test-key')
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(status, json=reply(finish=finish))
    client = ExperimentClient(ROOT, tmp_path/'calls', max_calls=4, max_repairs=1,
        transport=httpx.MockTransport(handler))
    with pytest.raises(error) as failure:
        client.generate('Return JSON', {}, SCHEMA)
    assert len(seen) == client.calls == 1 and not CAPS.intersection(seen[0])
    assert failure.value.response['status_code'] == status
    assert len(list((tmp_path/'calls').glob('call-*/response.json'))) == 1
    assert not list((tmp_path/'calls').glob('call-*/output.json'))


@pytest.mark.parametrize('status,finish', [(200, 'stop'), (200, 'length'), (429, 'stop')])
def test_local_transport_actual_http_and_incomplete_failure(monkeypatch, status, finish):
    monkeypatch.setenv('OPEN_ROUTER', 'synthetic-test-key')
    transport = local_gemma.LocalGemmaTransport(ROOT, ROOT)
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(status, json=reply(finish=finish))
    original_client = httpx.Client
    monkeypatch.setattr(local_gemma.httpx, 'Client',
        lambda **kw: original_client(**kw, transport=httpx.MockTransport(handler)))
    body = {'model': transport.binding['model'], 'stream': False,
            'messages': [{'role': 'user', 'content': 'synthetic'}],
            **{key: 6400 for key in CAPS}}
    original = deepcopy(body)
    def invoke(): return transport.send_once(body=body, ticket={'remaining_seconds': 30})
    if status == 429:
        with pytest.raises(TransportError) as failure: invoke()
        assert failure.value.response['status_code'] == 429 and failure.value.retryable
    elif finish == 'length':
        with pytest.raises(OutputContractError) as failure: invoke()
        assert not failure.value.repairable and failure.value.category == 'OUTPUT_INCOMPLETE'
        assert failure.value.response['body_json']['usage']['completion_tokens'] == 17000
    else:
        assert invoke()['body_json']['usage']['completion_tokens'] == 17000
    assert len(seen) == 1 and not CAPS.intersection(seen[0]) and body == original
    with pytest.raises(ContractError):
        transport.send_once(body={**body, 'model': 'unapproved'}, ticket={'remaining_seconds': 30})
    assert len(seen) == 1


def test_grant_rejects_policy_hash_drift(tmp_path, monkeypatch):
    monkeypatch.setenv('OPEN_ROUTER', 'synthetic-test-key')
    for name in ('00_SYSTEM/EXPERIMENT_MODEL_POLICY.json', '00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'):
        dest = tmp_path/name; dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT/name).read_bytes())
    path = tmp_path/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'
    policy = json.loads(path.read_text()); policy['max_output_tokens'] = 6400
    path.write_text(json.dumps(policy))
    with pytest.raises(ContractError, match='policy mismatch'):
        local_gemma.LocalGemmaTransport(tmp_path, tmp_path)


def test_frozen_finite_policy_still_reproduces_old_request(tmp_path, monkeypatch):
    monkeypatch.setenv('OPEN_ROUTER', 'synthetic-test-key')
    policy = json.loads((ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').read_text())
    policy['max_output_tokens'] = 6400
    policy.pop('output_policy', None)
    path = tmp_path/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'; path.parent.mkdir()
    path.write_text(json.dumps(policy))
    seen = []
    def handler(request):
        seen.append(json.loads(request.content)); return httpx.Response(200, json=reply())
    client = ExperimentClient(tmp_path, tmp_path/'calls', max_output_tokens=8000,
        transport=httpx.MockTransport(handler))
    assert client.generate('Return JSON', {}, SCHEMA) == {'ok': True}
    assert seen[0]['max_tokens'] == 8000


@pytest.mark.parametrize('route', ['connection', 'failure', 'batch'])
def test_current_api_sends_uncapped_requests_and_reuses_completed_request(
        tmp_path, term_glossary, monkeypatch, route):
    from semantic_runtime import app as api_module
    from test_selected_connection_scope_api import test_actual_api_reads_link_or_structural_target_and_reuses_request
    original = api_module.create_app
    seen = []
    def create(*args, **kwargs):
        transport = kwargs['legal_agent_transport']
        # Exercise this runtime's pinned profile, including older selected MAIN
        # which has no later experimental navigation settings.
        profile = json.loads((ROOT/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
        for name in ('read_judgment', 'small_connection_context', 'answer_first', 'answer_progress_control'):
            if name in profile['candidate_navigation']:
                profile['candidate_navigation'][name] = False
        profile.update(model_binding=transport.binding, answer_presentation='structured')
        kwargs['legal_agent_profile'] = profile
        send = transport.send_once
        def checked(**kw):
            seen.append(deepcopy(kw['body']))
            assert not CAPS.intersection(kw['body'])
            return send(**kw)
        monkeypatch.setattr(transport, 'send_once', checked)
        return original(*args, **kwargs)
    monkeypatch.setattr(api_module, 'create_app', create)
    test_actual_api_reads_link_or_structural_target_and_reuses_request(
        tmp_path, term_glossary, route, monkeypatch)
    assert len(seen) >= 3
