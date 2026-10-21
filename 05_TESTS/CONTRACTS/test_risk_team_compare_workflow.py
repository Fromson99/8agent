"""Workflow protocol tests with synthetic sources and scripted model responses only."""
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.workflow_tiers_policy import DEFAULT_PROFILE
from test_document_release import source
from test_legal_agent_double_harness import BINDING, wire
from workflow.contracts import route, request, WorkflowError
from workflow.risk_team_compare_workflow import basis, compare

ROOT=Path(os.environ.get('WORKFLOW_TEST_CODE_ROOT',Path(__file__).resolve().parents[2]))
PRINCIPAL={'user_id':'user-a','team_id':'risk_team','document_ids':['inside','outside']}
BODY={'question':'대사: 영업일 승인 기준','session_id':'session-a','request_id':'request-a','as_of':'2026-10-15'}


@pytest.fixture
def generation(tmp_path,term_glossary):
    path=source(tmp_path/'source.sqlite',[
        ('inside','모의내규',['모의외규에 따라 영업일에 승인을 받는다.']),
        ('outside','모의외규',['영업일에 승인을 받는다.'])])
    with sqlite3.connect(path) as db:
        for did,category in [('inside','internal'),('outside','external')]:
            db.execute('UPDATE document SET json=? WHERE document_id=?',(json.dumps({
                'document_category':category,'document_metadata':{'team':'risk_team'},
                'workflow_version':{'verified':True,'valid_from':'2020-01-01','valid_to':None}}),did))
    build_generation(path,term_glossary,tmp_path/'built',serving=True)
    return tmp_path/'built/generation'


class Scripted:
    binding=BINDING
    def validate_model(self):return {'verified':True,'synthetic':True}
    def __init__(self,*,verdict='CONFORMS',bad_basis=0):
        self.calls=[];self.verdict=verdict;self.bad_basis=bad_basis

    def send_once(self,*,body,ticket):
        view=json.loads(body['messages'][1]['content'])['view'];stage=view['source_stage']
        self.calls.append(stage)
        if stage=='workflow-intake':
            result={'issues':[{'id':'i1','label':'승인 기준','numeric':False}],
                'internal_queries':['영업일'],'external_queries':['영업일'],
                'scope_note':'합성 대상과 명시 기준일','missing_user_facts':[]}
        elif stage=='workflow-investigate':
            reads={r['action']['args']['node'] for r in view['history'] if r['action']['operation']=='read_node'}
            pending=[(r['action']['side'],item['node']) for r in view['history']
                if r['action']['operation']=='search_sources' for item in r['result']['items'] if item['node'] not in reads]
            result={'action':({'operation':'read_node','side':pending[0][0],
                'args':{'node':pending[0][1],'cursor':None},'reason':'원문 확인'} if pending else None),
                'finish':not pending,'reason':'양측 원문 읽기'}
        elif stage=='workflow-basis':
            a=next(e for e in view['sources'] if e['side']=='internal')
            b=next(e for e in view['sources'] if e['side']=='external')
            quotes=[{'evidence':e['evidence_id'],'quote':e['text']} for e in (a,b)]
            result={'pairs':[{'pair_id':'p1','issue_id':'i1','internal':[a['evidence_id']],
                'external':[b['evidence_id']],'applicability':{'status':'MATCH','reason':'합성 양측 적용',
                    'citations':quotes,'as_of':view['as_of']},'basis_relation':'DIRECT',
                'basis_path':[{'from_evidence':a['evidence_id'],'to_evidence':b['evidence_id'],'citation':quotes[0]}],
                'comparison_eligibility':True,'reason':'명시 인용'}], 'gaps':[],'summary':'모의내규가 모의외규를 명시 인용합니다.'}
            if self.bad_basis:
                self.bad_basis-=1
                result['pairs'][0]['basis_path'][0]['citation']['quote']='존재하지 않는 인용'
        elif stage=='workflow-compare':
            result={'rows':[{'pair_id':'p1','item':'승인 기준','verdict':self.verdict,
                'difference':'합성 판정','reason':'양측 원문 대조',
                'citations':[{'evidence':e['evidence_id'],'quote':e['text']} for e in view['sources']],
                'numeric':False,'dimensions':[],'unresolved':[]}],
                'answer':'합성 답변','unresolved':[]}
        else:raise AssertionError(stage)
        response=wire(result);response['body_json']['choices'][0]['finish_reason']='stop'
        return response


