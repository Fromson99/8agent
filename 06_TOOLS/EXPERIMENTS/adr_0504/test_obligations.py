"""Synthetic contracts only: these assertions do not measure Gemma semantic quality."""
import json
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import pytest
from conftest import term_glossary
from test_legal_agent_double_harness import generation, BINDING, wire
from test_source_tiers_v4 import app_for, PROFILE
from test_tool_exploration_v3 import read, delivered, tool
from semantic_runtime.legal_agent.errors import ProposalError, StaleProposal, BudgetExhausted
from semantic_runtime.legal_agent import obligation_protocol
from semantic_runtime.legal_agent.question_obligations import ObligationSession
from semantic_runtime.legal_agent.repository import encoded

SETTINGS={**PROFILE,'question_obligations_enabled':True}

def plan(refs=('Q1',),context=()):
    return {'demands':[
        {'question_refs':list(refs),'requirement':'승인 대상을 분류하라','given_facts':['승인 신청이 있다'],'missing_fact':None},
        {'question_refs':list(refs),'requirement':'승인 요건 위반 여부를 판단하라','given_facts':[],'missing_fact':'신청서 제출 여부'}],
        'context_refs':list(context),'change_reason':'질문의 분류와 위반 판단을 분리'}
def decision(proposed=None,**kwargs):
    return {'question_plan':proposed,'source_selection':None,'actions':[],'assessments':[],
            'relation_assessments':[],'intent':'CONTINUE','reason':'질문 요구에 맞는 근거 확인',**kwargs}
def choices(v):return {'choices':[{'source':e['evidence'],'decision':'KEEP_CORE','reason':'모의 승인 원문'} for e in v['exact_evidence']]}
@contextmanager
def session(tmp_path,generation,question='승인 대상과 요건 위반 여부는?',profile=None):
    app=app_for(tmp_path,generation,profile=profile or SETTINGS);p=app.state.pipeline
    try:
        with p.term_agent.open_session({'question':question,'document_ids':['d'],'use_llm':True},query=p.plan(question,['d']),runtime=tmp_path/'runtime') as s:
            assert isinstance(s,ObligationSession)
            yield s
    finally:p.store.close()
def adopt_plan(s,proposed=None):
    v=s.view('investigate');delivered(s,v);s.apply_turn(v,decision(proposed or plan()))
    return v

def drafted(s,both=False):
    adopt_plan(s);read(s);v=s.view('investigate');delivered(s,v);s.commit_selection(v,choices(v));s.select({'retrieval':s.retrieval()})
    v=s.view('compose',required=s.packed['evidence_ids']);delivered(s,v)
    ids=[d['id'] for d in s.plan()['demands']]
    paragraphs=[{'text':'모의 승인 대상입니다.','evidence':s.packed['evidence_ids'],'question_refs':['Q1'],
                 'fact_dependencies':[],'relation_dependencies':[],'obligation_refs':[oid]} for oid in (ids if both else ids[:1])]
    s.commit_draft(v,{'paragraphs':paragraphs,'limitations':[]})
    return ids

def review(s,status='MISSING_FACT'):
    claims=s.work.heads('claim',current=True);ids=[d['id'] for d in s.plan()['demands']]
    v=s.view('review',required=s.packed['evidence_ids'],extra={'claims':claims});delivered(s,v)
    checks=[{'claim':h['entity_id'],'verdict':'SUPPORTED','evidence':h['payload']['evidence'],
             'issue':'원문 일치','reason':'모의 원문 확인','actions':[],'relation_checks':[]} for h in claims]
    rows=[{'obligation':oid,'status':'ANSWERED' if i==0 else status,
           'claims':[h['entity_id'] for h in claims if oid in h['payload']['obligation_refs']],
           'reason':'원문으로 분류 가능' if i==0 else '신청서 제출 사실을 알려주십시오','actions':[]} for i,oid in enumerate(ids)]
    return v,{'checks':checks,'question':{'status':'RESOLVED','question_refs':['Q1'],'reason':'모의 전체 검토'},'obligation_checks':rows}

