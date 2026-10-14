"""Behavioral contracts on synthetic originals; no model/legal quality claims."""
from copy import deepcopy
from pathlib import Path
import json
import sqlite3
import pytest
from jsonschema import validate, ValidationError
from test_unit_fulltext_adaptive_read import tree, session, hit
from test_law_grouped_navigation import prepared, enable, decide
from test_investigation_control_adr0674 import apply
from test_unified_legal_agent import ScriptedTransport, ok
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire
from semantic_runtime.legal_agent import law_navigation as ln, unit_reading as ur
from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent.errors import ContractError, BudgetExhausted, TransportError
from semantic_runtime.app import create_app
from fastapi.testclient import TestClient


def inv_for(native, uid='0'):
    s=native.sources;record=prepared(s)
    enable(s,investigation_control=True,completion_contract=True)
    native.profile['candidate_navigation']=dict(s.profile['candidate_navigation'])
    if native.gateway is None:
        from types import SimpleNamespace
        from test_legal_agent_double_harness import DOMAIN
        native.gateway=SimpleNamespace(domain=DOMAIN,transport=ScriptedTransport())
    s.profile['max_read_chars']=10000
    record['unit_reads']=ur.acquire_batch(s,[hit(native,uid)],record['read_state'])
    record['unit_hits']=[hit(native,uid)]
    return ln.Investigation(s,'모의승인규정 제1조 승인 기준',record,None,120,None,None)


def decision(data, action='PENDING', target=None):
    v=decide(data,action,target);v['expected_state_version']=data['state_version']
    if action in ('READ_ARTICLES','READ_PARENT','READ_SCOPE','VIEW_SAVED_SOURCE','DECIDE','FINISH'):v['law_decisions']=[]
    for row in v['branch_decisions']:
        row['basis_refs']=[p['id'] for p in data['sources'] if p['branch_id']==row['branch_id']]
    return v


def read(inv):
    data,actions=inv.view();card=data['articles'][0]
    apply(inv,decision(data,'READ_PARENT',card['read_parent_action']),data,actions)
    return card['id']


def mark(inv,gid,status='DEFER',issue='Q1'):
    data,actions=inv.view();v=decision(data,'DECIDE')
    v['branch_decisions']=[{'branch_id':gid,'status':status,'reason':'모의 쟁점 판단',
        'issue_refs':[issue],'basis_refs':[p['id'] for p in data['sources'] if p['branch_id']==gid] if status=='ADOPT' else []}]
    apply(inv,v,data,actions)
    return v


def test_current_adoption_schema_and_runtime_exclude_old_title(session):
    native,_=session;inv=inv_for(native);gid=read(inv);data,actions=inv.view()
    old=deepcopy(data['sources'][0]);old['id']='old-title-page'
    inv.p['basis_history'][old['id']]=old
    data,actions=inv.view();v=decision(data,'FINISH')
    v['branch_decisions'][0]['basis_refs']=['old-title-page']
    with pytest.raises(ValidationError):validate(v,ln.decision_schema(data,actions,inv.p['groups']))
    with pytest.raises(ValidationError):inv.validate(v,data,actions)
    valid=decision(data,'FINISH');inv.validate(valid,data,actions)


def test_read_is_separate_from_adopt_or_defer(session):
    native,_=session;inv=inv_for(native);data,actions=inv.view();card=data['articles'][0]
    v=decision(data,'READ_PARENT',card['read_parent_action'])
    v['branch_decisions']=[{'branch_id':card['id'],'status':'DEFER','reason':'보류','issue_refs':['Q1'],'basis_refs':[]}]
    with pytest.raises(ValidationError):inv.validate(v,data,actions)
    v['branch_decisions']=[];apply(inv,v,data,actions)
    assert inv.view()[0]['sources'] and not inv.result({'next_action':'PENDING','queries':[], 'reason':'확인중','sufficiency_reason':'','evidence_sufficient':False})['final_ids']


def test_saved_read_preserves_defer_and_actual_body_is_delivered(session):
    native,_=session;inv=inv_for(native);gid=read(inv);mark(inv,gid)
    before=deepcopy(inv.p['basis_history'])
    data,actions=inv.view();target=next(a['id'] for a in actions.values() if a['action']=='VIEW_SAVED_SOURCE')
    apply(inv,decision(data,'VIEW_SAVED_SOURCE',target),data,actions)
    assert inv.p['groups'][gid]['status']=='DEFERRED'
    view,_=inv.view();assert view['sources'] and '승인' in view['sources'][0]['text']
    assert inv.p['basis_history']==before
    assert view['saved_inventory'][0]['currently_presented']


