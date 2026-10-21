"""Bounded comparison termination through real local API/service consumers."""
import asyncio
from copy import deepcopy
from datetime import datetime
import importlib
import json
import sqlite3
from types import SimpleNamespace as S

import pytest
from fastapi.testclient import TestClient

import test_internal_concept_comparison as fixture
from test_legal_agent_double_harness import wire
from test_research_resolution_consumers import load
from semantic_runtime.legal_agent.context import RequestContext
from semantic_runtime.legal_agent.errors import BudgetExhausted, TransportError
from semantic_runtime.legal_agent import workflow_execution as execution
from semantic_runtime.research_state import ResearchLedger

tree=fixture.tree
BODY=fixture.fixture.prior.BODY


class Clock:
    elapsed=0


class Transport(fixture.Transport):
    def __init__(self,clock,mode):
        super().__init__();self.clock=clock;self.mode=mode;self.calls=[];self.final_calls=0

    def send_once(self,*,body,ticket):
        view=json.loads(body['messages'][1]['content'])['view']
        stage=view.get('source_stage',view['phase'])
        self.calls.append((stage,ticket['remaining_seconds']))
        if stage=='workflow-finalize':
            self.final_calls+=1
            if self.mode=='final_timeout':
                self.clock.elapsed=571
                raise TransportError('synthetic final timeout',unknown=True,retryable=True)
            refs=[{'citation_id':s['citation_options'][0]['citation_id']} for s in view['sources']]
            if self.mode=='bad_final' or self.mode=='corrected_final' and self.final_calls==1:
                refs=[{'citation_id':'not-offered'}]
            return wire({'paragraphs':[{'text':'확보한 원문에서는 승인 후 보고하도록 정하고 있습니다.','citations':refs}],
                         'unresolved':['예외 적용 범위는 확인하지 못했습니다.']})
        if self.mode=='child_timeout' and stage.startswith('source-law-sources-') and view.get('workflow_task',{}).get('source_category')=='external':
            self.clock.elapsed=481
            raise TransportError('synthetic investigation timeout after read',unknown=True)
        result=super().send_once(body=body,ticket=ticket)
        if stage=='workflow-items' and self.mode!='normal':self.clock.elapsed=601 if self.mode=='hard_deadline' else 481
        if self.mode=='budget' and stage.startswith('source-law-sources-') and view.get('workflow_task',{}).get('source_category')=='external':
            parent=execution._parent.get()
            parent['work'].db.execute('UPDATE budget SET model_reserved=model_limit-finalization_reserve')
        return result


def application(tmp_path,tree,monkeypatch,mode):
    app,_=fixture.application(tmp_path,tree)
    clock=Clock();original=RequestContext.remaining
    # Advance request accounting only, without changing asyncio or real clocks.
    def remaining(context):
        from semantic_runtime.legal_agent.errors import DeadlineExceeded
        left=original(context)-clock.elapsed
        if left<=0:raise DeadlineExceeded('synthetic elapsed request deadline')
        return left
    monkeypatch.setattr(RequestContext,'remaining',remaining)
    t=Transport(clock,mode);app.state.pipeline.term_agent.transport=t
    return app,t,clock