def test_plan_reaches_all_model_views_without_extra_call(tmp_path,generation):
    with session(tmp_path,generation) as s:
        first=adopt_plan(s);assert first['original_question']==s.context.request['question']
        assert not s.gateway.transport.calls
        for phase in ('investigate','select_sources','compose','review'):
            v=s.view(phase);assert len(v['answer_obligations'])==2
            assert v['original_question']==s.context.request['question']
            assert all(d['id'].startswith('O') for d in v['question_plan']['demands'])
        assert not s.gateway.transport.calls

def test_background_is_context_not_an_answer_requirement(tmp_path,generation):
    with session(tmp_path,generation,question='승인 대상인가?\n업무 배경 설명') as s:
        refs=[q['id'] for q in s.context.pieces]
        adopt_plan(s,plan(refs[:1],refs[1:]));assert len(s.plan()['demands'])==2
        assert s.plan()['context_refs']==refs[1:]

@pytest.mark.parametrize('mutation',['missing_plan','unknown_question','uncovered_question','duplicate'])
def test_invalid_plan_cannot_mutate_state(tmp_path,generation,mutation):
    with session(tmp_path,generation,question='분류는?\n위반은?') as s:
        p=plan(['Q1','Q2']);v=s.view('investigate');delivered(s,v)
        if mutation=='missing_plan':p=None
        elif mutation=='unknown_question':p['context_refs']=['Q99']
        elif mutation=='uncovered_question':p=plan()
        elif mutation=='duplicate':p['demands'].append(deepcopy(p['demands'][0]))
        with pytest.raises(ProposalError):s.apply_turn(v,decision(p))
        assert s.plan() is None

def test_turn_replay_and_changed_plan_conflict(tmp_path,generation):
    with session(tmp_path,generation) as s:
        v=adopt_plan(s);assert s.apply_turn(v,decision(plan())) is False
        p=plan();p['demands'][0]['requirement']='다른 질문'
        with pytest.raises(ProposalError):s.apply_turn(v,decision(p))
        assert s.plan()['demands'][0]['requirement']=='승인 대상을 분류하라'

def test_plan_change_invalidates_claim_and_reviews_but_not_sources(tmp_path,generation):
    with session(tmp_path,generation) as s:
        drafted(s);v,r=review(s);s.commit_review(v,r)
        assert s.work.heads('review',current=True)
        p=plan();p['demands'][0]['given_facts'].append('추가 사실')
        adopt_plan(s,p)
        assert not s.work.heads('claim',current=True)
        assert not s.work.heads('review',current=True)
        assert not s.work.heads('obligation_review',current=True)
        assert s.work.heads('source_selection',current=True)
        assert s.question_review is None
        with pytest.raises(StaleProposal):s.commit_review(v,r)

def test_noop_plan_does_not_discard_supported_work(tmp_path,generation):
    with session(tmp_path,generation) as s:
        drafted(s);v,r=review(s);s.commit_review(v,r)
        p=plan();p['change_reason']='표현만 변경';adopt_plan(s,p)
        assert s.work.heads('claim',current=True) and s.work.heads('obligation_review',current=True)

def test_fake_resolved_becomes_partial_with_supported_claim_preserved(tmp_path,generation):
    with session(tmp_path,generation) as s:
        drafted(s);v,r=review(s);s.commit_review(v,r)
        assert s.question_review['status']=='MISSING_FACT'
        assert [r['status'] for r in s.obligation_status()]==['ANSWERED','MISSING_FACT']
        # Inspect existing finalizer without causing an additional model response.
        s.context.request['use_llm']=False
        result,control=s.answer_and_review({'request':s.context.request,'query':s.context.query,'retrieval':s.retrieval(),'selection':{},'assembly':{}})
        assert control['gate']=='CLARIFY'
        assert len(result['answer']['claims'])==1
        assert any('신청서 제출' in x['reason'] for x in result['answer']['unresolved'])
        assert result['assembly']['term_agent']['question_obligations']['items'][0]['evidence_ids']

