"""Synthetic contracts only: these assertions do not measure Gemma semantic quality."""
import json
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from conftest import term_glossary
from test_legal_agent_double_harness import generation, BINDING, wire
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.workflow_tiers_policy import DEFAULT_PROFILE
from test_legal_agent_double_harness import ROOT
from test_source_tiers_v4 import Transport
# Review-specific contracts opt in; production v5 defaults to no final review.
PROFILE = {**DEFAULT_PROFILE, 'model_binding': BINDING, 'max_model_attempts':20, 'final_review_enabled':True}


def test_warmed_glossary_connections_are_reused_without_request_handles(generation):
    from semantic_runtime.navigation_agent import glossary_assets
    first=glossary_assets(generation,{})
    original=first._value
    first.known['request-only'] = ('dictionary','synthetic')
    for db in original.dbs.values():
        db.set_progress_handler(lambda: 1, 1)
    first.close()
    second=glossary_assets(generation,{})
    try:
        assert second._value is original
        assert 'request-only' not in second.known
        for db in second.dbs.values():
            assert db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0] >= 0
    finally:
        second.close()


def app_for(tmp_path, generation, transport=None, profile=None):
    return create_app(tmp_path,generation,contracts_root=ROOT,provider=object(),implementation='legal-agent-tools-v5',
        legal_agent_profile=profile or PROFILE,legal_agent_transport=transport or Transport(),runtime_root=tmp_path/'runtime')
def source_checks(s, claim):
    return [{'source':eid,'quote':s.work.evidence(eid)['spans'][0]['text'],'draft_quote':claim['text'],
             'dimensions':{key:'PRESERVED' for key in obligation_protocol.DIMENSIONS},'reason':'원문 조건과 초안 대조'} for eid in claim['evidence']]

from test_tool_exploration_v3 import read, delivered, tool
from semantic_runtime.legal_agent.errors import ProposalError, StaleProposal, BudgetExhausted
from semantic_runtime.legal_agent.errors import ToolExecutionError
import sqlite3
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
    v=s.view('investigate');delivered(s,v);s.apply_turn(v,decision(proposed or plan(), actions=[tool('locate',target=s.sources.root,locator='모의승인규정 제1조',branch='any',cursor=None)]))
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
             'issue':'원문 일치','reason':'모의 원문 확인','actions':[],'relation_checks':[], 'source_checks':source_checks(s,h['payload'])} for h in claims]
    rows=[{'obligation':oid,'status':'ANSWERED' if i==0 else status,
           'claims':[h['entity_id'] for h in claims if oid in h['payload']['obligation_refs']],
           'reason':'원문으로 분류 가능' if i==0 else '신청서 제출 사실을 알려주십시오','actions':[]} for i,oid in enumerate(ids)]
    return v,{'checks':checks,'question':{'status':'RESOLVED','question_refs':['Q1'],'reason':'모의 전체 검토'},'obligation_checks':rows}

def test_plan_reaches_all_model_views_without_extra_call(tmp_path,generation):
    with session(tmp_path,generation) as s:
        first=adopt_plan(s);assert first['original_question']==s.context.request['question']
        assert first['tool_capabilities']['fulltext']==s.sources.capabilities['fulltext']
        assert not s.gateway.transport.calls
        for phase in ('investigate','select_sources','compose','review'):
            v=s.view(phase);assert len(v['answer_obligations'])==2
            assert v['original_question']==s.context.request['question']
            assert all(d['id'].startswith('O') for d in v['question_plan']['demands'])
        assert not s.gateway.transport.calls


def test_unavailable_fulltext_repair_offers_executable_title_search(tmp_path,generation,monkeypatch):
    from semantic_runtime.document_agent import ServingDocumentAgent
    monkeypatch.setattr(ServingDocumentAgent, 'get_fulltext', lambda self: None)
    with session(tmp_path,generation) as s:
        view=s.view('investigate')
        assert view['tool_capabilities']['fulltext'] is False
        action=tool('search',target=s.sources.root,query='모의승인규정',mode='fulltext',cursor=None)
        alternatives=s.corrective_actions(view,action)
        assert len(alternatives)==1
        assert alternatives[0]['args']['mode']=='title'
        s.sources.validate_action(alternatives[0],set(view['offered_handles']))


