"""Synthetic reproduction of the photographed intent/action conflict."""
from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient

from semantic_runtime.legal_agent.errors import ProposalError
from semantic_runtime.legal_agent.numbered_references import NumberedReferences
from test_legal_agent_double_harness import generation, BINDING, WireTransport, wire
from test_legal_agent_v5 import SETTINGS, app_for, decision, plan, session, tool


@pytest.mark.parametrize('intent', ['DRAFT', 'CLARIFY'])
def test_conflict_corrected_in_same_view_before_any_mutation(tmp_path, generation, intent):
    profile = {**SETTINGS, 'max_same_error_repairs': 0, 'max_schema_repairs': 1}
    with session(tmp_path, generation, profile=profile) as s:
        view = s.view('investigate')
        action = tool('locate', target=s.sources.root, locator='모의승인규정 제1조',
                      branch='any', cursor=None)
        invalid = decision(plan(), intent=intent, actions=[action])
        valid = {**deepcopy(invalid), 'intent': 'CONTINUE'}
        encode = NumberedReferences(view).project
        transport = WireTransport([encode(invalid), encode(valid)])
        s.gateway.transport = transport
        accepted = s.gateway.generate('investigate', view, 'TurnDecision')
        assert accepted == valid
        first, repaired = transport.calls
        assert first['messages'] == repaired['messages'][:2]
        correction = json.loads(repaired['messages'][2]['content'])
        assert 'use CONTINUE for actions' in correction['error']
        assert 'actions=[]' in correction['error']
        assert json.loads(correction['invalid_response_excerpt']) == encode(invalid)
        assert not s.work.observations()
        assert not s.work.heads('question_plan')
        rows = s.work.db.execute('SELECT logical_call_id, view_id FROM model_attempt').fetchall()
        assert len(rows) == 2 and len({tuple(row) for row in rows}) == 1
        assert not s.work.db.execute("SELECT 1 FROM event WHERE kind='SEMANTIC_REPAIR'").fetchone()
        s.apply_turn(view, accepted)
        assert len(s.work.observations()) == 1
        assert len(s.work.heads('question_plan')) == 1


@pytest.mark.parametrize('repair_limit', [0, 1])
def test_repeated_conflict_keeps_limits_and_executes_no_action(tmp_path, generation, repair_limit):
    profile = {**SETTINGS, 'max_schema_repairs': repair_limit}
    with session(tmp_path, generation, profile=profile) as s:
        view = s.view('investigate')
        invalid = decision(plan(), intent='DRAFT', actions=[tool(
            'locate', target=s.sources.root, locator='모의승인규정 제1조', branch='any', cursor=None)])
        output = NumberedReferences(view).project(invalid)
        transport = WireTransport([output] * (repair_limit + 1))
        s.gateway.transport = transport
        with pytest.raises(ProposalError, match='after bounded repair'):
            s.gateway.generate('investigate', view, 'TurnDecision')
        assert len(transport.calls) == repair_limit + 1
        assert not s.work.observations() and not s.work.heads('question_plan')
        errors = [json.loads(row[0]) for row in s.work.db.execute(
            "SELECT payload_json FROM event WHERE kind='OUTPUT_SCHEMA_INVALID' ORDER BY seq")]
        assert errors[-1]['repair_scheduled'] is False


def test_filtered_replies_fail_closed_and_keep_provider_signal(tmp_path, generation):
    class FilteredTransport(WireTransport):
        def send_once(self, *, body, ticket):
            result = super().send_once(body=body, ticket=ticket)
            result['body_json']['choices'][0]['finish_reason'] = 'content_filter'
            return result

    with session(tmp_path, generation, profile={**SETTINGS, 'max_schema_repairs': 1}) as s:
        transport = FilteredTransport(['출력 정책에 따라 답변할 수 없습니다.'] * 2)
        s.gateway.transport = transport
        with pytest.raises(ProposalError, match='after bounded repair'):
            s.gateway.generate('investigate', s.view('investigate'), 'TurnDecision')
        assert len(transport.calls) == 2
        assert not s.work.observations() and not s.work.heads('question_plan')
        for row in s.work.db.execute('SELECT response_json FROM model_attempt'):
            result = json.loads(row[0])
            assert result['body_json']['choices'][0]['finish_reason'] == 'content_filter'


@pytest.mark.parametrize('intent', ['DRAFT', 'CLARIFY'])
def test_http_conflict_repair_then_read_select_and_answer(tmp_path, generation, intent):
    class Transport:
        binding = BINDING

        def __init__(self):
            self.calls = []
            self.repaired = False

        def validate_model(self):
            return {'verified': True, 'synthetic': True}

        def send_once(self, *, body, ticket):
            self.calls.append(deepcopy(body))
            view = json.loads(body['messages'][1]['content'])['view']
            phase = view['phase']
            if phase == 'compose':
                return wire({'paragraphs': [{'text': '모의 승인 대상입니다.',
                    'evidence': [view['exact_evidence'][0]['evidence']], 'question_refs': [1],
                    'fact_dependencies': [], 'relation_dependencies': [],
                    'obligation_refs': [view['question_plan']['demands'][0]['id']]}], 'limitations': []})
            choices = {'choices': [{'source': row['evidence'], 'decision': 'KEEP_CORE',
                                   'reason': '모의 승인 원문 확인'} for row in view['exact_evidence']]}
            if phase == 'select_sources':
                return wire(choices)
            if view['question_plan'] is None:
                action = tool('locate', target=view['corpus_root'], locator='모의승인규정 제1조',
                              branch='any', cursor=None)
                action['question_refs'] = [1]
                if len(body['messages']) == 3:
                    correction = json.loads(body['messages'][2]['content'])
                    assert 'actions=[]' in correction['error']
                    assert self.calls[0]['messages'] == body['messages'][:2]
                    self.repaired = True
                return wire(decision(plan(refs=(1,)), actions=[action],
                                     intent='CONTINUE' if self.repaired else intent))
            if not view['exact_evidence']:
                target = next(o['items'][0]['target'] for o in view['last_action_results'] if o['tool'] == 'locate')
                action = tool('read', target=target, extent='subtree', cursor=None)
                action['question_refs'] = [1]
                return wire(decision(actions=[action]))
            return wire(decision(source_selection=choices, intent='DRAFT'))

    transport = Transport()
    app = app_for(tmp_path, generation, transport, {**SETTINGS,
        'max_same_error_repairs': 0, 'max_schema_repairs': 1, 'final_review_enabled': False})
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json={'question': '승인 대상과 요건은?', 'document_ids': ['d']})
        assert response.status_code == 200, response.text
        result = response.json()
        assert transport.repaired
        assert result['answer']['text'] == '모의 승인 대상입니다.'
        assert result['answer']['claims']
        assert result['assembly']['term_agent']['source_bundle']['sources']
        assert not result['answer']['unresolved']
