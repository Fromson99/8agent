"""Long legal observations survive conversion, publication and reuse unchanged."""
from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient
from jsonschema import ValidationError, validate
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent import completion_v5 as v5, completion_v6 as v6
from semantic_runtime.legal_agent import completion_v7 as v7, completion_v8 as v8
from semantic_runtime.legal_agent import narrative_answer as narrative
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from test_assessment_gap_action import VERSIONS, ISSUES, OPTIONS
from test_source_span_norm import proposal
from test_bounded_delivered_handoff import StopTransport
from test_main50_request_repair import tree
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire


LONG = ('원문에 연결된 판단의 세부 설명입니다. ' * 500).strip()


@pytest.mark.parametrize('impl,make', VERSIONS)
@pytest.mark.parametrize('field', ['subject', 'conclusion', 'condition', 'exception'])
def test_long_content_survives_every_supported_conversion(impl, make, field):
    raw = make()
    claim = raw['claims'][0]
    if field == 'subject':
        claim['rule']['subject'] = LONG
    elif field == 'conclusion':
        if impl in (v5, v6):
            claim['conclusion'] = LONG
        else:
            claim['rule']['norms'][0]['text'] = LONG
    elif field == 'condition':
        claim['rule']['condition_tree'] = {'mode': 'LEAF', 'text': LONG, 'evidence_refs': ['S1']}
    else:
        claim['rule']['exceptions'] = [{'target': '규칙', 'text': LONG, 'evidence_refs': ['S1']}]
    original = deepcopy(raw)
    accepted, model = impl.prepare(raw, impl.assessment_schema(ISSUES, [], OPTIONS, []), ISSUES, OPTIONS, [])
    assert raw == original
    assessment = impl.materialize(accepted, OPTIONS, ISSUES, model)
    result = cc.compose(assessment, cc.default_plan(assessment))
    cc.verify_composition(assessment, result)
    v5.verify_content(result['claims'][0])
    assert LONG in result['text']
    assert result['claims'][0]['answer_content']['rule'] == raw['claims'][0]['rule'] or impl is v8


@pytest.mark.parametrize('stream_type', [narrative.ParagraphStream, narrative.TokenStream])
def test_long_narrative_and_stream_have_no_character_cutoff(stream_type):
    text = LONG * 16 + '끝😀'
    value = {'paragraphs': [{'claim_ids': ['C1'], 'text': text}]}
    narrative.checked(value, ['C1'])
    sent = []
    stream = stream_type(sent.append, ['C1'])
    raw = json.dumps(value, ensure_ascii=False)
    for start in range(0, len(raw), 4096):
        stream.feed(raw[start:start + 4096])
    assert ''.join(sent) == text
    bad = deepcopy(value)
    bad['paragraphs'][0]['claim_ids'] = ['PRIVATE']
    rejected = []
    with pytest.raises(ValidationError):
        stream_type(rejected.append, ['C1']).feed(json.dumps(bad))
    assert rejected == []


@pytest.mark.parametrize('impl,make', [(v6, VERSIONS[1][1]), (v7, VERSIONS[2][1]), (v8, VERSIONS[3][1])])
def test_long_original_quote_is_preserved_and_still_exact(impl, make):
    raw = make()
    original = LONG + ' 신고할 수 있다.'
    norm = raw['claims'][0]['rule']['norms'][0]
    norm.update(kind='UNSPECIFIED', text=LONG)
    if impl is not v8:
        norm['source_quote'] = original
    options = [{'id': 'S1', 'source_id': 's', 'text': original}]
    value, model = impl.prepare(raw, impl.assessment_schema(ISSUES, [], options, []), ISSUES, options, [])
    materialized = impl.materialize(value, options, ISSUES, model)
    assert materialized['claims'][0]['quote'] == original
    assert materialized['claims'][0]['answer_content']['rule']['norms'][0]['source_quote'] == original
    if impl is not v8:
        norm['source_quote'] += ' 변조'
        with pytest.raises(ProposalError):
            impl.prepare(raw, impl.assessment_schema(ISSUES, [], options, []), ISSUES, options, [])