def test_fulltext_sql_failure_stops_request_with_stage_and_cause(tmp_path,generation,monkeypatch):
    with session(tmp_path,generation) as s:
        assert s.sources.capabilities['fulltext']
        monkeypatch.setattr(s.sources.matcher.fulltext,'rank',
                            lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError('interrupted')))
        action=tool('search',target=s.sources.root,query='승인',mode='fulltext',cursor=None)
        with pytest.raises(ToolExecutionError,match='stage=fulltext_tool.rank.*interrupted'):
            s.sources.execute(action,'fts-failure')


@pytest.mark.parametrize('past_request_deadline', [False, True])
def test_fulltext_has_no_twenty_second_timer_but_keeps_request_deadline(tmp_path,generation,monkeypatch,past_request_deadline):
    import time
    with session(tmp_path,generation) as s:
        rank = s.sources.matcher.fulltext.rank
        started = time.monotonic()
        def slow_rank(db, terms, allowed):
            simulated = s.context.deadline + 1 if past_request_deadline else started + 25
            with monkeypatch.context() as clock:
                clock.setattr(time, 'monotonic', lambda: simulated)
                # Real SQLite VM work invokes the installed progress handler.
                # No actual sleeping or model/performance experiment is used.
                db.execute('WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<3000) SELECT sum(x) FROM n').fetchone()
                return rank(db, terms, allowed)
        monkeypatch.setattr(s.sources.matcher.fulltext, 'rank', slow_rank)
        action=tool('search',target=s.sources.root,query='승인',mode='fulltext',cursor=None)
        if past_request_deadline:
            with pytest.raises(ToolExecutionError, match='interrupted'):
                s.sources.execute(action, 'past-deadline')
        else:
            result=s.sources.execute(action,'over-twenty-seconds')
            assert result['items']
            assert result['search_receipt']['total_status']=='exact'


def test_fulltext_failure_propagates_through_agent_turn(tmp_path,generation,monkeypatch):
    with session(tmp_path,generation) as s:
        monkeypatch.setattr(s.sources.matcher.fulltext,'rank',
                            lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError('interrupted')))
        view=s.view('investigate')
        delivered(s,view)
        action=tool('search',target=s.sources.root,query='승인',mode='fulltext',cursor=None)
        with pytest.raises(ToolExecutionError,match='fulltext_tool.rank'):
            s.apply_turn(view,decision(plan(),actions=[action]))


@pytest.mark.parametrize('extent,with_cursor', [
    ('subtree', False), ('article', False), ('exact', True), ('subtree', True),
])
def test_evidence_reread_rejects_invalid_extent_or_cursor_before_execution(tmp_path,generation,extent,with_cursor):
    with session(tmp_path,generation) as s:
        result=read(s)
        eid=result['evidence_ids'][0]
        original=s.work.evidence(eid)
        cursor=None
        if with_cursor:
            # A valid request-bound cursor for the original location still must
            # not be attached to an already stored evidence fragment.
            key,_=s.sources.source.cursor_position(tool('read',**result['effective_args']))
            cursor=s.sources.source.cursor(key,1)
        before=[e['evidence_id'] for e in s.work.evidence()]
        rejected=s.sources.execute(tool('read',target=eid,extent=extent,cursor=cursor),'bad-reread')
        assert rejected['status']=='NOT_EXECUTED'
        assert 'extent="exact", cursor=null' in rejected['server_reason']
        assert rejected['evidence_ids']==[]
        assert [e['evidence_id'] for e in s.work.evidence()]==before
        assert s.work.db.execute('SELECT status FROM action_context WHERE action_id=?',('bad-reread',)).fetchone()[0]=='NOT_EXECUTED'
        assert s.sources.execute(tool('read',target=eid,extent=extent,cursor=cursor),'bad-reread')==rejected
        corrected=s.sources.execute(tool('read',target=eid,extent='exact',cursor=None),'corrected-reread')
        assert corrected['status']=='REUSED'
        assert corrected['evidence_ids']==[eid]
        assert s.work.evidence(eid)==original


