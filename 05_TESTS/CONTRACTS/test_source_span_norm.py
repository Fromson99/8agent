from copy import deepcopy
import json
import pytest
from jsonschema import ValidationError
from semantic_runtime.legal_agent import completion_v8 as v8, completion_v5 as v5, completion_contracts as cc
from semantic_runtime.legal_agent.errors import ProposalError, ContractError
from test_single_rule_content import proposal as old_proposal, SingleTransport
from test_main50_request_repair import tree, GAP
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire
from test_unified_legal_agent import ok

ISSUES = [{'id': 'Q1', 'question': '모의 규정'}]

def proposal(quote='신고할 수 있다.', kind='PERMISSION', ids=('S1',), ref='S1'):
    value = old_proposal(ids, quote, kind)
    for claim in value['claims']:
        claim['content_contract'] = v8.CONTENT
        for norm in claim['rule']['norms']:
            norm.pop('source_quote'); norm['source_ref'] = ref
    return value

def accepted(value, options):
    result, model = v8.prepare(value, v8.assessment_schema(ISSUES, [], options, []), ISSUES, options, [])
    return v8.materialize(result, options, ISSUES, model)

@pytest.mark.parametrize('quote,actual,wrong', [
    ('신고할 수 있다.', 'PERMISSION', 'OBLIGATION'),
    ('보고하여야 한다.', 'OBLIGATION', 'PROHIBITION'),
    ('양도하여서는 아니 된다.', 'PROHIBITION', 'PERMISSION')])
def test_source_id_binds_original_and_corrects_only_label(quote, actual, wrong):
    options = [{'id': 'S1', 'source_id': 's', 'text': quote}]
    p = proposal(quote, wrong); original = deepcopy(p)
    out = accepted(p, options); claim = out['claims'][0]
    norm = claim['answer_content']['rule']['norms'][0]
    assert norm['source_quote'] == quote and norm['kind'] == actual and norm['text'] == quote
    assert p == original and out['model_proposal']['norm_label_corrections'][0]['model_kind'] == wrong
    rendered = cc.compose(out, cc.default_plan(out)); cc.verify_composition(out, rendered)
    v5.verify_content(rendered['claims'][0])
    p['claims'][0]['rule']['norms'][0]['source_quote'] = quote
    with pytest.raises(ValidationError): accepted(p, options)

@pytest.mark.parametrize('kind', ['OBLIGATION', 'PERMISSION'])
def test_contextual_label_kept_without_claiming_heuristic_certification(kind):
    quote = '해당 금액을 산입한다.'
    out = accepted(proposal(quote, kind), [{'id': 'S1', 'source_id': 's', 'text': quote}])
    assert out['claims'][0]['answer_content']['rule']['norms'][0]['kind'] == kind
    assert out['model_proposal']['norm_label_corrections'] == []

def test_source_ref_must_belong_to_norm_evidence():
    options = [{'id': x, 'source_id': x, 'text': '신고할 수 있다.'} for x in ('S1', 'S2')]
    with pytest.raises(ProposalError, match='selected evidence_refs'):
        accepted(proposal(ref='S2'), options)

def test_bound_original_receipt_cannot_be_substituted():
    out = accepted(proposal(), [{'id': 'S1', 'source_id': 's', 'text': '신고할 수 있다.'}])
    bad = deepcopy(out['claims'][0]); bad['span_receipts'][0]['text'] = '다른 원문'
    with pytest.raises(ContractError, match='receipt'): v5.verify_content(bad)

def test_same_source_role_is_written_once_even_after_label_correction():
    p = proposal(kind='OBLIGATION'); second = deepcopy(p['claims'][0]); second['claim_id'] = 'C2'
    second['rule']['norms'][0]['kind'] = 'PERMISSION'; p['claims'].append(second)
    with pytest.raises(ProposalError, match='Repeated source clause'):
        accepted(p, [{'id': 'S1', 'source_id': 's', 'text': '신고할 수 있다.'}])

def test_different_effects_may_share_a_mixed_original_paragraph():
    quote = '허가를 받아야 한다. 다만 신고로 갈음할 수 있다.'
    p = proposal('허가를 받아야 한다.', 'OBLIGATION')
    second = deepcopy(p['claims'][0]); second['claim_id'] = 'C2'
    second['rule']['norms'][0].update(kind='PERMISSION', text='신고로 갈음할 수 있다.')
    p['claims'].append(second)
    assert len(accepted(p, [{'id': 'S1', 'source_id': 's', 'text': quote}])['claims']) == 2

