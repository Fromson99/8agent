"""Internal review status must not replace substantive user-facing gaps."""
from copy import deepcopy

import pytest

from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent.errors import ContractError
from test_gap_reason_presentation import assessment
from test_main50_request_repair import tree


def add_internal(value):
    item={'id':'L-requirement-review','kind':'EXECUTION_LIMIT','issue_id':None,
          'text':'질문 전체의 요구별 원문 충족 검토를 완료하지 못했습니다. 확인한 원문 범위만 제공합니다.'}
    value['limitation_items'].append(item)
    value['limitations'].append(item['text'])
    value['answer_coverage']='PARTIAL'
    value['disposition']='LIMITED_ANSWER'
    return item['text']


@pytest.mark.parametrize('with_gap',[False,True])
def test_new_answers_hide_only_internal_receipts_and_preserve_assessment(with_gap):
    a,issues=assessment()
    if not with_gap:
        a['gaps']=[]
        cc.refresh_limitations(a,issues)
    diagnostic=add_internal(a);before=deepcopy(a)
    answer=cc.compose(a,cc.default_plan(a))
    assert diagnostic not in answer['text']
    assert a==before and answer['claims']==a['claims']
    assert diagnostic in answer['limitations']
    assert a['answer_coverage']=='PARTIAL' and a['disposition']=='LIMITED_ANSWER'
    if with_gap:
        assert a['gaps'][0]['reason'] in answer['text']
        assert cc.public_limitations(a,answer['composition_plan'])
    else:
        assert '확인 범위' not in answer['text']
        assert cc.public_limitations(a,answer['composition_plan'])==[]
    cc.verify_composition(a,answer)


def test_old_saved_plan_keeps_diagnostic_and_verifies_without_rewriting():
    a,_=assessment();diagnostic=add_internal(a)
    answer=cc.compose(a,cc.default_plan(a))
    answer['composition_plan'].pop('limitation_presentation')
    answer['text']=cc.render(a,answer['composition_plan'])
    before=deepcopy(answer)
    assert diagnostic in answer['text']
    cc.verify_composition(a,answer)
    assert answer==before


def test_same_words_are_not_hidden_when_they_also_describe_a_substantive_gap():
    a,_=assessment();diagnostic=add_internal(a)
    a['limitation_items'].append({'id':'L-fact','kind':'MISSING_FACT','issue_id':'Q1','text':diagnostic})
    assert diagnostic in cc.compose(a,cc.default_plan(a))['text']


def test_unknown_display_version_and_modified_claims_still_rejected():
    a,_=assessment();add_internal(a)
    answer=cc.compose(a,cc.default_plan(a))
    altered=deepcopy(answer);altered['composition_plan']['limitation_presentation']='unknown'
    with pytest.raises(ContractError):cc.verify_composition(a,altered)
    altered=deepcopy(answer);altered['claims'][0]['text']='근거 없는 확정 답변'
    with pytest.raises(ContractError):cc.verify_composition(a,altered)


def test_genos_shows_needed_fact_without_internal_table():
    from test_genos_chat_flow import workflow
    from semantic_runtime.legal_agent import review_explanation as review
    w=workflow()
    view=review.seal({'schema_version':'review-explanation-v1','actions':[
        {'kind':'REQUEST_FACT','actor':'USER','enabled':True,'fact_name':'승인 여부를 알려주세요.'},
        {'kind':'REVIEW_AGAIN','actor':'SYSTEM','enabled':True,'fact_name':None}]})
    body={'assembly':{'term_agent':{'review_explanation':view}}}
    text=w._review_explanation_text(body)
    assert '승인 여부' in text and '검토 상태' not in text and 'REVIEW_AGAIN' not in text
    body['assembly']['term_agent']['scenario_comparison']={
        'changes':{'금액':{'value':735000,'unit':'KRW'}},
        'comparisons':[{'node_id':'금액조건','before':{'status':'FALSE'},'after':{'status':'TRUE'}}],
        'unresolved':[{'reason':'승인 여부 미확인'}]}
    text=w._review_explanation_text(body)
    assert '735000' in text and 'FALSE' in text and 'TRUE' in text and '승인 여부 미확인' in text


def test_genos_hides_old_saved_diagnostic_only_in_verified_display():
    from test_genos_chat_flow import workflow
    w=workflow();a, _=assessment();diagnostic=add_internal(a)
    names=['INTENT','PLAN','RECALL','READ','SELECT','ASSESS','COMPOSE']
    case={'question_id':'G1','revision':1,'route_id':1,'judgment_refs':dict.fromkeys(names)}
    view={'schema_version':'judgment-view-v1','question_id':'G1','question_revision':1,'route_id':1,
          'stages':[{'stage':name,'judgment_ref':None,'limitations':a['limitations'],
                     'limitation_items':a['limitation_items']} for name in names]}
    view['content_sha256']=w._workflow_display_digest(view)
    old='확인된 답변.\n\n확인 범위\n\n'+'\n'.join('- '+text for text in a['limitations'])
    body={'answer':{'text':old},'assembly':{'term_agent':{'case':case,'judgment_view':view}}}
    before=deepcopy(body)
    text=w._public_answer_text(body)
    assert diagnostic not in text and a['limitations'][0] in text and '확인된 답변.' in text
    assert body==before
    view['content_sha256']='invalid'
    assert diagnostic in w._public_answer_text(body)


def test_native_api_and_duplicate_hide_diagnostic_but_keep_partial_receipt(tmp_path,tree,monkeypatch):
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent import narrative_answer as narrative
    from semantic_runtime.legal_agent.answer_stream import capture
    from test_narrative_answer import RichTransport
    from test_bounded_source_main import settings
    from test_legal_agent_double_harness import ROOT
    from test_main50_request_repair import GAP
    refresh=cc.refresh_limitations
    def limited(*args,**kwargs):
        value=refresh(*args,**kwargs)
        add_internal(value)
        return value
    monkeypatch.setattr(cc,'refresh_limitations',limited)
    gen,idx=tree;tokens=[];transport=RichTransport(tokens,False);transport.reentry=True
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,
        'final_review_enabled':False,'answer_presentation':narrative.VERSION,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,
            'completion_contract':True,'completion_policy_version':cc.V8,
            'compact_input':True,'assessment_reentry_limit':0}}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),
        implementation='legal-agent-unified-v6',legal_agent_profile=profile,
        legal_agent_transport=transport,runtime_root=tmp_path/'runtime',
        memory_identity=lambda _:{'user_id':'synthetic','team_id':'test_team','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    request={'question':'모의승인규정 제1조 승인 기준은?','session_id':'display','request_id':'r1'}
    with TestClient(app) as api:
        with capture(request['request_id'],tokens.append):
            response=api.post('/v1/rag/ask',json=request)
        assert response.status_code==200,response.text
        body=response.json();answer=body['answer']
        assert answer['claims'] and GAP['reason'] in answer['text']
        assert '질문 전체의 요구별' not in answer['text']
        assert answer['text']==''.join(x['text'] for x in tokens)
        assert answer['unresolved'] and body['assembly']['unresolved']
        assert all('질문 전체의 요구별' not in x['reason'] for x in answer['unresolved'])
        assert body['assembly']['term_agent']['accepted_outcome']['answer_coverage']=='PARTIAL'
        count=len(transport.phases)
        again=api.post('/v1/rag/ask',json=request)
        assert again.status_code==200,again.text
        assert again.json()['answer']==answer and len(transport.phases)==count
        changed=api.post('/v1/rag/ask',json={**request,'question':'다른 질문'})
        assert changed.status_code==409
