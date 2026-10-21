"""Provider-managed GENOS output length; synthetic contracts, no model calls."""
from copy import deepcopy
from dataclasses import replace
import json
import sqlite3
from types import SimpleNamespace

import pytest

from semantic_runtime.legal_agent import model_contract as mc, output_contract as oc
from semantic_runtime.legal_agent.bounded_source_session import BoundedSourceSession
from semantic_runtime.legal_agent.domain import profile
from semantic_runtime.legal_agent.errors import BudgetExhausted, DeadlineExceeded, ContractError
from test_legal_agent_double_harness import work, PROFILE, ROOT, wire
from test_investigation_completion_adr0678 import completed_app, tree
from test_narrative_answer import RichTransport, settings, n, cc, capture, ok

SCHEMA = {'type': 'object', 'properties': {'ok': {'const': True}},
          'required': ['ok'], 'additionalProperties': False}


def adapter(work, finishes=('stop',), values=None):
    calls = []
    class Transport:
        binding = PROFILE['model_binding']
        def send_once(self, *, body, ticket):
            calls.append(deepcopy(body))
            assert 'max_tokens' not in body and 'max_completion_tokens' not in body
            value = values[len(calls)-1] if values is not None else {'ok': True}
            response = wire(value)
            response['body_json']['choices'][0]['finish_reason'] = finishes[len(calls)-1]
            response['body_json']['usage'] = {'completion_tokens': 17000}
            return response
    s = object.__new__(BoundedSourceSession)
    s.profile = {**PROFILE, 'max_output_tokens': None,
        'candidate_navigation': {'completion_contract': True, 'length_recovery_max_tokens': 12800}}
    s.work = work; s.context = work.context
    s.gateway = SimpleNamespace(domain={}, transport=Transport()); s.selection_views = {}
    return s, calls


@pytest.mark.parametrize('phase', ['bounded-question-plan', 'source-query-plan', 'source-reference-1',
    'source-law-navigation-1', 'source-law-navigation-1-repair', 'memory-assess', 'memory-compose'])
def test_stage_defaults_and_old_length_repair_ceiling_never_restore_limit(work, phase):
    s, calls = adapter(work)
    data = {'repair_contract': {'validation': {'category': 'OUTPUT_INCOMPLETE',
        'issues': [{'code': 'OUTPUT_LENGTH'}]}}}
    assert s.structured('system', data, SCHEMA, phase, 60, 6400) == {'ok': True}
    assert len(calls) == 1 and work.budget()['model_reserved'] == 1
    assert not work.db.execute("SELECT 1 FROM event WHERE kind='LENGTH_RECOVERY_POLICY'").fetchall()


def test_optional_wire_field_and_length_metrics_do_not_invent_server_cap():
    request = mc.structured_request(model='synthetic', max_tokens=None, messages=[], schema_name='s', schema=SCHEMA)
    assert 'max_tokens' not in request
    response = wire({'ok': True})['body_json']
    response['choices'][0]['finish_reason'] = 'length'
    response['usage'] = {'prompt_tokens': 5000, 'completion_tokens': 17000}
    metrics = mc.response_length_metrics(request, response)
    assert metrics['max_tokens'] is None and metrics['output_cap_reached'] is None
    assert metrics['length_diagnosis'] == 'length_stop_cause_unknown'
    assert metrics['context_limit_known'] is False
    with pytest.raises(oc.OutputContractError) as failure:
        mc.structured_value(response, allow_length_repair=False)
    assert failure.value.category == 'OUTPUT_INCOMPLETE' and not failure.value.repairable


def test_nullable_profile_preserves_all_other_budgets():
    value = profile({**PROFILE, 'max_output_tokens': None}, require_model=True)
    assert {k: v for k, v in value.items() if k != 'max_output_tokens'} == {
        k: v for k, v in PROFILE.items() if k != 'max_output_tokens'}
    for key in ('wall_seconds', 'max_model_attempts', 'max_tool_actions'):
        with pytest.raises(ContractError): profile({**value, key: None})
    for invalid in (0, -1, True, 'unlimited'):
        with pytest.raises(ContractError): profile({**value, 'max_output_tokens': invalid})


def test_server_length_failure_is_durable_terminal_without_same_request_retry(work):
    s, calls = adapter(work, ('length',))
    data = {'question': 'synthetic'}
    def invoke(payload, attempt):
        return s.structured('system', payload, SCHEMA,
            'source-law-navigation-1' + ('-repair' if attempt else ''), 60)
    for _ in range(2):
        with pytest.raises(oc.OutputContractError) as failure:
            oc.bounded_decision(work, 'law-navigation', data, SCHEMA, invoke,
                lambda value: oc.validate_shape(value, SCHEMA))
        assert not failure.value.repairable
    assert len(calls) == 1 and work.budget()['model_reserved'] == 1
    assert not work.heads('finding')


@pytest.mark.parametrize('second', [{'ok': True}, {'wrong': True}])
def test_schema_repair_retains_one_owner_and_never_adds_limit(work, second):
    s, calls = adapter(work, ('stop', 'stop'), [{'wrong': True}, second])
    def invoke(payload, attempt):
        return s.structured('system', payload, SCHEMA,
            'source-law-navigation-1' + ('-repair' if attempt else ''), 60)
    def run():
        return oc.bounded_decision(work, 'law-navigation', {'q': 'synthetic'}, SCHEMA, invoke,
            lambda value: oc.validate_shape(value, SCHEMA))
    if second == {'ok': True}: assert run() == run() == second
    else:
        for _ in range(2):
            with pytest.raises(oc.OutputContractError): run()
    assert len(calls) == 2