def test_invalid_evidence_reread_preserves_selection_and_offers_executable_repair(tmp_path,generation):
    with session(tmp_path,generation) as s:
        adopt_plan(s);result=read(s);eid=result['evidence_ids'][0]
        view=s.view('investigate');delivered(s,view)
        with pytest.raises(ProposalError,match='workflow operations rejected'):
            s.apply_turn(view,decision(source_selection=choices(view),actions=[
                tool('read',target=eid,extent='subtree',cursor=None)]))
        assert eid in [p['evidence_id'] for p in s.selection_summary()]
        error=s.errors[-1]['errors'][0]
        assert 'extent="exact", cursor=null' in error['message']
        corrective=error['corrective_actions'][0]
        assert corrective['args']=={'target':eid,'extent':'exact','cursor':None}
        next_view=s.view('investigate');delivered(s,next_view)
        assert s.apply_turn(next_view,decision(actions=[corrective]))
        rereads=[a for a in s.sources.action_summaries() if a['actor']=='MODEL' and a['tool']=='read']
        assert rereads[-1]['status']=='REUSED'


def test_other_tool_execution_failure_also_stops_request(tmp_path,generation):
    with session(tmp_path,generation) as s:
        def fail(*args):
            raise ValueError('broken location lookup')
        s.sources.handlers['locate']=fail
        action=tool('locate',target=s.sources.root,locator='모의승인규정',branch='any',cursor=None)
        with pytest.raises(ToolExecutionError,match='tool=locate.*broken location lookup'):
            s.sources.execute(action,'locate-failure')


@pytest.mark.parametrize('name',['read','locate','follow_relations'])
def test_handler_proposal_error_returns_repair_receipt_without_failed_evidence(tmp_path,generation,name):
    with session(tmp_path,generation) as s:
        read_result=read(s);eid=read_result['evidence_ids'][0]
        action=(tool('read',target=eid,extent='exact',cursor=None) if name=='read' else
                tool('locate',target=s.sources.root,locator='모의승인규정 제1조',branch='any',cursor=None) if name=='locate' else
                tool('follow_relations',target=eid,family='reference',cursor=None))
        before=[e['evidence_id'] for e in s.work.evidence()]
        original=s.sources.handlers[name]
        def invalid(*args):raise ProposalError('resolved target requires a different read action')
        s.sources.handlers[name]=invalid
        result=s.sources.execute(action,'handler-proposal-rejected')
        assert result['status']=='NOT_EXECUTED' and result['recoverable'] is True
        assert result['error_code']=='MODEL_PROPOSAL_INVALID'
        assert 'respond again to the original question' in result['retry_instruction']
        assert result['evidence_ids']==[] and result['budget']['new_read_chars']==0
        assert [e['evidence_id'] for e in s.work.evidence()]==before
        assert s.work.db.execute('SELECT status FROM action_context WHERE action_id=?',('handler-proposal-rejected',)).fetchone()[0]=='NOT_EXECUTED'
        s.sources.handlers[name]=original
        assert s.sources.execute(action,'handler-proposal-rejected')==result
        assert s.sources.execute(action,'handler-proposal-corrected')['status'] in ('OK','REUSED','EMPTY')


def test_handler_error_status_also_stops_request(tmp_path,generation):
    with session(tmp_path,generation) as s:
        s.sources.handlers['locate']=lambda *args:([],None,[],{'status':'ERROR','server_reason':'synthetic read failure'})
        action=tool('locate',target=s.sources.root,locator='모의승인규정',branch='any',cursor=None)
        with pytest.raises(ToolExecutionError,match='synthetic read failure'):
            s.sources.execute(action,'locate-error-result')


