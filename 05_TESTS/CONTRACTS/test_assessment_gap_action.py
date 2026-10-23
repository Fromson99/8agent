from conftest import term_glossary
"""Source/fact routing regression; synthetic originals and model doubles only."""
from copy import deepcopy
import json

import pytest
from jsonschema import ValidationError
from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent import completion_v5 as v5, completion_v6 as v6
from semantic_runtime.legal_agent import completion_v7 as v7, completion_v8 as v8
from semantic_runtime.legal_agent.errors import ProposalError
from semantic_runtime.legal_agent.investigation_contracts import GAP_KINDS
from test_main50_request_repair import proposal as p5, GAP, tree
from test_focused_input_modality import v6_proposal as p6
from test_single_rule_content import proposal as p7
from test_source_span_norm import proposal as p8, SpanTransport
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT
from test_unified_legal_agent import ok


VERSIONS = [(v5, p5), (v6, p6), (v7, p7), (v8, p8)]
ISSUES = [{'id': 'Q1', 'question': '모의 규정'}]
OPTIONS = [{'id': 'S1', 'source_id': 's', 'text': '신고를 갈음할 수 있다. 신고할 수 있다.'}]


def prepare(impl, raw, materials=()):
    return impl.prepare(raw, impl.assessment_schema(ISSUES, materials, OPTIONS, []), ISSUES, OPTIONS, [])


@pytest.mark.parametrize('impl,make', VERSIONS)
@pytest.mark.parametrize('kind', [k for k in GAP_KINDS if k != 'MISSING_FACT'])
@pytest.mark.parametrize('material', [True, False])
def test_source_gap_action_preserves_gap_claims_and_proposal(impl, make, kind, material):
    raw = make()
    raw['gaps'] = [{**GAP, 'kind': kind, 'material': material, 'suggested_action': 'REQUEST_FACT'}]
    before = deepcopy(raw)
    accepted, audit = prepare(impl, raw)
    assert raw == before
    gap = accepted['gaps'][0]
    assert gap['suggested_action'] == 'RESEARCH'
    for key in ('kind', 'reason', 'missing_target', 'material_id', 'issue_id'):
        assert gap[key] == before['gaps'][0][key]
    assert gap['material'] == ((material or kind != 'UNRESOLVED_REFERENCE') if impl is v5 else material)
    if gap['material']:
        assert accepted['disposition'] == 'NEEDS_INVESTIGATION'
        assert accepted['issue_assessments'][0]['status'] == 'PARTIAL'
    assert audit['gap_action_corrections'] == [{'gap_index': 0, 'issue_id': 'Q1',
        'kind': kind, 'from': 'REQUEST_FACT', 'to': 'RESEARCH'}]
    compiled = impl.materialize(accepted, OPTIONS, ISSUES, audit)
    for claim in compiled['claims']:
        v5.verify_content(claim)
    assert compiled['model_proposal']['gap_action_corrections'] == audit['gap_action_corrections']


@pytest.mark.parametrize('impl,make', VERSIONS)
def test_real_user_fact_remains_user_fact_and_inconsistent_fact_still_rejected(impl, make):
    raw = make()
    raw['gaps'] = [{**GAP, 'kind': 'MISSING_FACT', 'missing_target': '', 'suggested_action': 'REQUEST_FACT'}]
    accepted, audit = prepare(impl, raw)
    assert accepted['gaps'] == raw['gaps'] and 'gap_action_corrections' not in audit
    assert accepted['disposition'] == 'LIMITED_ANSWER'
    raw['gaps'][0]['material_id'] = 'saved'
    with pytest.raises(ProposalError, match='cannot target'):
        prepare(impl, raw, ['saved'])
    raw['gaps'][0].update(material_id=None, suggested_action='RESEARCH')
    with pytest.raises(ProposalError, match='Missing user facts'):
        prepare(impl, raw)