def test_authored_text_reversal_is_not_silently_corrected():
    with pytest.raises(ProposalError, match='wording reverses'):
        accepted(proposal('신고하여야 한다.', 'OBLIGATION'),
                 [{'id': 'S1', 'source_id': 's', 'text': '신고할 수 있다.'}])

class SpanTransport(SingleTransport):
    def send_once(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']; phase = view.get('source_stage', view['phase'])
        if phase.startswith('memory-assess'):
            self.phases.append(phase)
            options = view['evidence_options']; ref = next(o['id'] for o in options if '승인 후 보고한다.' in o['text'])
            out = proposal('승인 후 보고한다.', 'OBLIGATION', [o['id'] for o in options], ref)
            if self.reentry and not view['gap_history']:
                out['gaps'] = [deepcopy(GAP)]
                if getattr(self,'mixed_gap',False):
                    c=deepcopy(out['claims'][0]);c.update(claim_id='C2',rule=None,
                        explanation='요청한 원문을 추가로 확인해야 합니다.')
                    out['claims'].append(c)
            return wire(out)
        return super().send_once(body=body, ticket=ticket)

@pytest.mark.parametrize('mixed_gap', [False, True])
@pytest.mark.parametrize('direct_note', [False, True])
@pytest.mark.parametrize('reentry,reject_once', [(False, False), (True, False), (False, True)])
def test_native_v8_source_ids_publication_repair_reentry_reuse(tmp_path, tree, direct_note, reentry, reject_once, mixed_gap):
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    gen, idx = tree; transport = SpanTransport(reentry, reject_once); transport.direct_note = direct_note; transport.mixed_gap = mixed_gap
    profile = {**settings(), 'max_model_attempts': 40, 'max_read_chars': 10000,
        'candidate_navigation': {'mode': 'law-first-v1', 'investigation_control': True,
        'completion_contract': True, 'completion_policy_version': cc.V8, 'compact_input': True}}
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport,
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 't', 'document_ids': ['d']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    with TestClient(app) as api:
        body = {'question': '모의승인규정 제1조 승인 기준은?', 'session_id': 'v8', 'request_id': 'r1'}
        out = ok(api.post('/v1/rag/ask', json=body)); calls = len(transport.phases)
        assert out['assembly']['term_agent']['completion_contract'] == cc.V8
        assert out['assembly']['term_agent']['accepted_outcome']['answer_coverage'] == 'COVERED'
        assert out['answer']['text'].count('승인 후 보고한다.') == 1
        assert '미열람 미확인 메모' not in out['answer']['text']
        assert len(out['assembly']['term_agent']['case']['judgment_refs']) == 7
        again = ok(api.post('/v1/rag/ask', json=body))
        assert again['answer'] == out['answer'] and len(transport.phases) == calls
        if reentry:
            assert transport.phases.count('memory-assess') == 2
            assert '추가로 확인해야' not in out['answer']['text']



def test_mixed_source_gap_reaches_investigation_without_publishing_as_final():
    options=[{'id':'S1','source_id':'s','text':'신고할 수 있다.'}]
    p=proposal();p['gaps']=[deepcopy(GAP)]
    c=deepcopy(p['claims'][0]);c.update(claim_id='C2',rule=None,explanation='추가 원문 확인 필요')
    p['claims'].append(c)
    out=accepted(p,options)
    assert out['disposition']=='NEEDS_INVESTIGATION'
    assert out['gaps'][0]['material'] is True
    for claim in out['claims']:v5.verify_content(claim)



@pytest.mark.parametrize('difference', ['effect','context'])
def test_shared_source_and_role_do_not_prove_duplicate_effect(difference):
    quote='신고할 수 있다. 변경할 수 있다.'
    p=proposal();c=deepcopy(p['claims'][0]);c['claim_id']='C2'
    if difference=='effect':c['rule']['norms'][0]['text']='변경할 수 있다.'
    else:c['rule']['condition_tree']={'mode':'LEAF','text':'변경의 경우','evidence_refs':['S1']}
    p['claims'].append(c)
    out=accepted(p,[{'id':'S1','source_id':'s','text':quote}])
    assert len(out['claims'])==2
    assert out['claims'][1]['answer_content']['rule']['norms'][0]['text']==c['rule']['norms'][0]['text']
    for claim in out['claims']:v5.verify_content(claim)