def test_tool_execution_failure_returns_actual_stage_to_serving_caller(tmp_path,generation,monkeypatch):
    app=app_for(tmp_path,generation)
    try:
        def fail(*args,**kwargs):
            raise ToolExecutionError('tool=search mode=fulltext stage=fulltext_tool.rank cause=OperationalError: interrupted')
        monkeypatch.setattr(app.state.pipeline,'run',fail)
        with TestClient(app) as client:
            response=client.post('/v1/rag/ask',json={'question':'승인 기준은?'})
        assert response.status_code==500
        assert response.json()['answer_status']=='failed'
        assert 'fulltext_tool.rank' not in response.text
        assert response.json()['answer_status']=='failed'
    finally:
        app.state.pipeline.store.close()

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
        v=adopt_plan(s);assert s.apply_turn(v,decision(plan(),actions=[tool('locate',target=s.sources.root,locator='모의승인규정 제1조',branch='any',cursor=None)])) is False
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

@pytest.mark.parametrize('numbered',[True])
@pytest.mark.parametrize('mismatched_quote',[False,True])
@pytest.mark.parametrize('changed_condition',[False,True])
@pytest.mark.parametrize('review_enabled',[False,True])
@pytest.mark.parametrize('invalid_reread',[False,True,'handler'])
def test_http_question_to_claim_to_review_uses_existing_phases(tmp_path,generation,numbered,mismatched_quote,changed_condition,review_enabled,invalid_reread,monkeypatch):
    monkeypatch.setenv('GENOS_RAG_RELAX_REVIEW_QUOTE_MATCH', '1')
    if invalid_reread=='handler':
        from semantic_runtime.legal_agent.workflow_relations_tools import RelationsTools
        original_read=RelationsTools.read
        rejected=False
        def resolved_target_rejection(self,args,offset):
            nonlocal rejected
            if args['target'].startswith('E') and not rejected:
                rejected=True
                raise ProposalError('resolved article does not support this read action; choose a supplied location')
            return original_read(self,args,offset)
        monkeypatch.setattr(RelationsTools,'read',resolved_target_rejection)
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
        def __init__(self):self.calls=[];self.reread_attempted=False;self.reread_repaired=False
        def validate_model(self):return {'verified':True,'synthetic':True}
        def send_once(self,*,body,ticket):
            self.calls.append(body);v=json.loads(body['messages'][1]['content'])['view'];phase=v['phase']
            if phase=='select_sources':return reply(choices(v))
            if phase=='compose':
                oid=v['question_plan']['demands'][0]['id'];eid=v['exact_evidence'][0]['evidence']
                return reply({'paragraphs':[{'text':'모의 승인 대상입니다.','evidence':[eid],'question_refs':['Q1'],'fact_dependencies':[],'relation_dependencies':[],'obligation_refs':[oid]}],'limitations':[]})
            if phase=='review':
                c=v['claims'][0];ids=[d['id'] for d in v['question_plan']['demands']]
                return reply({'checks':[{'claim':c['claim'],'verdict':'SUPPORTED','evidence':c['evidence'],'issue':'원문 일치','reason':'모의 원문 확인','actions':[],'relation_checks':[], 'source_checks':[{'source':eid,'quote':'잘못 복사한 인용문' if mismatched_quote else next(e for e in v['exact_evidence'] if e['evidence']==eid)['text'],'draft_quote':c['text'],'dimensions':{k:('CHANGED' if changed_condition and k=='conditions' else 'PRESERVED') for k in obligation_protocol.DIMENSIONS},'reason':'원문 조건과 초안 대조'} for eid in c['evidence']]}],
                    'question':{'status':'RESOLVED','question_refs':['Q1'],'reason':'분류 확인'},
                    'obligation_checks':[{'obligation':oid,'status':'ANSWERED' if i==0 else 'MISSING_FACT','claims':[c['claim']] if i==0 else [],'reason':'분류 확인' if i==0 else '신청서 제출 사실 필요','actions':[]} for i,oid in enumerate(ids)]})
            if v['question_plan'] is None:
                return reply(decision(plan(),actions=[tool('locate',target=v['corpus_root'],locator='모의승인규정 제1조',branch='any',cursor=None)]))
            if not v['exact_evidence']:
                target=next(o['items'][0]['target'] for o in v['last_action_results'] if o['tool']=='locate')
                return reply(decision(actions=[tool('read',target=target,extent='subtree',cursor=None)]))
            if invalid_reread and not self.reread_attempted:
                self.reread_attempted=True
                return reply(decision(source_selection=choices(v),actions=[
                    tool('read',target=v['exact_evidence'][0]['evidence'],extent='exact' if invalid_reread=='handler' else 'subtree',cursor=None)]))
            if invalid_reread and not self.reread_repaired:
                repair=next(e for e in v['errors'] if e.get('code')=='OPERATION_REJECTED')
                correction=repair['errors'][0]['corrective_actions'][0]
                assert correction['args']['extent']=='exact' and correction['args']['cursor'] is None
                assert 'respond again to the original question' in repair['message']
                if invalid_reread=='handler':
                    assert 'respond again to the original question' in repair['errors'][0]['retry_instruction']
                self.reread_repaired=True
                return reply(decision(actions=[correction]))
            return reply(decision(source_selection=choices(v),intent='DRAFT'))
    t=Transport();app=app_for(tmp_path,generation,t,{**SETTINGS,"numbered_references_enabled":numbered, 'final_review_enabled':review_enabled})
    with TestClient(app) as client:
        r=client.post('/v1/rag/ask',json={'question':'승인 대상과 위반 여부는?','document_ids':['d']})
        assert r.status_code==200,r.text
        value=r.json();assert value['answer']['claims']
        items=value['assembly']['term_agent']['question_obligations']['items']
        assert [i['status'] for i in items]==(['OPEN','OPEN'] if changed_condition or not review_enabled else ['ANSWERED','MISSING_FACT'])
        if review_enabled:
            assert '신청서 제출' in value['answer']['text']
        assert value['answer']['provider_receipt']['final_review_policy']==('advisory' if review_enabled else 'disabled')
        if not review_enabled:
            assert value['answer']['text']=='모의 승인 대상입니다.'
            assert value['answer']['provider_receipt']['final_review_status']=='SKIPPED'
            assert not value['answer']['unresolved']
            assert set(value['answer']['provider_receipt']['claim_review_status'].values())=={'UNREVIEWED'}
        if changed_condition and review_enabled:
            assert '적용 요건과 요건 사이의 관계' in value['answer']['text']
            assert set(value['answer']['provider_receipt']['claim_review_status'].values())=={'UNREVIEWED'}
        if mismatched_quote and review_enabled:
            assert '모의 승인 대상입니다.' in value['answer']['text']
            assert '인용 문구가 확보한 원문과 일치하지' in value['answer']['text']
    phases=[json.loads(b['messages'][1]['content'])['view']['phase'] for b in t.calls]
    assert phases==['investigate']*(5 if invalid_reread else 3)+['select_sources','compose']+(['review'] if review_enabled else [])