def application(tmp_path,generation,transport=None,profile=None,identity=None):
    t=transport or Scripted()
    app=create_app(tmp_path,generation,contracts_root=ROOT,workspace_root=Path(__file__).resolve().parents[2],
        provider=object(),implementation='legal-agent-tools-v5',runtime_root=tmp_path/'runtime',
        legal_agent_profile={**DEFAULT_PROFILE,'model_binding':t.binding,**(profile or {})},legal_agent_transport=t,
        memory_identity=identity or (lambda request:PRINCIPAL))
    return app,t


@pytest.mark.parametrize('q,expected',[('대사: 내규와 외규 비교','risk_team_compare_workflow'),
    (' 대사： 비교','risk_team_compare_workflow'),('내규: 대사 내용',None),('외규: 영업일',None)])
def test_prefix_precedes_source_routing(q,expected):
    assert route({'question':q})==expected


def test_conflicting_route_is_rejected():
    with pytest.raises(WorkflowError):route({'question':'대사: 비교','workflow_id':'other'})


@pytest.mark.parametrize('body',[{'question':'대사:'},{'document_ids':['hidden']},{'user_id':'user-b'},
    {'use_llm':1},{'as_of':'2026-02-30'},{'budget':999},{'workflow_version':'2.0.0'}])
def test_closed_ingress(tmp_path,generation,body):
    app,_=application(tmp_path,generation)
    with TestClient(app) as client:
        response=client.post('/v1/workflows/run',json={**BODY,**body})
        assert response.status_code in (403,404,422)


@pytest.mark.parametrize('path',['/v1/workflows/run','/v1/rag/ask'])
def test_real_api_source_model_storage_and_display(tmp_path,generation,path):
    app,t=application(tmp_path,generation)
    with TestClient(app) as client:
        response=client.post(path,json=BODY)
        assert response.status_code==200,response.text
        value=response.json()
        assert value['status']=='completed',value
        assert value['report']['rows'][0]['verdict']=='CONFORMS'
        assert len(value['evidence_refs'])==2
        assert value['assembly']['term_agent']['source_bundle']['schema_version']=='workflow-source-v1'
        assert value['usage']['model_reserved']==6
        calls=len(t.calls)
        again=client.post(path,json=BODY).json()
        assert {k:v for k,v in again.items() if k!='execution_stats'}=={k:v for k,v in value.items() if k!='execution_stats'}
        assert len(t.calls)==calls
        status=client.get('/v1/workflows/runs/'+value['run_id'],params={'session_id':'session-a'})
        assert status.status_code==200,status.text
        assert status.json()['answer']==value['answer']
        assert len(t.calls)==calls


def test_model_free_keeps_unconfirmed_sources(tmp_path,generation):
    app,t=application(tmp_path,generation)
    with TestClient(app) as client:
        result=client.post('/v1/rag/ask',json={**BODY,'use_llm':False}).json()
        assert result['status']=='partial',result
        assert len(result['evidence_refs'])==2
        assert '근거 관계' in result['answer']['text']
        assert t.calls==[]


@pytest.mark.parametrize('invalid_attempts,expected,physical',[(1,'completed',7),(2,'partial',6)])
def test_semantic_repair_one_owner(tmp_path,generation,invalid_attempts,expected,physical):
    app,t=application(tmp_path,generation,Scripted(bad_basis=invalid_attempts))
    with TestClient(app) as client:
        result=client.post('/v1/workflows/run',json=BODY).json()
        assert result['status']==expected,result
        assert result['usage']['model_reserved']==physical
        assert t.calls.count('workflow-basis')==2
        if expected=='partial':
            assert result['error_code']=='WORKFLOW_REPAIR_EXHAUSTED'
            assert result['report']['rows']==[]


def test_conflict_is_reported_without_more_retrieval(tmp_path,generation):
    app,t=application(tmp_path,generation,Scripted(verdict='CONFLICT'))
    with TestClient(app) as client:
        result=client.post('/v1/workflows/run',json=BODY).json()
        assert result['report']['rows'][0]['verdict']=='CONFLICT',result
        assert t.calls[-1]=='workflow-compare'
        assert result['usage']['tool_used']==4