@pytest.mark.parametrize('mutation',['missing','invented','unsupported','foreign_claim','empty_reason'])
def test_review_cannot_hide_or_fabricate_coverage(tmp_path,generation,mutation):
    with session(tmp_path,generation) as s:
        drafted(s);v,r=review(s)
        if mutation=='missing':r['obligation_checks'].pop()
        elif mutation=='invented':r['obligation_checks'][1]['obligation']='Ounknown'
        elif mutation=='unsupported':r['obligation_checks'][1]['status']='ANSWERED'
        elif mutation=='foreign_claim':r['obligation_checks'][1]['claims']=[r['checks'][0]['claim']]
        elif mutation=='empty_reason':r['obligation_checks'][1]['reason']='   '
        with pytest.raises(ProposalError):s.commit_review(v,r)
        assert not s.work.heads('review',current=True)

def test_complete_demands_accept_direct_answer(tmp_path,generation):
    with session(tmp_path,generation) as s:
        drafted(s,both=True);v,r=review(s,'ANSWERED');s.commit_review(v,r)
        assert s.question_review['status']=='RESOLVED'
        s.context.request['use_llm']=False
        result,control=s.answer_and_review({'request':s.context.request,'query':s.context.query,'retrieval':s.retrieval(),'selection':{},'assembly':{}})
        assert len(result['answer']['claims'])==2
        assert all(row['status']=='ANSWERED' for row in s.obligation_status())
        assert all('판단하라:' not in row['reason'] and '분류하라:' not in row['reason'] for row in result['answer']['unresolved'])
        # Inherited relation-coverage gates remain in force, independently of demands.

@pytest.mark.parametrize('status',['NEEDS_REWRITE','NEEDS_RESEARCH'])
def test_unanswered_demand_routes_to_existing_controller(tmp_path,generation,status):
    with session(tmp_path,generation) as s:
        drafted(s);v,r=review(s,status)
        if status=='NEEDS_RESEARCH':r['obligation_checks'][1]['actions']=[tool('search',target=s.sources.root,query='승인 요건',mode='literal',cursor=None)]
        s.commit_review(v,r)
        if status=='NEEDS_RESEARCH':assert s.pending
        else:assert s.next_mode=='RECOMPOSE'
        assert s.question_review['status']=='PARTIAL'

def test_draft_cannot_invent_obligation_id(tmp_path,generation):
    with session(tmp_path,generation) as s:
        drafted(s);v=s.view('compose',required=s.packed['evidence_ids']);delivered(s,v)
        p=deepcopy(s.work.heads('claim',current=True)[0]['payload']);p['obligation_refs']=['Ounknown']
        with pytest.raises(ProposalError):s.commit_draft(v,{'paragraphs':[p],'limitations':[]})
        assert s.work.heads('claim',current=True)

def test_plan_is_in_context_budget_not_appended_after_packing(tmp_path,generation):
    with session(tmp_path,generation) as s:
        adopt_plan(s);s.profile['max_context_chars']=400
        with pytest.raises(BudgetExhausted):s.view('investigate')

def test_candidate_gemma_policy_and_wire_schema_are_explicit(tmp_path,monkeypatch):
    import httpx
    from lawrag.research.experiment_client import ExperimentClient
    R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0504-gemma-numbered-reference-wiring'
    monkeypatch.setenv('OPEN_ROUTER','offline-contract-key-not-a-secret')
    sent=[]
    def transport(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200,json={'model':'google/gemma-4-31b-it','provider':'DeepInfra','choices':[{'finish_reason':'stop','message':{'content':'{}'}}],'usage':{'prompt_tokens':1,'completion_tokens':1}})
    client=ExperimentClient(R,tmp_path/'calls',scoped_policy=A/'artifacts/gemma-policy.json',transport=httpx.MockTransport(transport))
    body={'model':client.model,'messages':[{'role':'user','content':'synthetic'}],'response_format':{'type':'json_schema','json_schema':{'name':'fixture','strict':True,'schema':{'type':'object','properties':{'uniqueItems':{'type':'array','uniqueItems':True,'items':{'type':'string'}}},'required':['uniqueItems'],'additionalProperties':False}}}}
    before=deepcopy(body);client.chat_completions(body)
    assert body==before
    schema=sent[0]['response_format']['json_schema']['schema']
    assert 'uniqueItems' in schema['properties'] and 'uniqueItems' not in schema['properties']['uniqueItems']
    assert sent[0]['model']=='google/gemma-4-31b-it'
    assert sent[0]['provider']['only']==['deepinfra/fp8'] and not sent[0]['reasoning']['enabled']
    with pytest.raises(ValueError):client.chat_completions({**body,'model':'qwen/qwen3.5-122b-a10b'})
    assert len(sent)==1