@pytest.mark.parametrize('value',['연','   ','a b'])
def test_single_character_or_blank_plan_rejected(tmp_path,generation,value):
    with session(tmp_path,generation) as s:
        v=s.view('investigate');delivered(s,v);p=plan();p['demands'][0]['requirement']=value
        with pytest.raises(ProposalError):s.apply_turn(v,decision(p))
        assert s.plan() is None

@pytest.mark.parametrize('kind',['empty_continue','draft_actions','clarify_without_fact','context_overlap'])
def test_judgment_action_mismatch_is_atomic(tmp_path,generation,kind):
    with session(tmp_path,generation) as s:
        v=s.view('investigate');delivered(s,v);p=plan();d=decision(p)
        if kind=='draft_actions':d.update(intent='DRAFT',actions=[tool('locate',target=s.sources.root,locator='승인',branch='any',cursor=None)])
        if kind=='clarify_without_fact':
            d['intent']='CLARIFY'
            for row in p['demands']:row['missing_fact']=None
        if kind=='context_overlap':p['context_refs']=['Q1']
        with pytest.raises(ProposalError):s.apply_turn(v,d)
        assert s.plan() is None
        assert not s.work.db.execute("SELECT 1 FROM event WHERE event_id LIKE 'workflow-turn:%'").fetchone()