def test_no_progress_stops_without_fabricating_adoption(session):
    native,_=session;inv=inv_for(native);gid=read(inv);mark(inv,gid)
    for _ in range(2):
        data,actions=inv.view();target=next(a['id'] for a in actions.values() if a['action']=='VIEW_SAVED_SOURCE')
        apply(inv,decision(data,'VIEW_SAVED_SOURCE',target),data,actions)
        mark(inv,gid)
    result=inv.run()
    assert result['status']=='pending' and result['stop_reason']=='NO_PROGRESS'
    assert result['final_ids']==[]


def test_new_issue_decision_is_progress(session):
    native,_=session;inv=inv_for(native);gid=read(inv);mark(inv,gid)
    inv.p['issues'].append({'id':'Q2','question':'새 보고 쟁점','kind':'OTHER','subject':''})
    inv.p['no_progress']=1;mark(inv,gid,issue='Q2')
    assert inv.p['no_progress']==0


def sources():
    text='모의 聯結 규칙\n다만 예외를 확인한다.'
    return [{'source_id':'s1','document_id':'d','text':text,'adopted_spans':[{'block_id':'1','start_cp':0,'end_cp':len(text),'text':text,'evidence_id':'E1'}]}]


def assess(gaps=None, status='COVERED'):
    src=sources();options=cc.evidence_options(src)
    v={'claims':[{'claim_id':'C1','text':'모의 규칙과 예외를 적용한다.','issue_refs':['Q1'],'evidence_refs':[o['id'] for o in options]}],
       'disposition':'LIMITED_ANSWER' if gaps else 'ANSWER','issue_assessments':[{'issue_id':'Q1','status':status,'reason':'원문 대조'}], 'gaps':gaps or []}
    return v,options,[{'id':'Q1','question':'승인 기준은?'}]


def test_span_compilation_preserves_unicode_and_multiple_segments():
    v,o,issues=assess();result=cc.materialize_assessment(v,o,issues)
    c=result['claims'][0];cc.verify_span_claim(c,sources())
    assert '聯' in c['quote'] and c['evidence']
    c['quote']=c['quote'].replace('聯','聯')
    with pytest.raises(ContractError,match='quote'):cc.verify_span_claim(c,sources())


def test_gap_errors_report_coverage_and_fact_action_together():
    gap={'issue_id':'Q1','kind':'MISSING_FACT','reason':'사실 미확인','material_id':None,'material':True,'suggested_action':'RESEARCH'}
    v,o,issues=assess([gap]);schema=cc.assessment_schema(issues,[],o)
    errors=cc.assessment_errors(v,schema,issues)
    assert any('REQUEST_FACT' in e for e in errors) and any('COVERED' in e for e in errors)


def test_diagnostic_reason_cannot_inject_legal_limitation():
    gap={'issue_id':'Q1','kind':'MISSING_SOURCE','reason':'유한회사 제270조에 따른 제한','material_id':None,'material':True,'suggested_action':'RESEARCH'}
    v,o,issues=assess([gap],'PARTIAL');a=cc.materialize_assessment(v,o,issues)
    answer=cc.compose(a,cc.default_plan(a));assert '270' not in answer['text']
    assert '추가 근거' in answer['text'] and answer['claims']==a['claims']
    assert '270' in a['gaps'][0]['reason']  # Immutable diagnostic retained separately.


@pytest.mark.parametrize('layout',['paragraphs','table','bullets'])
def test_closed_render_rejects_added_text_or_omitted_claim(layout):
    v,o,issues=assess();a=cc.materialize_assessment(v,o,issues)
    out=cc.compose(a,{'layout':layout,'claim_order':['C1']});cc.verify_composition(a,out)
    out['text']+=' 거래가 제한될 수 있습니다.'
    with pytest.raises(ContractError):cc.verify_composition(a,out)
    with pytest.raises(ContractError):cc.compose(a,{'layout':layout,'claim_order':[]})


def test_finalize_uses_actual_reserved_native_slot(session,monkeypatch):
    native,_=session;inv_for(native)
    native.work.db.execute('UPDATE budget SET model_limit=40,finalization_reserve=3,model_reserved=37')
    seen=[]
    def send_once(*,body,ticket):
        seen.append(json.loads(body['messages'][1]['content'])['view']);return wire({'ok':True})
    monkeypatch.setattr(native.gateway.transport,'send_once',send_once)
    schema=cc.obj({'ok':{'type':'boolean'}})
    assert native.structured('mock',{},schema,'memory-assess',30)=={'ok':True}
    assert seen[-1]['budget_class']=='FINALIZE' and seen[-1]['phase']=='compose'
    assert native.work.budget()['model_reserved']==38
    with pytest.raises(BudgetExhausted):native.structured('mock',{},schema,'source-test',30)