@pytest.mark.parametrize('mode',['normal','review_deadline','child_timeout','budget','final_timeout','bad_final','corrected_final','hard_deadline'])
def test_service_deadline_budget_final_failure_and_saved_answer(tmp_path,tree,monkeypatch,mode):
    app,t,clock=application(tmp_path,tree,monkeypatch,mode)
    service=load('ten_minute_service_'+mode,'service.py');service._APP=app
    service._BINDING={'mode':'isolated-contract-test'}
    request={'API_TYPE':'RAG_ASK',**BODY}
    from semantic_runtime.legal_agent.answer_stream import capture
    events=[]
    with capture(BODY['request_id'],events.append):
        result=asyncio.run(service.service({},request))
    assert result['status']==200,result
    body=result['body'];assert body['answer']['text'] and body['evidence_refs'],body
    assert ''.join(e['text'] for e in events)==body['answer']['text']
    assert {c['side'] for c in body['assembly']['term_agent']['source_bundle']['sources']}=={'internal','external'}
    if mode!='normal':
        assert body['status']=='partial',body
        assert '미완료' not in body['answer']['text']
        assert '<details style=' in body['answer']['text']
        assert '승인' in body['answer']['text'] and '보고' in body['answer']['text']
        expected=0 if mode=='hard_deadline' else 2 if mode in ('bad_final','corrected_final') else 1
        assert t.final_calls==expected,t.calls
        index=next((i for i,(stage,_) in enumerate(t.calls) if stage=='workflow-finalize'),len(t.calls))
        assert all(stage=='workflow-finalize' for stage,_ in t.calls[index:])
        if mode not in ('final_timeout','bad_final','hard_deadline'):
            assert body['finalization']['status']=='COMPLETE',body
            assert '확보한 원문에서는 승인 후 보고' in body['answer']['text']
        else:assert body['finalization']['status']=='SAVED_EVIDENCE_ONLY'
        if mode not in ('budget','hard_deadline'):assert 0<t.calls[index][1]<=90,t.calls
    journal=app.state.workflow_runtime.root/body['run_id']/'journal.sqlite'
    with sqlite3.connect(journal) as db:
        start,end=db.execute('SELECT started_at,deadline_at FROM run').fetchone()
        assert 599<= (datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()<=600
        budget=db.execute('SELECT model_limit,finalization_reserve,model_reserved FROM budget').fetchone()
        assert budget[0:2]==(24,4) and budget[2]<=24
    calls=len(t.calls)
    saved=asyncio.run(service.service({}, {'API_TYPE':'WORKFLOW_STATUS','run_id':body['run_id'],'session_id':'s'}))
    again=asyncio.run(service.service({}, request))
    assert saved['status']==again['status']==200,(saved,again)
    assert saved['body']['answer']==again['body']['answer']==body['answer']
    assert len(t.calls)==calls
    with sqlite3.connect(journal) as db:
        assert db.execute('SELECT deadline_at FROM run').fetchone()[0]==end
        assert db.execute('SELECT model_limit,finalization_reserve,model_reserved FROM budget').fetchone()==budget


def test_finalization_resume_reuses_received_answer_without_reopening_research(tmp_path,tree,monkeypatch):
    app,t,clock=application(tmp_path,tree,monkeypatch,'review_deadline')
    definition=app.state.workflow_runtime.registry.resolve('risk_team_compare_workflow',None,'risk_team')
    package=definition.entrypoint.__module__.split('.risk_team_compare_workflow')[0]
    repository=importlib.import_module(package+'.repository').Repository
    original=repository.save;interrupted=[]
    def save(repo,state,**kwargs):
        if state.get('finalization',{}).get('status')=='COMPLETE' and not interrupted:
            interrupted.append(True)
            raise KeyboardInterrupt('after final model receipt before final checkpoint')
        return original(repo,state,**kwargs)
    monkeypatch.setattr(repository,'save',save)
    with pytest.raises(KeyboardInterrupt):
        app.state.workflow_runtime.execute({**BODY,'workflow_id':'risk_team_compare_workflow'},
            fixture.fixture.prior.prior._base.PRINCIPAL)
    journal=next(app.state.workflow_runtime.root.glob('*/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        revision=db.execute('SELECT revision FROM workflow_state').fetchone()[0]
        deadline=db.execute('SELECT deadline_at FROM run').fetchone()[0]
    count=len(t.calls)
    with TestClient(app) as client:
        response=client.post('/v1/workflows/resume',json={'run_id':journal.parent.name,'session_id':'s','expected_revision':revision})
    assert response.status_code==200,response.text
    assert response.json()['finalization']['status']=='COMPLETE',response.json()
    assert len(t.calls)==count
    with sqlite3.connect(journal) as db:assert db.execute('SELECT deadline_at FROM run').fetchone()[0]==deadline


def test_catalogue_receipt_change_alone_does_not_reopen_review():
    ledger=ResearchLedger({'tasks':{},'reviewed':[]})
    first=ledger.review_input('i',[],{}, {'catalogue_hash':'old','items':[]})
    assert first==ledger.review_input('i',[],{}, {'catalogue_hash':'new','items':[]})
    assert first!=ledger.review_input('i',[],{}, {'catalogue_hash':'new','items':[{'lead_id':'L1','preview':'new original location'}]})


def test_per_child_physical_call_limit_and_resume_counter(tmp_path):
    from semantic_runtime.legal_agent.repository import WorkRepository
    query={'id':'q','question':'q','scope':{'document_version_ids':[]}}
    context=RequestContext.create(query,{}, {'execution_policy':{'max_child_model_attempts':6}},600)
    owner=WorkRepository(tmp_path/'parent.sqlite',context,{'max_model_attempts':24,'finalization_reserve':4,'max_tool_actions':20})
    try:
        work=S(context=context,workflow_parent={'context':context,'work':owner,'call_id':'child1','task':{}})
        for _ in range(6):execution.reserve(work,'model')
        with pytest.raises(BudgetExhausted,match='child investigation'):execution.reserve(work,'model')
        owner.close()
        owner=WorkRepository(tmp_path/'parent.sqlite',context)
        work.workflow_parent['work']=owner
        with pytest.raises(BudgetExhausted):execution.reserve(work,'model')
        assert owner.budget()['model_reserved']==6
    finally:owner.close()


def test_lower_operator_limits_and_other_workflow_budget_are_preserved(tmp_path):
    from semantic_runtime.workflow_bridge import Services
    service=Services.__new__(Services)
    service.profile={'wall_seconds':90,'max_model_attempts':5,'finalization_reserve':1,'max_tool_actions':20}
    policy={'wall_seconds':600,'max_model_attempts':24,'finalization_reserve':4,
            'finalization_seconds':120,'publication_seconds':30}
    request={'question':'q','document_ids':[]}
    binding={'generation_id':'g','execution_policy':policy}
    context=service.context(request,binding,'a'*32,tmp_path/'new.sqlite')
    assert 89<context.remaining()<=90
    assert 71<service.phase_context(context).remaining()<=72
    assert 84<service.phase_context(context,final=True).remaining()<=85.5
    work=service.journal(tmp_path/'new.sqlite',context)
    assert work.budget()['model_limit']==5
    assert work.budget()['finalization_reserve']==4
    work.close()
    other=service.context(request,{'generation_id':'g'},'b'*32,tmp_path/'other.sqlite')
    assert service.phase_context(other)==other
    work=service.journal(tmp_path/'other.sqlite',other)
    assert work.budget()['model_limit']==5 and work.budget()['finalization_reserve']==1
    work.close()