@pytest.mark.parametrize('impl,make', VERSIONS)
def test_legal_research_action_and_schema_boundary_unchanged(impl, make):
    raw = make(); raw['gaps'] = [deepcopy(GAP)]
    accepted, audit = prepare(impl, raw)
    assert accepted['gaps'] == raw['gaps'] and 'gap_action_corrections' not in audit
    raw['gaps'][0].update(kind='UNKNOWN', suggested_action='REQUEST_FACT')
    with pytest.raises(ValidationError): prepare(impl, raw)
    raw['gaps'][0].update(kind='MISSING_SOURCE', suggested_action='UNKNOWN')
    with pytest.raises(ValidationError): prepare(impl, raw)


@pytest.mark.parametrize('bad', ['unknown_ref', 'invented_fact'])
def test_gap_correction_does_not_accept_unsupported_claims(bad):
    raw = p8(); raw['gaps'] = [{**GAP, 'suggested_action': 'REQUEST_FACT'}]
    claim = raw['claims'][0]
    if bad == 'unknown_ref': claim['rule']['norms'][0]['source_ref'] = 'PRIVATE'
    elif bad == 'reversed_text': claim['rule']['norms'][0]['text'] = '신고하여야 한다.'
    else: claim['rule'].update(kind='CASE_APPLICATION', fact_refs=[{'id': 'U0', 'quote': '승인 받음'}])
    with pytest.raises((ProposalError, ValidationError)): prepare(v8, raw)


class GapTransport(SpanTransport):
    def __init__(self, repeat=False, empty=False):
        super().__init__(reentry=True)
        self.repeat, self.empty = repeat, empty
        self.investigated = []

    def send_once(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']
        phase = view.get('source_stage', view['phase'])
        if phase.startswith('source-law-navigation-'):
            self.investigated.extend(deepcopy(view.get('assessment_gaps', [])))
        result = super().send_once(body=body, ticket=ticket)
        if phase.startswith('memory-assess'):
            message = result['body_json']['choices'][0]['message']
            value = json.loads(message['content'])
            if self.repeat or not view['gap_history']:
                value['gaps'] = [{**GAP, 'suggested_action': 'RESEARCH'}]
            if self.empty: value['claims'] = []
            message['content'] = json.dumps(value, ensure_ascii=False)
        return result


@pytest.mark.parametrize('limit,repeat,empty', [(1, False, False), (1, True, False), (0, True, False), (0, True, True)])
def test_native_v8_gap_reentry_bounded_stop_and_idempotent_response(tmp_path, tree, caplog, limit, repeat, empty):
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    gen, index = tree; transport = GapTransport(repeat, empty)
    profile = {**settings(), 'max_model_attempts': 40, 'max_read_chars': 10000,
        'candidate_navigation': {'mode': 'law-first-v1', 'investigation_control': True,
            'completion_contract': True, 'completion_policy_version': cc.V8, 'compact_input': True, 'answer_first': True,
            'assessment_reentry_limit': limit}}
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport,
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'test_team', 'document_ids': ['d']})
    app.state.pipeline.term_agent.unit_fulltext = index
    with TestClient(app) as api:
        body = {'question': '모의승인규정 제1조 승인 기준은?', 'session_id': 'gap', 'request_id': 'r1'}
        response = api.post('/v1/rag/ask', json=body)
        assert not any('assess-repair' in phase for phase in transport.phases)
        if empty:
            assert response.status_code == 200, response.text
            out=response.json()
            assert not out['answer']['claims'] and out['answer']['unresolved']
            assert '승인 후 보고한다.' in out['answer']['text']
            assert out['assembly']['term_agent']['text_integrity'] == 'VERIFIED_SOURCE_EXCERPTS'
            return
        out = ok(response)
        assert '승인 후 보고한다.' in out['answer']['text']
        assert transport.phases.count('memory-assess') == (2 if limit else 1)
        if limit:
            assert transport.investigated
            assert all(g['suggested_action'] == 'RESEARCH' for g in transport.investigated)
        if repeat:
            assert out['assembly']['term_agent']['accepted_outcome']['answer_coverage'] != 'COVERED'
        calls = len(transport.phases)
        assert ok(api.post('/v1/rag/ask', json=body))['answer'] == out['answer']
        assert len(transport.phases) == calls