def test_other_principal_cannot_open_or_resume(tmp_path,generation):
    who=deepcopy(PRINCIPAL)
    app,_=application(tmp_path,generation,identity=lambda req:who)
    with TestClient(app) as client:
        result=client.post('/v1/workflows/run',json=BODY).json()
        who['user_id']='user-b'
        assert client.get('/v1/workflows/runs/'+result['run_id'],params={'session_id':'session-a'}).status_code==404
        assert client.post('/v1/workflows/resume',json={'run_id':result['run_id'],'session_id':'session-a',
            'expected_revision':result['revision']}).status_code==404


def test_reused_request_different_question_conflicts(tmp_path,generation):
    app,_=application(tmp_path,generation)
    with TestClient(app) as client:
        assert client.post('/v1/workflows/run',json=BODY).status_code==200
        response=client.post('/v1/workflows/run',json={**BODY,'question':'대사: 다른 질문'})
        assert response.status_code==409


@pytest.mark.parametrize('limit,expected',[(2,2),(3,3)])
def test_tool_budget_is_shared_and_not_reset(tmp_path,generation,limit,expected):
    app,_=application(tmp_path,generation,profile={'max_tool_actions':limit,'tool_finalization_reserve':1})
    with TestClient(app) as client:
        result=client.post('/v1/workflows/run',json=BODY).json()
        assert result['status'] in ('failed','partial'),result
        assert result['usage']['tool_used']==expected
        assert result['error_code']=='BUDGET_EXHAUSTED'
        assert client.post('/v1/workflows/run',json=BODY).json()['usage']==result['usage']


def test_registry_supports_new_explicit_workflow():
    from workflow.registry import Registry
    registry=Registry();handler=lambda ctx:{'status':'completed'}
    registry.register({'workflow_id':'other','version':'1','allowed_teams':['risk_team']},handler)
    assert registry.resolve('other','1','risk_team').entrypoint is handler
    with pytest.raises(WorkflowError):registry.resolve('other','1','financial_team')


def test_external_transport_never_receives_internal_question(tmp_path,generation):
    transport=Scripted();transport.binding={**BINDING,'trust_zone':'external'}
    app,_=application(tmp_path,generation,transport)
    with TestClient(app) as client:
        result=client.post('/v1/workflows/run',json=BODY).json()
        assert result['status']=='blocked',result
        assert result['error_code']=='WORKFLOW_INTERNAL_MODEL_REQUIRED'
        assert result['usage']['model_reserved']==0
        assert transport.calls==[]


def test_no_server_identity_is_not_self_authorized(tmp_path,generation,monkeypatch):
    for key in ('WORKFLOW_USER_ID','TEAM_ID'):monkeypatch.delenv(key,raising=False)
    app,_=application(tmp_path,generation)
    # Reinstall through the real port without a trusted principal resolver.
    from semantic_runtime.workflow_bridge import install
    other=create_app(tmp_path/'other',generation,contracts_root=ROOT,workspace_root=Path(__file__).resolve().parents[2],
        provider=object(),implementation='legal-agent-tools-v5',runtime_root=tmp_path/'other-runtime',
        legal_agent_profile={**DEFAULT_PROFILE,'model_binding':BINDING},legal_agent_transport=Scripted())
    with TestClient(other) as client:
        response=client.post('/v1/workflows/run',json={**BODY,'user_id':'user-a','team_id':'risk_team'})
        assert response.status_code==403
    app.state.pipeline.store.close()