def test_long_questions_are_accepted_without_bypassing_scope():
    from semantic_runtime.contracts import Contracts
    from workflow.contracts import request, WorkflowError
    question = LONG * 3
    Contracts(ROOT).validate_port('runtime.request', {'question': question})
    principal = {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d']}
    body = {'question': question, 'session_id': 'long', 'request_id': 'r1', 'document_ids': ['d']}
    assert request(body, principal)['question'] == question
    with pytest.raises(WorkflowError): request({**body, 'document_ids': ['private']}, principal)


def test_long_claim_does_not_weaken_source_or_fact_validation():
    raw = proposal()
    raw['claims'][0]['rule']['norms'][0]['text'] = LONG
    options = [{'id': 'S1', 'source_id': 's', 'text': '신고할 수 있다.'}]
    schema = v8.assessment_schema(ISSUES, [], options, [])
    raw['claims'][0]['rule']['norms'][0]['source_ref'] = 'PRIVATE'
    with pytest.raises(ValidationError): v8.prepare(raw, schema, ISSUES, options, [])
    raw['claims'][0]['rule']['norms'][0]['source_ref'] = 'S1'
    raw['claims'][0]['rule'].update(kind='CASE_APPLICATION', fact_refs=[{'id': 'U0', 'quote': LONG}])
    with pytest.raises((ValidationError, ProposalError)): v8.prepare(raw, schema, ISSUES, options, [])


def test_comparison_finalize_preserves_long_paragraph_and_exact_quote():
    from workflow.risk_team_compare_workflow.finalize import SCHEMA
    from workflow.risk_team_compare_workflow.contracts import COMPARE, check_citations
    validate({'rows': [], 'answer': LONG, 'unresolved': [LONG]}, COMPARE)
    citation = {'evidence': 'E1', 'quote': LONG}
    value = {'paragraphs': [{'text': LONG, 'citations': [citation]}], 'unresolved': [LONG]}
    validate(value, SCHEMA)
    check_citations([citation], {'E1': {'spans': [{'text': LONG}]}})
    with pytest.raises(ValueError): check_citations([citation], {'E1': {'spans': [{'text': '다른 원문'}]}})


def test_workflow_delivers_sse_answer_larger_than_one_megabyte(monkeypatch):
    import asyncio
    from test_genos_answer_stream import load
    workflow = load('unlimited_sse_workflow', '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    monkeypatch.setattr(workflow, '_post_code_serving', lambda body: {'status': 200, 'body': {'ad_handled': False}})
    monkeypatch.setattr(workflow, '_settings', lambda: ('http://fixture/json', 'synthetic', 2))
    expected = LONG * 40 + '끝'
    emitted = []
    async def emit(self, event, value):
        if event == 'token': emitted.append(value)
    monkeypatch.setattr(workflow._ChatProgress, '_send', emit)
    class Response:
        status = 200
        headers = {'Content-Type': 'text/event-stream'}
        def __init__(self, rid): self.rid = rid
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def __iter__(self):
            for frame in [
                {'event': 'answer_delta', 'data': {'schema_version': 'rag-answer-delta-v1',
                    'request_id': self.rid, 'seq': 1, 'text': expected}},
                {'event': 'result', 'data': {'status': 200, 'body': {'answer': {'text': expected}}}}
            ]:
                encoded = ('data: ' + json.dumps(frame, ensure_ascii=False) + '\n\n').encode()
                assert len(encoded) > 1048576
                yield encoded
    monkeypatch.setattr(workflow.urllib.request, 'urlopen', lambda req, **kw: Response(json.loads(req.data)['request_id']))
    result = asyncio.run(workflow.run({'question': 'synthetic', 'socketIOClientId': 'fixture'}))
    assert result['answer_status'] == 'answered' and result['text'] == expected
    assert ''.join(emitted) == expected


class LongTransport(StopTransport):
    def __init__(self):
        super().__init__('repaired')

    def send_once(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']
        phase = view.get('source_stage', view['phase'])
        if phase.startswith('memory-assess'):
            self.phases.append(phase)
            options = view['evidence_options']
            ref = next(o['id'] for o in options if '승인 후 보고한다.' in o['text'])
            value = proposal(LONG, 'UNSPECIFIED', [ref], ref)
            value.pop('disposition')
            for row in value['issue_assessments']: row.pop('reason')
            return wire(value)
        if phase == narrative.PHASE:
            self.phases.append(phase)
            return wire({'paragraphs': [{'claim_ids': view['answer_claim_ids'], 'text': LONG * 2 + '끝'}]})
        return super().send_once(body=body, ticket=ticket)


@pytest.mark.parametrize('rich', [False, True])
def test_long_answer_api_publication_restart_reuse_and_integrity(tmp_path, tree, rich):
    from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
    from semantic_runtime.legal_agent.unified_publication import validate_saved, validate_current
    gen, idx = tree
    transport = LongTransport()
    runtime = tmp_path / 'runtime'
    profile = {**settings(), 'max_model_attempts': 40, 'max_read_chars': 10000,
        'max_context_chars': 200000, 'final_review_enabled': False,
        **({'answer_presentation': narrative.VERSION} if rich else {}),
        'candidate_navigation': {'mode': 'law-first-v1', 'investigation_control': True,
            'completion_contract': True, 'completion_policy_version': cc.V8, 'compact_input': True}}
    def app():
        instance = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(),
            implementation='legal-agent-unified-v6', legal_agent_profile=profile,
            legal_agent_transport=transport, runtime_root=runtime,
            memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d']})
        instance.state.pipeline.term_agent.unit_fulltext = idx
        return instance
    body = {'question': '모의승인규정 제1조 승인 기준은?', 'session_id': 'long', 'request_id': 'r1'}
    first = app()
    with TestClient(first) as api:
        response = api.post('/v1/rag/ask', json=body)
        assert response.status_code == 200, response.text
        out = response.json()
        assert LONG in out['answer']['text']
        count = len(transport.phases)
        assert 'memory-assess-repair' not in transport.phases
        again = api.post('/v1/rag/ask', json=body)
        assert again.status_code == 200 and again.json()['answer'] == out['answer']
        assert len(transport.phases) == count
    journal = next((runtime / 'legal-agent/runs').glob('*/' + out['run_id'] + '/journal.sqlite'))
    repo = UnifiedRepository(journal)
    try:
        validate_saved(repo, out)
        budget, deadline = repo.budget(), repo.run()['deadline_at']
        tampered = deepcopy(out)
        tampered['answer']['text'] = tampered['answer']['text'][:-1]
        with pytest.raises(ContractError): validate_saved(repo, tampered)
        with pytest.raises(ContractError, match='authorization changed'):
            validate_current(repo, out, first.state.pipeline.store, allowed_documents=[])
    finally:
        repo.close()
    with TestClient(app()) as api:
        resumed = api.post('/v1/rag/ask', json=body)
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()['answer'] == out['answer'] and len(transport.phases) == count
    repo = UnifiedRepository(journal)
    try:
        assert repo.budget() == budget and repo.run()['deadline_at'] == deadline
    finally:
        repo.close()
