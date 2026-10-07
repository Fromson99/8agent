"""Wire compaction preserves evidence, strict validation and conditional repairs.

All responses are synthetic; no model quality or serving latency is measured.
"""
import json
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from conftest import term_glossary
from test_legal_agent_double_harness import generation, wire
from test_legal_agent_v5 import session, drafted, review
from test_genos_wire_schema import _Context, _Transport
from semantic_runtime.legal_agent import obligation_protocol
from semantic_runtime.legal_agent.bounded_source_session import _Gateway, _Protocol
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from semantic_runtime.legal_agent.gateway import WIRE_PROJECTION, compact_wire_view
from semantic_runtime.legal_agent.numbered_references import NumberedReferences


def test_duplicate_span_text_is_removed_without_losing_source_or_coordinates():
    view = {'exact_evidence': [{'evidence': 'E1', 'text': '제1조 A 또는 B.', 'spans': [
        {'block_id': 'b1', 'start_cp': 0, 'end_cp': 11, 'text': '제1조 A 또는 B.'},
        {'block_id': 'b2', 'start_cp': 0, 'end_cp': 5, 'text': '추가 문맥'}]}],
        'navigation_choices': [{'target': 1}], 'continuations': [{'action': 'needed by reviewer'}],
        'question_plan': {'demands': ['요건 설명']}, 'relation_notices': [{'relation_id': 'REL1'}]}
    original = deepcopy(view)
    composed = compact_wire_view(view, 'compose')
    assert view == original
    assert composed['exact_evidence'][0]['text'] == original['exact_evidence'][0]['text']
    assert composed['exact_evidence'][0]['spans'][0] == {'block_id': 'b1', 'start_cp': 0, 'end_cp': 11}
    assert composed['exact_evidence'][0]['spans'][1]['text'] == '추가 문맥'
    assert composed['question_plan'] == original['question_plan']
    assert composed['relation_notices'] == original['relation_notices']
    assert 'navigation_choices' not in composed and 'continuations' not in composed
    reviewed = compact_wire_view(view, 'review')
    assert reviewed['continuations'] == original['continuations']
    assert reviewed['navigation_choices'] == original['navigation_choices']


@pytest.mark.parametrize('phase,name', [('compose', 'Draft'), ('review', 'ReviewDecision')])
def test_main_v5_projection_is_verified_and_receipted(tmp_path, generation, phase, name):
    with session(tmp_path, generation) as s:
        drafted(s)
        v = review(s)[0] if phase == 'review' else s.view(phase, required=s.packed['evidence_ids'])
        original = deepcopy(v)
        refs = NumberedReferences(v)
        request = s.gateway.request(phase, v, name, references=refs)
        shown = json.loads(request['messages'][1]['content'])
        assert 'output_schema' not in shown and 'DomainSpec' not in request['messages'][0]['content']
        assert request['response_format']['json_schema']['strict'] is True
        Draft202012Validator.check_schema(request['response_format']['json_schema']['schema'])
        assert v == original and v['exact_evidence'][0]['spans'][0]['text']
        assert shown['view']['exact_evidence'][0]['text'] == v['exact_evidence'][0]['text']
        assert 'text' not in shown['view']['exact_evidence'][0]['spans'][0]
        attempt = s.work.reserve_attempt(v, request, 'compact-call', 1, phase,
            numbered_references=refs, wire_projection=WIRE_PROJECTION)
        event = s.work.db.execute("SELECT payload_json FROM event WHERE kind='WIRE_PROJECTION'").fetchone()
        assert json.loads(event[0])['attempt_id'] == attempt
        stored = json.loads(s.work.db.execute('SELECT body_json FROM model_view WHERE view_id=?',
            (v['view_id'],)).fetchone()[0])
        assert stored == original
        shown['view']['exact_evidence'][0]['spans'][0]['end_cp'] += 1
        request['messages'][1]['content'] = json.dumps(shown, ensure_ascii=False)
        with pytest.raises(ContractError, match='wire view differs'):
            s.work.reserve_attempt(v, request, 'forged-compact', 1, phase,
                numbered_references=refs, wire_projection=WIRE_PROJECTION)


def test_bounded_v5_also_uses_only_response_schema():
    schema = obligation_protocol.schema('TurnDecision')['properties']['question_plan']['anyOf'][0]
    profile = {'schema_version': 'system-harness-profile-v5', 'model_binding': _Transport.binding,
               'max_output_tokens': 4096}
    gateway = _Gateway(None, _Context(), profile, {}, _Transport(), message_protocol=_Protocol(schema),
        system='모의 요구 정리', prompts={'investigate': ''})
    request = gateway.request('investigate', {'original_question': '요건은?'}, 'BoundedSourceDecision')
    assert json.loads(request['messages'][1]['content']) == {'view': {'original_question': '요건은?'}}
    assert request['response_format']['json_schema']['strict'] is True
    assert not Draft202012Validator(schema).is_valid({'demands': [], 'context_refs': [], 'change_reason': '요건'})


@pytest.mark.parametrize('invalid_first', [False, True])
def test_valid_answer_has_one_call_and_invalid_output_alone_triggers_repair(tmp_path, generation, invalid_first):
    with session(tmp_path, generation) as s:
        drafted(s)
        v, original = review(s)
        refs = NumberedReferences(v)
        valid = refs.project(original)
        calls = []
        def respond(*, body, ticket):
            calls.append(deepcopy(body))
            value = deepcopy(valid)
            if invalid_first and len(calls) == 1:
                value['checks'][0]['claim'] = 999
            return wire(value)
        s.gateway.transport.send_once = respond
        assert s.gateway.generate('review', v, 'ReviewDecision') == original
        assert len(calls) == (2 if invalid_first else 1)
        if invalid_first:
            repair = json.loads(calls[1]['messages'][-1]['content'])
            assert repair['error'] and repair['invalid_response_excerpt'].startswith('{')
            assert calls[0]['messages'] == calls[1]['messages'][:2]
            assert calls[0]['response_format'] == calls[1]['response_format']


def test_compact_draft_still_requires_real_obligation_reference(tmp_path, generation):
    with session(tmp_path, generation) as s:
        drafted(s)
        v = s.view('compose', required=s.packed['evidence_ids'])
        refs = NumberedReferences(v)
        request = s.gateway.request('compose', v, 'Draft', references=refs)
        value = refs.project({'paragraphs': [s.work.heads('claim', current=True)[0]['payload']], 'limitations': []})
        value['paragraphs'][0]['obligation_refs'] = []
        with pytest.raises(ProposalError):
            refs.decode(value, request['response_format']['json_schema']['schema'], 'Draft')