def test_process_interruption_restores_tool_receipt_without_reread(tmp_path,generation,monkeypatch):
    app,t=application(tmp_path,generation)
    package=importlib.import_module(app.state.workflow_runtime.__class__.__module__.rsplit('.',1)[0]+'.repository')
    original=package.Repository.finish
    once=[]
    def interrupt_after_tool(self,ident,result):
        if ident.startswith('tool:') and not once:
            once.append(True)
            raise KeyboardInterrupt('simulated worker exit after atomic source receipt')
        return original(self,ident,result)
    monkeypatch.setattr(package.Repository,'finish',interrupt_after_tool)
    runtime=app.state.workflow_runtime
    with pytest.raises(KeyboardInterrupt):runtime.execute({**BODY,'workflow_id':'risk_team_compare_workflow'},PRINCIPAL)
    monkeypatch.setattr(package.Repository,'finish',original)
    journal=next((tmp_path/'runtime/workflows').glob('*/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        revision=db.execute('SELECT revision FROM workflow_state').fetchone()[0]
        deadline=db.execute('SELECT deadline_at FROM run').fetchone()[0]
        before=db.execute('SELECT model_reserved,tool_used FROM budget').fetchone()
        assert before==(1,1)
    resumed=runtime.resume(journal.parent.name,PRINCIPAL,'session-a',revision)
    assert resumed['status']=='completed'
    assert resumed['usage']['tool_used']==4
    assert resumed['usage']['model_reserved']==6
    with sqlite3.connect(journal) as db:assert db.execute('SELECT deadline_at FROM run').fetchone()[0]==deadline
    app.state.pipeline.store.close()


def test_concurrent_resume_rejected_by_execution_lock(tmp_path,generation):
    app,_=application(tmp_path,generation)
    from workflow.repository import execution_lock
    from workflow.contracts import digest
    run_id=digest([{'user_id':'user-a','team_id':'risk_team'},'session-a','request-a'])[:32]
    with execution_lock(tmp_path/'runtime/workflows',run_id),TestClient(app) as client:
        response=client.post('/v1/workflows/run',json=BODY)
        assert response.status_code==409
        assert response.json()['error_code']=='WORKFLOW_BUSY'


def test_stale_revision_and_acl_change_cannot_resume(tmp_path,generation):
    who=deepcopy(PRINCIPAL);app,_=application(tmp_path,generation,identity=lambda req:who)
    with TestClient(app) as client:
        result=client.post('/v1/workflows/run',json=BODY).json()
        response=client.post('/v1/workflows/resume',json={'run_id':result['run_id'],'session_id':'session-a',
            'expected_revision':result['revision']-1})
        assert response.status_code==409
        who['document_ids']=['outside']
        assert client.get('/v1/workflows/runs/'+result['run_id'],params={'session_id':'session-a'}).status_code==403


def test_saved_report_tamper_is_rejected(tmp_path,generation):
    app,_=application(tmp_path,generation)
    with TestClient(app) as client:
        result=client.post('/v1/workflows/run',json=BODY).json()
        journal=tmp_path/'runtime/workflows'/result['run_id']/'journal.sqlite'
        with sqlite3.connect(journal) as db:
            db.execute("UPDATE workflow_state SET result_json=json_set(result_json,'$.answer.text','tampered')")
        response=client.get('/v1/workflows/runs/'+result['run_id'],params={'session_id':'session-a'})
        assert response.status_code==409
        assert response.json()['error_code']=='WORKFLOW_STATE_INTEGRITY'


def test_model_budget_and_deadline_stop_without_new_allowance(tmp_path,generation):
    app,t=application(tmp_path,generation,profile={'max_model_attempts':4,'finalization_reserve':3})
    with TestClient(app) as client:
        result=client.post('/v1/workflows/run',json=BODY).json()
        assert result['error_code']=='BUDGET_EXHAUSTED',result
        assert result['usage']['model_reserved']==1
        assert client.post('/v1/workflows/run',json=BODY).json()['usage']==result['usage']


def semantic_fixture():
    evidence=[{'evidence_id':'ei','side':'internal','document_id':'di','metadata':{'document_name':'모의내규'},
        'spans':[{'text':'모의외규에 따라 영업일에 승인한다.'}],'version_verified':True,'source_complete':True},
        {'evidence_id':'ee','side':'external','document_id':'de','metadata':{'document_name':'모의외규'},
        'spans':[{'text':'영업일에 승인한다.'}],'version_verified':True,'source_complete':True}]
    quotes=[{'evidence':e['evidence_id'],'quote':e['spans'][0]['text']} for e in evidence]
    pair={'pair_id':'p1','issue_id':'i1','internal':['ei'],'external':['ee'],
        'applicability':{'status':'MATCH','reason':'합성','citations':quotes,'as_of':'2026-10-15'},
        'basis_relation':'DIRECT','basis_path':[{'from_evidence':'ei','to_evidence':'ee','citation':quotes[0]}],
        'comparison_eligibility':True,'reason':'합성'}
    return evidence,{'pairs':[pair],'gaps':[],'summary':'합성'},[{'id':'i1','label':'승인','numeric':False}]


@pytest.mark.parametrize('mutation',['similar','unknown_version','partial','wrong_side','fake_quote','disconnected'])
def test_basis_does_not_promote_unverified_relations(mutation):
    evidence,value,issues=semantic_fixture();pair=value['pairs'][0]
    if mutation=='similar':pair.update(basis_relation='UNKNOWN',basis_path=[])
    elif mutation=='unknown_version':evidence[0]['version_verified']=False
    elif mutation=='partial':evidence[0]['source_complete']=False
    elif mutation=='wrong_side':pair['internal']=['ee']
    elif mutation=='fake_quote':pair['basis_path'][0]['citation']['quote']='가짜 인용'
    elif mutation=='disconnected':pair['basis_path'][0]['to_evidence']='missing'
    with pytest.raises(ValueError):basis.validate(value,evidence,issues,'2026-10-15')


@pytest.mark.parametrize('verdict',['CONFORMS','CONFLICT','ADDITIONAL_INTERNAL','POSSIBLE_GAP'])
def test_numeric_difference_alone_cannot_be_a_judgment(verdict):
    evidence,value,issues=semantic_fixture();issues[0]['numeric']=True
    row={'pair_id':'p1','verdict':verdict,'citations':value['pairs'][0]['applicability']['citations'],
        'numeric':True,'dimensions':[],'unresolved':['정의·산식 미확인']}
    with pytest.raises(ValueError):compare.validate({'rows':[row]},evidence,value,issues)


def test_content_correspondence_can_only_be_described_as_unconfirmed():
    evidence,value,issues=semantic_fixture();value['pairs'][0].update(basis_relation='CONTENT_ONLY',basis_path=[])
    basis.validate(value,evidence,issues,'2026-10-15')
    row={'pair_id':'p1','verdict':'CONFORMS','citations':value['pairs'][0]['applicability']['citations'],
         'numeric':False,'dimensions':[],'unresolved':[]}
    with pytest.raises(ValueError):compare.validate({'rows':[row]},evidence,value,issues)
    row['verdict']='DEFERRED';compare.validate({'rows':[row]},evidence,value,issues)


def test_model_response_receipt_survives_process_exit(tmp_path,generation,monkeypatch):
    app,t=application(tmp_path,generation);runtime=app.state.workflow_runtime
    module=importlib.import_module(runtime.__class__.__module__.rsplit('.',1)[0]+'.repository')
    original=module.Repository.finish;once=[]
    def crash(self,ident,result):
        if ident.startswith('model:') and not once:
            once.append(True);raise KeyboardInterrupt('model completed before checkpoint')
        return original(self,ident,result)
    monkeypatch.setattr(module.Repository,'finish',crash)
    with pytest.raises(KeyboardInterrupt):runtime.execute({**BODY,'workflow_id':'risk_team_compare_workflow'},PRINCIPAL)
    monkeypatch.setattr(module.Repository,'finish',original)
    journal=next((tmp_path/'runtime/workflows').glob('*/journal.sqlite'))
    with sqlite3.connect(journal) as db:revision=db.execute('SELECT revision FROM workflow_state').fetchone()[0]
    result=runtime.resume(journal.parent.name,PRINCIPAL,'session-a',revision)
    assert result['status']=='completed',result
    assert result['usage']['model_reserved']==6
    assert t.calls.count('workflow-intake')==1
    app.state.pipeline.store.close()


def test_unknown_model_outcome_is_not_resent(tmp_path,generation):
    class Lost(Scripted):
        def send_once(self,**kwargs):
            self.calls.append('sent');raise KeyboardInterrupt('worker died after send')
    app,t=application(tmp_path,generation,Lost());runtime=app.state.workflow_runtime
    with pytest.raises(KeyboardInterrupt):runtime.execute({**BODY,'workflow_id':'risk_team_compare_workflow'},PRINCIPAL)
    journal=next((tmp_path/'runtime/workflows').glob('*/journal.sqlite'))
    with sqlite3.connect(journal) as db:revision=db.execute('SELECT revision FROM workflow_state').fetchone()[0]
    result=runtime.resume(journal.parent.name,PRINCIPAL,'session-a',revision)
    assert result['error_code']=='WORKFLOW_MODEL_OUTCOME_UNKNOWN',result
    assert result['usage']['model_reserved']==1 and len(t.calls)==1
    app.state.pipeline.store.close()


def test_expired_deadline_is_not_reset_by_resume(tmp_path,generation,monkeypatch):
    from dataclasses import replace
    import time
    app,t=application(tmp_path,generation);runtime=app.state.workflow_runtime
    original=runtime.services.context
    def expired(*args):return replace(original(*args),deadline=time.monotonic()-1)
    monkeypatch.setattr(runtime.services,'context',expired)
    result=runtime.execute({**BODY,'workflow_id':'risk_team_compare_workflow'},PRINCIPAL)
    assert result['error_code']=='DEADLINE_EXCEEDED',result
    assert result['usage']['model_reserved']==0
    again=runtime.resume(result['run_id'],PRINCIPAL,'session-a',result['revision'])
    assert again['usage']==result['usage'] and t.calls==[]
    app.state.pipeline.store.close()


def test_missing_category_is_registration_gap_not_legal_absence(tmp_path,generation):
    principal={**PRINCIPAL,'document_ids':['outside']}
    app,t=application(tmp_path,generation,identity=lambda req:principal)
    with TestClient(app) as client:
        result=client.post('/v1/workflows/run',json={**BODY,'use_llm':False}).json()
        assert result['status']=='partial' and result['report']['rows']==[]
        assert len(result['evidence_refs'])==1 and t.calls==[]
        with sqlite3.connect(tmp_path/'runtime/workflows'/result['run_id']/'journal.sqlite') as db:
            rows=db.execute("SELECT result_json FROM workflow_call WHERE kind='rag'").fetchall()
            assert any(json.loads(row[0]).get('registration_status')=='NOT_REGISTERED' for row in rows)


def test_failed_tool_never_becomes_absence_or_success(tmp_path,generation,monkeypatch):
    from semantic_runtime.workflow_bridge import SourcePort
    from semantic_runtime.legal_agent.errors import ToolExecutionError
    original=SourcePort.execute;count=[]
    def broken(self,action):
        count.append(action)
        if len(count)==2:raise ToolExecutionError('synthetic source unavailable')
        return original(self,action)
    monkeypatch.setattr(SourcePort,'execute',broken)
    app,t=application(tmp_path,generation)
    with TestClient(app) as client:
        result=client.post('/v1/workflows/run',json=BODY).json()
        assert result['status']=='failed' and result['error_code']=='SOURCE_TOOL_ERROR',result
        assert result['report']['rows']==[] and result['evidence_refs']==[]
        assert client.post('/v1/workflows/run',json=BODY).json()['usage']==result['usage']
        assert len(count)==2


def test_selected_source_bytes_change_blocks_saved_result(tmp_path,generation):
    app,t=application(tmp_path,generation)
    with TestClient(app,raise_server_exceptions=False) as client:
        result=client.post('/v1/workflows/run',json=BODY).json()
        with sqlite3.connect(generation/'store.sqlite') as db:
            db.execute("UPDATE source_block SET text='altered' WHERE document_id='inside'")
        response=client.get('/v1/workflows/runs/'+result['run_id'],params={'session_id':'session-a'})
        assert response.status_code>=400
        assert 'altered' not in response.text
        assert len(t.calls)==6


def test_targeted_recovery_keeps_unaffected_pair(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from workflow.risk_team_compare_workflow import recovery
    action={'operation':'search_sources','side':'external','args':{'query':'정확한 업권'},'reason':'범위 수정'}
    state={'recovery_count':0,'gaps':[],'basis':{'pairs':[{'issue_id':'i1'},{'issue_id':'i2'}],
        'gaps':[{'issue_id':'i1','kind':'EXTERNAL_SCOPE','action':action}]}}
    calls=[];saves=[]
    ctx=SimpleNamespace(definition=SimpleNamespace(manifest={'max_recoveries':2}),
        rag=SimpleNamespace(evidence=lambda:['preserved']),repo=SimpleNamespace(save=lambda s:saves.append(deepcopy(s))))
    monkeypatch.setattr(recovery,'call',lambda ctx,state,act:calls.append(act))
    assert recovery.recover(ctx,state)
    assert calls==[action] and state['retained_pairs']==[{'issue_id':'i2'}]
    action['side']='internal'
    assert not recovery.recover(ctx,state)
    assert len(calls)==1


def test_stored_citation_title_supports_reference_path():
    evidence,value,issues=semantic_fixture()
    evidence[1]['metadata']['document_name']='RAW > external > 모의외규'
    evidence[1]['citation_names']=['모의외규']
    basis.validate(value,evidence,issues,'2026-10-15')


def load_file(name,path):
    import importlib.util,sys
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module


@pytest.mark.parametrize('api_type',['WORKFLOW_RUN','LEGAL_AGENT'])
def test_service_gateway_and_display_use_workflow_result(tmp_path,generation,monkeypatch,api_type):
    import asyncio
    from types import SimpleNamespace
    app,t=application(tmp_path,generation)
    gateway=load_file('risk_workflow_service_'+api_type,ROOT/'service.py')
    monkeypatch.setattr(gateway,'_APP',app)
    monkeypatch.setattr(gateway,'_ad_control',lambda:SimpleNamespace(intercept=lambda *args:None,start_worker=lambda *args:None))
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(tmp_path/'runtime'))
    monkeypatch.delenv('GENOS_SHARED_LOG_DIR',raising=False)
    async def check():
        response=await gateway.service({}, {'API_TYPE':api_type,**BODY,'return_to':{'parent_run':'parent','step':'compare','call_id':'c1'}})
        assert response['status']==200,response
        result=response['body'];assert result['status']=='completed',result
        assert result['return_to']['parent_run']=='parent'
        status=await gateway.service({}, {'API_TYPE':'WORKFLOW_STATUS','run_id':result['run_id'],'session_id':'session-a'})
        assert status['status']==200,status
        assert status['body']['answer']==result['answer']
        resume=await gateway.service({}, {'API_TYPE':'WORKFLOW_RESUME','run_id':result['run_id'],
            'session_id':'session-a','expected_revision':result['revision']})
        assert resume['status']==200,resume
        assert len(t.calls)==6
        renderer=load_file('risk_workflow_display_'+api_type,ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
        rendered=await renderer.workflow_display_result(result,[],request_id=result['request_id'])
        assert '근거 관계' in rendered['text'] and '모의내규' in rendered['text']
        partial={**result,'status':'partial'}
        assert renderer._completion_answer_status(partial,True)=='partial'
    asyncio.run(check())
    app.state.pipeline.store.close()


def test_indirect_basis_requires_contiguous_cited_parent():
    evidence,value,issues=semantic_fixture()
    evidence[0]['spans'][0]['text']='상위내규에 따라 승인한다.'
    middle={'evidence_id':'em','document_id':'dm','side':'internal',
        'metadata':{'document_name':'상위내규'},'spans':[{'text':'모의외규에 따라 승인한다.'}],
        'source_complete':True,'version_verified':True}
    evidence.append(middle)
    pair=value['pairs'][0]
    pair['applicability']['citations'][0]['quote']=evidence[0]['spans'][0]['text']
    pair['basis_relation']='INDIRECT'
    pair['basis_path']=[{'from_evidence':'ei','to_evidence':'em','citation':{'evidence':'ei','quote':evidence[0]['spans'][0]['text']}},
        {'from_evidence':'em','to_evidence':'ee','citation':{'evidence':'em','quote':middle['spans'][0]['text']}}]
    basis.validate(value,evidence,issues,'2026-10-15')
    pair['basis_path'][1]['from_evidence']='ee'
    with pytest.raises(ValueError):basis.validate(value,evidence,issues,'2026-10-15')


def test_failed_state_is_not_offered_as_resumable(tmp_path,generation,monkeypatch):
    from semantic_runtime.workflow_bridge import SourcePort
    app,t=application(tmp_path,generation);runtime=app.state.workflow_runtime
    original=SourcePort.execute
    def fatal(*args):raise RuntimeError('synthetic unexpected tool defect')
    monkeypatch.setattr(SourcePort,'execute',fatal)
    with pytest.raises(RuntimeError):runtime.execute({**BODY,'workflow_id':'risk_team_compare_workflow'},PRINCIPAL)
    monkeypatch.setattr(SourcePort,'execute',original)
    journal=next((tmp_path/'runtime/workflows').glob('*/journal.sqlite'))
    status=runtime.status(journal.parent.name,PRINCIPAL,'session-a')
    assert status['status']=='failed' and status['resume_available'] is False
    with pytest.raises(ValueError):runtime.resume(journal.parent.name,PRINCIPAL,'session-a',status['revision'])
    assert len(t.calls)==1
    app.state.pipeline.store.close()


def test_call_receipt_tamper_cannot_supply_model_or_source_result(tmp_path,generation,monkeypatch):
    app,t=application(tmp_path,generation);runtime=app.state.workflow_runtime
    module=importlib.import_module(runtime.__class__.__module__.rsplit('.',1)[0]+'.repository')
    original=module.Repository.finish;once=[]
    def crash(self,ident,result):
        if ident.startswith('tool:') and not once:
            once.append(True);raise KeyboardInterrupt('source receipt before checkpoint')
        return original(self,ident,result)
    monkeypatch.setattr(module.Repository,'finish',crash)
    with pytest.raises(KeyboardInterrupt):runtime.execute({**BODY,'workflow_id':'risk_team_compare_workflow'},PRINCIPAL)
    monkeypatch.setattr(module.Repository,'finish',original)
    journal=next((tmp_path/'runtime/workflows').glob('*/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        revision=db.execute('SELECT revision FROM workflow_state').fetchone()[0]
        db.execute("UPDATE workflow_call SET result_json=json_set(result_json,'$.status','NOT_FOUND') WHERE kind='rag'")
    with pytest.raises(ValueError) as exc:runtime.resume(journal.parent.name,PRINCIPAL,'session-a',revision)
    assert exc.value.code=='WORKFLOW_CALL_INTEGRITY'
    assert len(t.calls)==1
    app.state.pipeline.store.close()


def test_explicit_ratio_request_keeps_numeric_requirement_without_model(tmp_path,generation):
    app,t=application(tmp_path,generation)
    with TestClient(app) as client:
        result=client.post('/v1/workflows/run',json={**BODY,'question':'대사: 유동성비율','use_llm':False}).json()
        assert '현재 확보한 내규에서 수치 기준 미확인' in result['answer']['text']
        assert result['report']['scope']['issues'][0]['numeric'] is True
        assert result['report']['rows']==[] and t.calls==[]


def test_unanswered_user_facts_prevent_completed_applicability(tmp_path,generation):
    class MissingFacts(Scripted):
        def send_once(self,**kwargs):
            response=super().send_once(**kwargs)
            message=response['body_json']['choices'][0]['message']
            value=json.loads(message['content'])
            if 'missing_user_facts' in value:
                value['missing_user_facts']=['적용 회사의 업권']
                message['content']=json.dumps(value,ensure_ascii=False)
            return response
    app,t=application(tmp_path,generation,MissingFacts())
    with TestClient(app) as client:
        result=client.post('/v1/workflows/run',json=BODY).json()
        assert result['status']=='partial' and result['report']['rows']==[]
        assert '적용 회사의 업권' in result['answer']['text']
        assert t.calls.count('workflow-basis')==2


def test_generation_bound_unit_fulltext_is_used_by_workflow(tmp_path,generation):
    from lawrag.pipeline.fulltext_stage import derive
    derived=tmp_path/'with-fulltext'
    derive(generation,derived,workers=1)
    app,t=application(tmp_path,derived)
    with TestClient(app) as client:
        result=client.post('/v1/workflows/run',json=BODY).json()
        assert result['status']=='completed',result
        assert app.state.pipeline.term_agent.get_fulltext().manifest['schema_version']=='semantic-unit-fulltext-v1'
        assert len(result['evidence_refs'])==2


def exclude_outside(generation):
    from semantic_runtime.search_selection import selection_path
    from semantic_runtime.contracts import sha
    manifest=json.loads((generation/'manifest.json').read_text())
    with sqlite3.connect(generation/'store.sqlite') as db:
        source_hash=db.execute("SELECT source_artifact_sha256 FROM document WHERE document_id='outside'").fetchone()[0]
    value={'schema_version':'filename-search-selection-v1','generation_id':manifest['generation_id'],
      'store_sha256':manifest['store_sha256'],'manifest_sha256':sha(generation/'manifest.json'),
      'excluded':[{'document_id':'outside','source_artifact_sha256':source_hash}]}
    path=selection_path(generation);path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(value))


def test_workflow_does_not_reintroduce_search_excluded_document(tmp_path,generation):
    exclude_outside(generation)
    app,t=application(tmp_path,generation)
    with TestClient(app) as client:
        denied=client.post('/v1/workflows/run',json={**BODY,'document_ids':['outside'],'use_llm':False})
        assert denied.status_code==403
        result=client.post('/v1/workflows/run',json={**BODY,'use_llm':False}).json()
        assert result['status']=='partial',result
        assert result['binding']['document_ids']==['inside']
        assert result['binding']['search_selection_sha256']
        assert all(s['document_id']=='inside' for s in result['assembly']['term_agent']['source_bundle']['sources'])
        assert t.calls==[]


def test_search_selection_change_revokes_previous_answer(tmp_path,generation):
    app,t=application(tmp_path,generation)
    with TestClient(app) as client:result=client.post('/v1/workflows/run',json=BODY).json()
    exclude_outside(generation)
    reopened,_=application(tmp_path,generation,t)
    with TestClient(reopened) as client:
        status=client.get('/v1/workflows/runs/'+result['run_id'],params={'session_id':'session-a'})
        assert status.status_code==403,status.text
        assert len(t.calls)==6