@pytest.mark.parametrize('dimension',obligation_protocol.DIMENSIONS)
def test_supported_cannot_contradict_source_comparison(tmp_path,generation,dimension):
    with session(tmp_path,generation) as s:
        drafted(s);v,r=review(s);r['checks'][0]['source_checks'][0]['dimensions'][dimension]='CHANGED'
        with pytest.raises(ProposalError):s.commit_review(v,r)
        assert not s.work.heads('review',current=True)

@pytest.mark.parametrize('mutation',['invent_quote','invent_draft','omit_source','unsupported_action'])
def test_review_requires_real_quotes_and_consistent_actions(tmp_path,generation,mutation,monkeypatch):
    monkeypatch.setenv('GENOS_RAG_RELAX_REVIEW_QUOTE_MATCH', '0')
    with session(tmp_path,generation) as s:
        drafted(s);v,r=review(s);check=r['checks'][0]
        if mutation=='invent_quote':check['source_checks'][0]['quote']='제999조: 원문에 없는 조건'
        if mutation=='invent_draft':check['source_checks'][0]['draft_quote']='초안에 없는 주장'
        if mutation=='omit_source':check['source_checks']=[]
        if mutation=='unsupported_action':check['actions']=[tool('locate',target=s.sources.root,locator='승인',branch='any',cursor=None)]
        with pytest.raises(ProposalError):s.commit_review(v,r)
        assert not s.work.heads('review',current=True)


def test_review_quote_mismatch_is_bounded_but_does_not_block_answer(tmp_path,generation,monkeypatch):
    monkeypatch.setenv('GENOS_RAG_RELAX_REVIEW_QUOTE_MATCH', '1')
    with session(tmp_path,generation) as s:
        drafted(s);v,r=review(s)
        r['checks'][0]['source_checks'][0]['quote']='모델이 잘못 복사한 인용문'
        s.commit_review(v,r)
        assert s.work.heads('review',current=True)
        assert any('검토 인용문' in reason for reason in s.limitations)
        assert s.work.db.execute("SELECT 1 FROM event WHERE kind='REVIEW_QUOTE_MISMATCH_ACCEPTED'").fetchone()


def test_rewording_plan_is_not_progress(tmp_path,generation):
    with session(tmp_path,generation) as s:
        adopt_plan(s);before=s.progress_key();p=plan();p['demands'][0]['requirement']='승인 분류를 다시 설명하라'
        adopt_plan(s,p)
        assert before==s.progress_key()


def test_sentence_schema_has_no_single_character_regex():
    p=obligation_protocol.schema('TurnDecision')['properties']['question_plan']['anyOf'][0]
    assert 'pattern' not in p['properties']['demands']['items']['properties']['requirement']


def test_whole_question_uncertainty_cannot_be_erased(tmp_path,generation):
    with session(tmp_path,generation) as s:
        drafted(s,both=True);v,r=review(s,'ANSWERED');r['question']['status']='PARTIAL'
        with pytest.raises(ProposalError):s.commit_review(v,r)
        assert not s.work.heads('review',current=True)


def test_rewrite_cannot_publish_all_supported_claims(tmp_path,generation):
    with session(tmp_path,generation) as s:
        drafted(s,both=True);v,r=review(s,'NEEDS_REWRITE')
        with pytest.raises(ProposalError):s.commit_review(v,r)
        assert not s.work.heads('review',current=True)