@pytest.mark.parametrize('numbered',[False,True])
def test_http_question_to_claim_to_review_uses_existing_phases(tmp_path,generation,numbered):
    def reply(value):
        if numbered:
            def convert(v):
                if isinstance(v,list):return [convert(x) for x in v]
                if isinstance(v,dict):return {k:[1 if x=='Q1' else x for x in val] if k in ('question_refs','context_refs') else convert(val) for k,val in v.items()}
                return v
            value=convert(value)
        return wire(value)

    from fastapi.testclient import TestClient
    class Transport:
        binding=BINDING
        def __init__(self):self.calls=[]
        def validate_model(self):return {'verified':True,'synthetic':True}
        def send_once(self,*,body,ticket):
            self.calls.append(body);v=json.loads(body['messages'][1]['content'])['view'];phase=v['phase']
            if phase=='select_sources':return reply(choices(v))
            if phase=='compose':
                oid=v['question_plan']['demands'][0]['id'];eid=v['exact_evidence'][0]['evidence']
                return reply({'paragraphs':[{'text':'모의 승인 대상입니다.','evidence':[eid],'question_refs':['Q1'],'fact_dependencies':[],'relation_dependencies':[],'obligation_refs':[oid]}],'limitations':[]})
            if phase=='review':
                c=v['claims'][0];ids=[d['id'] for d in v['question_plan']['demands']]
                return reply({'checks':[{'claim':c['claim'],'verdict':'SUPPORTED','evidence':c['evidence'],'issue':'원문 일치','reason':'모의 원문 확인','actions':[],'relation_checks':[]}],
                    'question':{'status':'RESOLVED','question_refs':['Q1'],'reason':'분류 확인'},
                    'obligation_checks':[{'obligation':oid,'status':'ANSWERED' if i==0 else 'MISSING_FACT','claims':[c['claim']] if i==0 else [],'reason':'분류 확인' if i==0 else '신청서 제출 사실 필요','actions':[]} for i,oid in enumerate(ids)]})
            if v['question_plan'] is None:
                return reply(decision(plan(),actions=[tool('locate',target=v['corpus_root'],locator='모의승인규정 제1조',branch='any',cursor=None)]))
            if not v['exact_evidence']:
                target=next(o['items'][0]['target'] for o in v['last_action_results'] if o['tool']=='locate')
                return reply(decision(actions=[tool('read',target=target,extent='subtree',cursor=None)]))
            return reply(decision(source_selection=choices(v),intent='DRAFT'))
    t=Transport();app=app_for(tmp_path,generation,t,{**SETTINGS,"numbered_references_enabled":numbered})
    with TestClient(app) as client:
        r=client.post('/v1/rag/ask',json={'question':'승인 대상과 위반 여부는?','document_ids':['d']})
        assert r.status_code==200,r.text
        value=r.json();assert value['answer']['claims']
        items=value['assembly']['term_agent']['question_obligations']['items']
        assert [i['status'] for i in items]==['ANSWERED','MISSING_FACT']
        assert '신청서 제출' in value['answer']['text']
    phases=[json.loads(b['messages'][1]['content'])['view']['phase'] for b in t.calls]
    assert phases==['investigate','investigate','investigate','select_sources','compose','review']