def test_unknown_transmission_is_not_retried(session,monkeypatch):
    native,_=session;inv_for(native);native.profile['max_transport_retries']=1;calls=[]
    def send_once(**kwargs):
        calls.append(1);raise TransportError('unknown',retryable=True,unknown=True)
    monkeypatch.setattr(native.gateway.transport,'send_once',send_once)
    with pytest.raises(TransportError):native.structured('mock',{},cc.obj({'ok':{'type':'boolean'}}),'source-test',30)
    assert len(calls)==1


def test_known_429_retries_once_with_original_status(session,monkeypatch):
    native,_=session;inv_for(native);native.profile['max_transport_retries']=1;calls=[]
    def send_once(**kwargs):
        calls.append(1)
        if len(calls)==1:raise TransportError('busy',retryable=True,response={'status_code':429})
        return wire({'ok':True})
    monkeypatch.setattr(native.gateway.transport,'send_once',send_once)
    monkeypatch.setattr('semantic_runtime.legal_agent.gateway.time.sleep',lambda _:None)
    assert native.structured('mock',{},cc.obj({'ok':{'type':'boolean'}}),'source-test',30)=={'ok':True}
    assert len(calls)==2


class CompletionTransport(ScriptedTransport):
    def send_once(self,*,body,ticket):
        v=json.loads(body['messages'][1]['content'])['view'];phase=v.get('source_stage',v['phase'])
        if phase=='memory-intent':
            self.phases.append(phase)
            return wire({'purpose':'승인 기준 확인','concepts':['승인'],'issues':[{'id':'Q1','question':'승인 기준은?','subject':'승인','kind':'OTHER'}]})
        if phase.startswith('source-law-navigation-'):
            self.phases.append(phase)
            if v['sources']:return wire(decision(v,'FINISH'))
            cards=[c for law in v['laws'] for c in law.get('articles',[])]
            card=next(c for c in cards if c.get('read_parent_action'))
            return wire(decision(v,'READ_PARENT',card['read_parent_action']))
        if phase.startswith('memory-assess'):
            self.phases.append(phase)
            return wire({'claims':[{'claim_id':'C1','rule':None,'text':'모의 승인 기준과 예외를 적용한다.','issue_refs':['Q1'],
                'evidence_refs':[o['id'] for o in v['evidence_options']]}], 'disposition':'ANSWER',
                'issue_assessments':[{'issue_id':'Q1','status':'COVERED','reason':'모의 원문 확인'}],'gaps':[]})
        return super().send_once(body=body,ticket=ticket)


def test_native_completion_publishes_closed_text_and_seven_refs(tmp_path,tree):
    gen,idx=tree;t=CompletionTransport()
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,
             'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True}}
    principal={'user_id':'u','team_id':'t','document_ids':['d']}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=t,memory_identity=lambda _:principal)
    app.state.pipeline.term_agent.unit_fulltext=idx
    with TestClient(app) as api:
        result=ok(api.post('/v1/rag/ask',json={'question':'모의승인규정 제1조 승인 기준은?','session_id':'s','request_id':'r1'}))
        assert result['answer']['text']=='모의 승인 기준과 예외를 적용한다.'
        assert result['assembly']['term_agent']['completion_contract']==cc.CONTRACT
        assert len(result['assembly']['term_agent']['case']['judgment_refs'])==7
        assert not any(p.startswith('memory-compose') for p in t.phases)
        assert result['answer']['provider_receipt']['final_review_status']=='SKIPPED'


@pytest.fixture
def completed_app(tmp_path,tree):
    gen,idx=tree;t=CompletionTransport()
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,'max_transport_retries':0,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True}}
    principal={'user_id':'u','team_id':'t','document_ids':['d']}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=t,memory_identity=lambda _:principal)
    app.state.pipeline.term_agent.unit_fulltext=idx
    with TestClient(app) as api:yield api,t,tmp_path/'90_RUNTIME/semantic'


def test_same_request_retries_keep_budget_and_original_deadline(completed_app,monkeypatch):
    api,t,runtime=completed_app;calls=[]
    def fail(**kwargs):
        calls.append(1);raise TransportError('busy',retryable=True,response={'status_code':429})
    monkeypatch.setattr(t,'send_once',fail)
    body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'s','request_id':'r1'}
    for _ in range(2):
        response=api.post('/v1/rag/ask',json=body)
        assert response.status_code==503,response.text
    journals=list((runtime/'legal-agent/runs').glob('*/*/journal.sqlite'))
    values=[]
    for p in journals:
        with sqlite3.connect(p) as db:
            values.append((db.execute('SELECT model_reserved FROM budget').fetchone()[0],db.execute('SELECT deadline_at FROM run').fetchone()[0]))
    assert sorted(v[0] for v in values)==[1,2] and len({v[1] for v in values})==1
    assert len(calls)==2
    response=api.post('/v1/rag/ask',json={**body,'request_id':'r2'})
    assert response.status_code==503,response.text
    from semantic_runtime.legal_agent.shortcut_store import selected_store
    with sqlite3.connect(selected_store(runtime)) as db:
        assert db.execute('SELECT count(*) FROM completion_request_budget').fetchone()[0]==2
        assert db.execute('SELECT count(*) FROM completion_request_run').fetchone()[0]==3
        assert db.execute('SELECT count(*) FROM route').fetchone()[0]==0


