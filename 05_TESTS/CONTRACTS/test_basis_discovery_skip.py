"""Synthetic research failure contracts; native RAG is exercised separately."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace as S

import pytest
from fastapi.testclient import TestClient
from test_ingress import app
from test_document_release import source
from test_legal_agent_double_harness import wire
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.errors import (
    ContractError, ProposalError, StaleProposal, TransportError,
    BudgetExhausted, DeadlineExceeded, ToolExecutionError)
from semantic_runtime.legal_agent.context import RequestContext
from semantic_runtime.legal_agent.repository import WorkRepository
from semantic_runtime.legal_agent.workflow_execution import child_execution, register
from semantic_runtime.workflow_evidence import parent_issues
from lawrag.pipeline.term_generation import build_generation
from lawrag.pipeline import basis_batch as batch
from lawrag.pipeline.basis_batch_candidates import factory
from workflow.internal_basis_discovery_workflow.contracts import skippable


@pytest.fixture
def generation(tmp_path,term_glossary):
    raw=source(tmp_path/'raw.sqlite',[
        ('inside','모의내규',['제1조 승인 후 보고한다.','제2조 변경을 확인한다.']),
        ('inside2','두번째내규',['제1조 두번째 업무를 확인한다.']),
        ('outside','모의외규',['제1조 승인 후 보고한다.'])])
    with sqlite3.connect(raw) as db:
        for did in ('inside','inside2','outside'):
            db.execute('UPDATE document SET json=? WHERE document_id=?',(json.dumps({
                'document_category':'external' if did=='outside' else 'internal',
                'document_metadata':{'team':'risk_team','is_latest':True}}),did))
    build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    return tmp_path/'built/generation'


def request(**extra):
    return {'workflow_id':'internal_basis_discovery_workflow','session_id':'skip-test','request_id':'same',
            'input':{'internal_document_id':'inside','skip_research_errors':True,
                     'publish_candidates':True,**extra}}


def port(app):
    return importlib.import_module(app.state.workflow_runtime.services.__class__.__module__.rsplit('.',1)[0]+'.workflow_rag')


def synthetic_link(app,monkeypatch):
    calls=[]
    def send(*,body,ticket):
        view=json.loads(body['messages'][1]['content'])['view'];calls.append(view)
        a=next(e for e in view['sources'] if e['side']=='internal')
        b=next(e for e in view['sources'] if e['side']=='external')
        return wire({'links':[{'internal_ref':a['evidence_id'],'external_refs':[b['evidence_id']],
                              'kind':'RELATED','reason':'합성 원문 연결'}],'notes':[]})
    monkeypatch.setattr(app.state.pipeline.term_agent.transport,'send_once',send)
    return calls


def test_no_issues_task_is_durable_and_no_issue_ids_invented(tmp_path):
    q={'id':'q','question':'조사','scope':{'document_version_ids':['doc']}}
    ctx=RequestContext.create(q,{'question':'조사'},{'documents':['doc']},60)
    childctx=RequestContext.create(q,{'question':'조사'},{'documents':['doc']},60)
    profile={'max_model_attempts':5,'finalization_reserve':1,'max_tool_actions':8}
    parent=WorkRepository(tmp_path/'parent.sqlite',ctx,profile)
    child=WorkRepository(tmp_path/'child.sqlite',childctx,profile)
    task={'source_category':'external','search_hints':[],'return_mode':'sources','preferred_document_ids':[]}
    try:
        with child_execution(parent,ctx,'call',['doc'],task=task):register(child)
        row=child.db.execute("SELECT payload_json FROM event WHERE kind='WORKFLOW_PARENT_TASK_BOUND'").fetchone()
        assert json.loads(row[0])['task']==task
        assert json.loads(row[0])['issue_map']=={}
        assert parent_issues(child) is None
    finally:parent.close();child.close()
    child=WorkRepository(tmp_path/'child.sqlite')
    try:assert parent_issues(child) is None
    finally:child.close()


@pytest.mark.parametrize('exc,allowed',[
    (ContractError('source return task missing'),True),(ProposalError('schema'),True),
    (TransportError('network',unknown=True),True),(ToolExecutionError('read failed'),True),
    (StaleProposal('stale'),False),(ContractError('source return task changed'),False),
    (ContractError('hash mismatch'),False),(BudgetExhausted('limit'),False),
    (DeadlineExceeded('time'),False),(RuntimeError('unknown'),False)])
def test_failure_allowlist(exc,allowed):
    assert skippable(exc) is allowed


@pytest.mark.parametrize('cause',[MemoryError('memory'),PermissionError('denied'),
    OSError(28,'disk full'),ContractError('source hash mismatch'),StaleProposal('revision')])
def test_wrapped_resource_and_integrity_failure_is_not_skipped(cause):
    import errno
    if isinstance(cause,PermissionError):cause=PermissionError(errno.EACCES,'denied')
    error=ToolExecutionError('wrapped source failure')
    error.__cause__=cause
    assert not skippable(error)


@pytest.mark.parametrize('failure',[ContractError('source return task missing'),ProposalError('invalid JSON'),
                                  TransportError('network failed',unknown=True),ToolExecutionError('read failed')])
def test_api_skip_first_scope_keep_next_candidate_and_duplicate(app,monkeypatch,tmp_path,failure):
    app.state.pipeline.basis_factory=factory(app,tmp_path/'CANDIDATES.json')
    calls=[];models=synthetic_link(app,monkeypatch)
    def child(p,action,call_id):
        calls.append(call_id)
        if len(calls)==1:raise failure
        return p.execute({'operation':'read_node','side':'external',
                          'args':{'node':p.session.node('outside','0'),'cursor':None}})
    monkeypatch.setattr(port(app),'execute',child)
    with TestClient(app) as client:
        response=client.post('/v1/workflows/run',json=request())
        assert response.status_code==200,response.text
        out=response.json()
        assert out['status']=='partial' and out['coverage']['skipped']==1 and out['coverage']['reviewed']==1,out
        assert out['coverage']['not_found']==0 and len(out['basis_link_ids'])==1
        assert out['research_failures'][0]['message']==str(failure)
        assert out['answer']['answer_status']=='PARTIAL'
        before=(len(calls),len(models))
        again=client.post('/v1/workflows/run',json=request())
        assert again.status_code==200,again.text
        assert before==(len(calls),len(models))
    assert (tmp_path/'CANDIDATES.json').exists()
    assert not (app.state.workflow_runtime.services.runtime/'basis-links/SQLITE_ENABLED.json').exists()


@pytest.mark.parametrize('fault',[ContractError('source return task changed'),StaleProposal('state changed')])
def test_integrity_and_stale_never_skip_to_next_scope(app,monkeypatch,fault):
    calls=[]
    def child(*args):
        calls.append(1);raise fault
    monkeypatch.setattr(port(app),'execute',child)
    with TestClient(app,raise_server_exceptions=False) as client:
        out=client.post('/v1/workflows/run',json=request())
        assert out.status_code>=400,out.text
    assert len(calls)==1


def test_failed_receipt_checkpoint_gap_resume_does_not_repeat(app,monkeypatch):
    calls=[];models=synthetic_link(app,monkeypatch)
    def child(p,action,call_id):
        calls.append(call_id)
        if len(calls)==1:raise ContractError('source return task missing')
        return p.execute({'operation':'read_node','side':'external',
                          'args':{'node':p.session.node('outside','0'),'cursor':None}})
    monkeypatch.setattr(port(app),'execute',child)
    Repository=importlib.import_module(app.state.workflow_runtime.__class__.__module__.rsplit('.',1)[0]+'.repository').Repository
    save=Repository.save;crashed=[]
    def stop(repo,checkpoint,**kw):
        if any(u['status']=='skipped' for u in checkpoint.get('units',{}).values()) and not crashed:
            crashed.append(True);raise KeyboardInterrupt('after failed call before skip checkpoint')
        return save(repo,checkpoint,**kw)
    monkeypatch.setattr(Repository,'save',stop)
    runtime=app.state.workflow_runtime
    who=runtime.services.principal('test','risk_team')
    with pytest.raises(KeyboardInterrupt):runtime.execute(request(),who)
    path=next(runtime.root.glob('*/journal.sqlite'))
    with sqlite3.connect(path) as db:
        deadline=db.execute('SELECT deadline_at FROM run').fetchone()[0]
    out=runtime.execute(request(),who,resume=True)
    assert out['status']=='partial' and out['coverage']['skipped']==1
    assert len(calls)==2 and len(set(calls))==2
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT deadline_at FROM run').fetchone()[0]==deadline


def test_candidate_batch_document_failure_continues_and_never_enables_sqlite(app,monkeypatch,tmp_path):
    app.state.workflow_runtime.services.release={'mode':'local-release'}
    value,_=batch.plan(app,'risk_team',ids=['inside','inside2'])
    value['candidate_storage']={'kind':'json-candidates-v1','path':str(tmp_path/'CANDIDATES.json')}
    value['plan_sha256']=digest({k:v for k,v in value.items() if k!='plan_sha256'})
    calls=[];original=app.state.workflow_runtime.execute
    def run(body,who,**kw):
        calls.append(body['input']['internal_document_id'])
        if len(calls)==1:raise ContractError('source return task missing')
        return original(body,who,**kw)
    monkeypatch.setattr(app.state.workflow_runtime,'execute',run)
    monkeypatch.setattr(batch,'enable',lambda app:pytest.fail('SQLite enable'))
    state=batch.run(app,value,tmp_path,use_llm=False,candidate_factory=factory(app,tmp_path/'CANDIDATES.json'))
    assert len(calls)==2 and state['status']=='partial'
    assert state['documents'][calls[0]]['status']=='failed'
    assert state['documents'][calls[1]]['status']=='completed'
    batch.run(app,value,tmp_path,resume=True,use_llm=False,candidate_factory=factory(app,tmp_path/'CANDIDATES.json'))
    assert len(calls)==2


def test_native_rag_source_return_without_parent_issues(app,monkeypatch,tmp_path):
    from test_sources import Sources
    native=Sources();calls=[]
    def send(*,body,ticket):
        view=json.loads(body['messages'][1]['content'])['view']
        stage=view.get('source_stage',view['phase']);calls.append(stage)
        if stage.startswith('request-entry'):
            from semantic_runtime.legal_agent.workflow_execution import entry_proposal
            value=entry_proposal({'source_category':'external','search_hints':['승인'],
                'issues':[{'id':'fixture','question':'승인 기준','numeric':False}],'facts':[]},view['question'],True)
            if 'history_ids' in body['response_format']['json_schema']['schema'].get('properties',{}):
                value['history_ids']=[]
            return wire(value)
        if stage.startswith('memory-intent'):
            return wire({'purpose':'원문 조사','concepts':['승인'],'background_quotes':[],
                         'issues':[{'id':'Q1','question':'승인 기준','kind':'OTHER',
                                    'subject':'외규','request_quote':view['question']}]})
        if stage.startswith('source-law-sources-'):
            actions=view.get('actions',[])
            target=None if view.get('sources') else next((a for a in actions if a['action']=='READ_ARTICLES'),None)
            if target is None and not view.get('sources'):
                target=next((a for a in actions if a['action']=='OPEN_STRUCTURE'),None)
            if target is None and not view.get('sources'):
                target=next((a for a in actions if a['action']=='SEARCH_STRUCTURE'),None)
            return wire({'target_id':target['id'] if target else None,
                         'query':'모의외규 제1조' if target and target['action']=='SEARCH_STRUCTURE' else None,
                         'reason':'합성 원문 위치 확인' if target else '읽은 원문 반환'})
        if stage=='workflow-link':
            a=next(e for e in view['sources'] if e['side']=='internal')
            b=next(e for e in view['sources'] if e['side']=='external')
            return wire({'links':[{'internal_ref':a['evidence_id'],'external_refs':[b['evidence_id']],
                                  'kind':'RELATED','reason':'합성 모델 원문 연결'}],'notes':[]})
        return native.send_once(body=body,ticket=ticket)
    monkeypatch.setattr(app.state.pipeline.term_agent.transport,'send_once',send)
    app.state.pipeline.basis_factory=factory(app,tmp_path/'CANDIDATES.json')
    with TestClient(app) as client:
        response=client.post('/v1/workflows/run',json=request())
        assert response.status_code==200,response.text
        out=response.json()
        assert out['coverage']['skipped']==0,out
        journals=list((app.state.workflow_runtime.root/out['run_id']).glob('children/external/legal-agent/runs/*/*/journal.sqlite'))
        assert journals
        exports=0;exported=[]
        for path in journals:
            with sqlite3.connect(path) as db:
                rows=db.execute("SELECT payload_json FROM event WHERE kind='WORKFLOW_PARENT_TASK_BOUND'").fetchall()
                assert len(rows)==1
                task=json.loads(rows[0][0])
                assert 'issues' not in task['task'] and task['issue_map']=={}
                exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='source_handoff_export'").fetchone()
                if exists:
                    exports+=db.execute('SELECT count(*) FROM source_handoff_export').fetchone()[0]
                    exported.append(path)
        assert exports>0
        count=len(calls)
        again=client.post('/v1/workflows/run',json=request())
        assert again.status_code==200 and len(calls)==count,again.text
        # Validate the same durable export through its actual consumer boundary.
        from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
        from semantic_runtime.legal_agent.source_handoff import validate_export
        child=UnifiedRepository(exported[0])
        envelope=json.loads(child.db.execute('SELECT payload_json FROM source_handoff_export').fetchone()[0])
        validate_export(child,envelope)
        child.close()
        with sqlite3.connect(exported[0]) as db:
            for name, in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='event'").fetchall():
                db.execute('DROP TRIGGER "'+name+'"')
            db.execute("UPDATE event SET payload_hash=? WHERE kind='WORKFLOW_PARENT_TASK_BOUND'",('0'*64,))
        child=UnifiedRepository(exported[0])
        try:
            with pytest.raises(ContractError,match='source return task changed'):
                validate_export(child,envelope)
        finally:child.close()
        assert len(calls)==count


@pytest.mark.parametrize('fault',[BudgetExhausted('fixed allowance'),DeadlineExceeded('fixed deadline')])
def test_budget_ends_document_without_skipping_remaining_scopes(app,monkeypatch,fault):
    calls=[]
    def child(*args):
        calls.append(1);raise fault
    monkeypatch.setattr(port(app),'execute',child)
    with TestClient(app) as client:
        response=client.post('/v1/workflows/run',json=request())
        assert response.status_code==200,response.text
        out=response.json()
        assert out['status']=='partial' and out['coverage']['skipped']==0
        assert out['error_code']==fault.code and len(calls)==1
        again=client.post('/v1/workflows/run',json=request())
        assert again.status_code==200 and len(calls)==1