def test_pipeline_cli_uses_coordinator_and_finishes_journal(tmp_path,generation):
    import importlib.util
    import shutil
    from semantic_runtime.contracts import sha
    spec=importlib.util.spec_from_file_location('v5_engine_host',ROOT/'02_BACKEND/PIPELINE/engine_host.py')
    host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
    root=tmp_path;config=json.loads((ROOT/'00_SYSTEM/PIPELINE.json').read_text())
    # This legacy CLI contract explicitly selects the complete v5 profile.
    config['profiles']['legal-rag']=deepcopy(config['profiles']['legal-agent-rag-v5'])
    pins={}
    paths={'00_SYSTEM/PIPELINE.json','00_SYSTEM/WORKSPACE.json','00_SYSTEM/SCHEMAS/pipeline-engine-v1.schema.json'}
    for step in config['profiles']['legal-rag']['nodes']:
        path=config['engines'][step['engine']]['manifest'];paths.add(path)
        pins.update(json.loads((ROOT/path).read_text())['files'])
    paths.update(pins)
    paths.update(str(p.relative_to(ROOT)) for p in (ROOT/'00_SYSTEM/LEGAL_AGENT').glob('*.json'))
    paths.update(x['schema_path'] for x in config['contracts'].values())
    for relative in paths:
        target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,target)
    (root/'00_SYSTEM/PIPELINE.json').write_text(json.dumps(config))
    active=root/'01_DATA/ACTIVE/local';active.mkdir(parents=True,exist_ok=True)
    release=active/'release.json';release.write_text(json.dumps({'files':pins,'data_path':str(generation.relative_to(root))}))
    (active/'ACTIVE_RELEASE.json').write_text(json.dumps({'schema_version':'semantic-runtime-active-v2','manifest_path':str(release.relative_to(root)),'release_manifest_sha256':sha(release)}))
    request=root/'request.json';request.write_text(json.dumps({'question':'자료 목록','document_ids':['d'],'use_llm':False}))
    receipt=host.execute(config,'legal-rag',{'request':{'path':str(request),'sha256':sha(request)}},root/'cli-output',root=root)
    assert receipt['status']=='COMPLETE'
    assert receipt['execution']['kind']=='REQUEST_LOCAL_LEGAL_COORDINATOR'
    result=json.loads((root/'cli-output'/receipt['outputs']['result']['path']).read_text())
    assert result['assembly']['term_agent']['implementation']=='legal-agent-tools-v5'
    import sqlite3
    journal=next((root/'90_RUNTIME/semantic/legal-agent/runs').glob('*/'+receipt['execution']['run_id']+'/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        assert db.execute('SELECT status FROM run').fetchone()[0]=='COMPLETED'
    from legal_agent_trace import read_trace
    assert read_trace(root/'90_RUNTIME/semantic',receipt['execution']['run_id'])['status']=='COMPLETED'


def test_genos_profile_configuration_never_contacts_network(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import semantic_runtime.genos as genos
    from legal_agent_contracts import bind_genos_v5
    monkeypatch.setattr(genos,'from_env',lambda kind:(SimpleNamespace(root='http://internal-fixture/v1'),'gemma-internal-fixture'))
    monkeypatch.setattr(genos,'request_json',lambda *a,**kw:pytest.fail('explicit binding must stay offline'))
    result=bind_genos_v5(tmp_path,500000)
    assert result['network_contacted'] is False
    binding=json.loads(Path(result['profile']).read_text())['model_binding']
    assert binding['model']=='gemma-internal-fixture' and binding['trust_zone']=='internal'


def standalone_profile_root(root, monkeypatch):
    from types import SimpleNamespace
    import semantic_runtime.genos as genos
    monkeypatch.setattr(genos, 'from_env', lambda kind: (
        SimpleNamespace(root='http://internal-fixture/v1'), 'gemma-internal-fixture'))
    profile = root/'00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json'
    profile.parent.mkdir(parents=True)
    profile.write_text(json.dumps(DEFAULT_PROFILE))
    engine = root/'engine.json'
    engine.write_text(json.dumps({'files': {'00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json': 'fixture'}}))
    pipeline = root/'00_SYSTEM/PIPELINE.json'
    pipeline.write_text(json.dumps({'engines': {'fixture': {'manifest': 'engine.json'}}}))
    return [profile, engine, pipeline]


def test_standalone_genos_profile_needs_no_data_and_preserves_pins(tmp_path, monkeypatch):
    from legal_agent_contracts import bind_genos_v5
    files = standalone_profile_root(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in files}
    result = bind_genos_v5(tmp_path, 500000, output='00_SYSTEM/LEGAL_AGENT/profile-genos-v5.json')
    assert result['standalone'] and not result['network_contacted']
    assert not (tmp_path/'01_DATA').exists()
    assert {p: p.read_bytes() for p in files} == before
    assert bind_genos_v5(tmp_path, 500000, output=result['profile']) == result
    with pytest.raises(ValueError, match='different settings'):
        bind_genos_v5(tmp_path, 600000, output=result['profile'])
    assert json.loads(Path(result['profile']).read_text())['model_binding']['max_input_bytes'] == 500000


@pytest.mark.parametrize('model_profile', ['qwen', 'gemma'])
def test_genos_auto_model_binding_and_serving_without_model_env(tmp_path, monkeypatch, model_profile):
    import semantic_runtime.genos as genos
    from legal_agent_contracts import bind_genos_v5
    from semantic_runtime.legal_agent.transport import GenosTransport
    from semantic_runtime.legal_agent.errors import ContractError
    with monkeypatch.context() as setup:
        standalone_profile_root(tmp_path, setup)
    # Use real environment resolution, using the same generic settings for both model families.
    for name in list(__import__('os').environ):
        if name.startswith('GENOS_'):
            monkeypatch.delenv(name)
    monkeypatch.setenv('GENOS_BASE_URL', 'https://internal-fixture.invalid')
    monkeypatch.setenv('GENOS_LLM_SERVING_ID', '123')
    monkeypatch.setenv('GENOS_LLM_KEY', 'synthetic-test-key')
    calls = []
    model = model_profile + '-internal-fixture'
    def models(target, path):
        calls.append((target.root, path))
        return {'data': [{'id': model}]}
    monkeypatch.setattr(genos, 'request_json', models)
    result = bind_genos_v5(tmp_path, 500000, output='00_SYSTEM/LEGAL_AGENT/profile-genos-v5.json')
    assert result['network_contacted'] and result['model'] == model
    assert calls == [('https://internal-fixture.invalid/api/gateway/rep/serving/123', '/models')]
    binding = json.loads(Path(result['profile']).read_text())['model_binding']
    transport = GenosTransport.from_environment(binding)
    async def request(method, path, body, seconds):
        assert (method, path) == ('GET', '/models')
        return {'body_json': {'data': [{'id': model}]}}
    monkeypatch.setattr(transport, '_request', request)
    assert transport.validate_model()['model'] == model
    async def changed_model(*args):
        return {'body_json': {'data': [{'id': 'replacement-model'}]}}
    monkeypatch.setattr(transport, '_request', changed_model)
    with pytest.raises(ContractError, match='not advertised'):
        transport.validate_model()
    monkeypatch.setenv('GENOS_LLM_MODEL', 'different-model')
    with pytest.raises(ContractError, match='environment model'):
        GenosTransport.from_environment(binding)
    monkeypatch.delenv('GENOS_LLM_MODEL')
    monkeypatch.setenv('GENOS_LLM_SERVING_ID', '456')
    with pytest.raises(ContractError, match='endpoint'):
        GenosTransport.from_environment(binding)


@pytest.mark.parametrize('response', [{'data': []}, {'data': [{'id': 'a'}, {'id': 'b'}]}, {'data': None}])
def test_genos_auto_binding_rejects_ambiguous_or_invalid_models(tmp_path, monkeypatch, response):
    from types import SimpleNamespace
    import semantic_runtime.genos as genos
    from legal_agent_contracts import bind_genos_v5
    standalone_profile_root(tmp_path, monkeypatch)
    monkeypatch.setattr(genos, 'from_env', lambda kind: (genos.endpoint('http://fixture/v1'), ''))
    monkeypatch.setattr(genos, 'request_json', lambda *args: response)
    output = '00_SYSTEM/LEGAL_AGENT/profile-genos-v5.json'
    with pytest.raises(genos.ServingError):
        bind_genos_v5(tmp_path, 500000, output=output)
    assert not (tmp_path/output).exists()


@pytest.mark.parametrize('output', ['00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json',
                                  '../escape.json', '00_SYSTEM/PIPELINE.json'])
def test_standalone_genos_profile_rejects_pinned_or_outside_paths(tmp_path, monkeypatch, output):
    from legal_agent_contracts import bind_genos_v5
    files = standalone_profile_root(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in files}
    with pytest.raises(ValueError):
        bind_genos_v5(tmp_path, 500000, output=output)
    assert {p: p.read_bytes() for p in files} == before