@pytest.mark.parametrize('exhaustion', ['deadline', 'calls'])
def test_unlimited_output_does_not_reset_request_budget(work, exhaustion):
    s, calls = adapter(work)
    if exhaustion == 'deadline': s.context = replace(s.context, deadline=0)
    else: work.db.execute('UPDATE budget SET model_reserved=model_limit WHERE singleton=1')
    with pytest.raises((DeadlineExceeded, BudgetExhausted)):
        s.structured('system', {}, SCHEMA, 'source-law-navigation-1', 60)
    assert calls == []


@pytest.mark.parametrize('finish', ['stop', 'length'])
def test_native_api_omits_limit_and_keeps_final_status(completed_app, monkeypatch, finish):
    api, transport, runtime = completed_app
    api.app.state.pipeline.term_agent.profile['max_output_tokens'] = None
    original = transport.send_once; requests = []
    def send(**kw):
        request = deepcopy(kw['body']); requests.append(request)
        assert 'max_tokens' not in request and 'max_completion_tokens' not in request
        response = original(**kw)
        stage = json.loads(request['messages'][1]['content'])['view'].get('source_stage', '')
        if stage.startswith('source-law-navigation-1') and finish == 'length':
            response['body_json']['choices'][0].update(finish_reason='length', message={'content': '{"next_action":'})
        return response
    monkeypatch.setattr(transport, 'send_once', send)
    body = {'question': '모의승인규정 제1조 승인 기준은?', 'session_id': 's', 'request_id': 'uncapped-api'}
    result = api.post('/v1/rag/ask', json=body)
    if finish == 'stop':
        assert result.status_code == 200, result.text
        before = len(requests)
        assert api.post('/v1/rag/ask', json=body).json()['answer'] == result.json()['answer']
        assert len(requests) == before
    else:
        assert result.status_code >= 400 and not result.json().get('answer'), result.text
        stages = [json.loads(r['messages'][1]['content'])['view'].get('source_stage', '') for r in requests]
        assert stages.count('source-law-navigation-1') == 1
        assert not any(stage.endswith('-repair') for stage in stages)
    journals = list((runtime/'legal-agent/runs').glob('*/*/journal.sqlite'))
    assert journals
    with sqlite3.connect(journals[-1]) as db:
        rows = db.execute('SELECT request_json FROM model_attempt').fetchall()
        assert rows and all('max_tokens' not in json.loads(row[0]) for row in rows)


@pytest.mark.parametrize('fail', [False, True])
def test_native_streaming_output_is_uncapped_and_interruption_never_publishes(tmp_path, tree, fail):
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    gen, idx = tree; tokens = []; seen = []
    class Transport(RichTransport):
        def send_once(self, **kw):
            seen.append(kw['body']); assert 'max_tokens' not in kw['body']
            return super().send_once(**kw)
        def send_stream_once(self, **kw):
            seen.append(kw['body']); assert 'max_tokens' not in kw['body']
            return super().send_stream_once(**kw)
    transport = Transport(tokens, fail)
    config = {**settings(), 'max_output_tokens': None, 'max_model_attempts': 40, 'max_read_chars': 10000,
        'final_review_enabled': False, 'answer_presentation': n.VERSION,
        'candidate_navigation': {'mode': 'law-first-v1', 'investigation_control': True,
            'completion_contract': True, 'completion_policy_version': cc.V8, 'compact_input': True}}
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=config, legal_agent_transport=transport,
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 't', 'document_ids': ['d']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    with TestClient(app) as api:
        body = {'question': '모의승인규정 제1조 승인 기준은?', 'session_id': 's', 'request_id': 'uncapped-stream'}
        with capture(body['request_id'], tokens.append): result = api.post('/v1/rag/ask', json=body)
        assert transport.streamed and transport.compose_calls == 1 and tokens and seen
        if fail: assert result.status_code != 200 and not result.json().get('answer')
        else: assert ok(result)['answer']['text'] == ''.join(t['text'] for t in tokens)


def test_legacy_genos_provider_rejects_even_complete_json_with_length_stop():
    from semantic_runtime.provider import _structured_genos_value
    response = wire({'ok': True})['body_json']; response['choices'][0]['finish_reason'] = 'length'
    with pytest.raises(oc.OutputContractError) as failure: _structured_genos_value(response)
    assert not failure.value.repairable and failure.value.category == 'OUTPUT_INCOMPLETE'


def test_legacy_genos_provider_omits_output_cap_in_recorded_and_sent_payload(tmp_path, monkeypatch):
    from semantic_runtime.provider import Haiku
    from semantic_runtime import genos
    provider = Haiku(tmp_path, tmp_path/'records', backend='genos', trust_zone='internal')
    monkeypatch.setattr(provider, '_resolve_genos', lambda _: (object(), 'synthetic'))
    sent = []
    def request(target, path, payload):
        sent.append(payload)
        return wire({'ok': True})['body_json']
    monkeypatch.setattr(genos, 'request_json', request)
    value, receipt = provider.call('test', 'synthetic', {}, SCHEMA)
    assert value == {'ok': True} and len(sent) == 1 and 'max_tokens' not in sent[0]
    directory = next((tmp_path/'records').iterdir())
    for name in ('request.json', 'transport-request.json'):
        assert 'max_tokens' not in json.loads((directory/name).read_bytes())