def test_completion_preserves_correction_table_history_and_experience(completed_app):
    from test_memory_runtime_v2 import command
    api,t,runtime=completed_app;count=0
    def send(c=None,**overrides):
        nonlocal count
        count+=1
        if c is not None:t.command=c
        return ok(api.post('/v1/rag/ask',json={'question':'모의승인규정 제1조 승인 기준은?',
            'session_id':'s','request_id':'r'+str(count),**overrides}))
    first=send();gid=first['question_id']
    corrected=send(command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'모의 A'}]))
    assert corrected['executed']==['ASSESS','COMPOSE']
    shown=send(command('ANSWER_PRESENT',target=gid,format='table'))
    assert '|' in shown['answer']['text'] and shown['executed']==['COMPOSE']
    history=send(command('HISTORY_EXPLAIN',target=gid))
    assert '수정 이력:' in history['answer']['text']
    assert history['assembly']['term_agent']['answer_presentation']['method_id']=='HISTORY_EXPLAIN'
    stored=send(command('EXPERIENCE_CONFIRM',target=gid));kid=stored['experience_id']
    reused=send(command('EXPERIENCE_REUSE',document_scope_mode='AUTHORIZED',knowledge_id=kid,
        task='모의승인규정 제1조의 승인 대상은?',facts=[{'name':'대상','value':'모의 A'}],queries=['승인']),session_id='other')
    assert reused['answer']['claims'] and reused['assembly']['term_agent']['completion_contract']==cc.CONTRACT


def test_return_to_deferred_read_point_restores_choices_without_rewinding_judgment(session):
    from semantic_runtime.legal_agent import investigation_chain as trail
    native,_=session;inv=inv_for(native)
    initial,_=inv.view();gid=read(inv)
    original,_=inv.view();fid=original['chain_frame_id']
    mark(inv,gid)
    history=deepcopy(trail.context(inv.p)['steps'])
    data,actions=inv.view()
    target=next(a['id'] for a in actions.values() if a['action']=='RETURN_TO' and a['identity']['frame_id']==fid)
    v=decision(data,'RETURN_TO',target);v['reason']='보류했던 원문과 선택지로 복귀해 다시 판단'
    apply(inv,v,data,actions)
    restored,_=inv.view()
    assert restored['sources']==original['sources']
    assert inv.p['groups'][gid]['status']=='DEFERRED'
    assert trail.context(inv.p)['steps'][:len(history)]==history
    assert restored['return_context']['frame_id']==fid
    mark(inv,gid,'ADOPT')
    assert inv.p['groups'][gid]['status']=='ACTIVE'
    assert any(s['action']=='RETURN_TO' for s in trail.context(inv.p)['steps'])


def test_current_publication_blocks_added_sentence_and_changed_source_scope(completed_app):
    from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
    from semantic_runtime.legal_agent.unified_publication import validate_saved,validate_current
    api,t,runtime=completed_app
    result=ok(api.post('/v1/rag/ask',json={'question':'모의승인규정 제1조 승인 기준은?',
        'session_id':'s','request_id':'r1'}))
    journal=next((runtime/'legal-agent/runs').glob('*/*/journal.sqlite'))
    repo=UnifiedRepository(journal)
    try:
        validate_saved(repo,result)
        changed=deepcopy(result);changed['answer']['text']+=' 원문에 없는 거래 제한'
        with pytest.raises(ContractError,match='public answer differs'):validate_saved(repo,changed)
        with pytest.raises(ContractError,match='authorization changed'):
            validate_current(repo,result,api.app.state.pipeline.store,allowed_documents=[])
    finally:repo.close()


def test_candidate_workflow_distinguishes_partial_pending_and_provider_failure():
    import importlib.util
    path=Path(__file__).resolve().parents[2]/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
    spec=importlib.util.spec_from_file_location('candidate_completion_workflow',path)
    workflow=importlib.util.module_from_spec(spec);spec.loader.exec_module(workflow)
    assert workflow._completion_answer_status({'code':'SOURCE_INVESTIGATION_INCOMPLETE'},False)=='incomplete'
    assert workflow._completion_answer_status({'code':'MODEL_UPSTREAM_UNAVAILABLE'},False)=='unavailable'
    partial={'assembly':{'term_agent':{'completion_contract':cc.CONTRACT,'answer_coverage':'PARTIAL'}}}
    assert workflow._completion_answer_status(partial,True)=='partial'
    assert workflow.render({'code':'SOURCE_INVESTIGATION_INCOMPLETE','diagnostics':{'stage':'SELECT'}})
