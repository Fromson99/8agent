"""Synthetic originals only: anchored ordering, source table and real API consumers."""
import asyncio
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace as S

import pytest
from fastapi.testclient import TestClient
from markdown_it import MarkdownIt

from workflow.risk_team_compare_workflow import concepts, concept_report
from workflow.contracts import digest
from semantic_runtime.chat_adapter import views
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.workflow_execution import validate_internal_anchors
from semantic_runtime.workflow_rag import validate_internal_anchors as verify_anchors
from test_legal_agent_double_harness import wire

ROOT=Path(__file__).resolve().parents[2]
os.environ.setdefault('WORKFLOW_TEST_CODE_ROOT',str(ROOT))
spec=importlib.util.spec_from_file_location('concept_general_fixture',ROOT/'06_TOOLS/EXPERIMENTS/adr_0936/test_generalized.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
tree=fixture.tree


class Transport(fixture.General):
    def __init__(self,*,bad=False,count=1):
        super().__init__();self.bad=bad;self.count=count

    def send_once(self,*,body,ticket):
        view=json.loads(body['messages'][1]['content'])['view']
        stage=view.get('source_stage',view['phase'])
        if stage=='workflow-concepts':
            self.views.append((stage,deepcopy(view)))
            refs=[{'citation_id':s['citation_options'][0]['citation_id']} for s in view['sources']]
            if self.bad:
                refs=[{'citation_id':'NOT_PRESENTED'}]
                if type(self.bad) is int:self.bad-=1
            return wire({'concepts':[{'existing_id':None,'request_issue_id':view['request_issues'][0]['id'],
                'label':'승인 개념 '+str(i),'definition':'승인과 후속 보고를 함께 확인하는 개념',
                'scope_reason':'제공된 내규의 승인 의무와 보고 조건을 함께 읽음',
                'internal_citations':refs,'external_task':'내규의 승인·보고에 대응하는 모의승인규정 원문 확인',
                'external_queries':['승인','보고'],'numeric':False,'work_type':'general',
                'requested_fields':['obligation']} for i in range(self.count)],'unresolved':[]})
        return super().send_once(body=body,ticket=ticket)


def application(tmp,tree,**kwargs):
    from lawrag.pipeline.search_selection import plan,activate
    activate(plan(tree[0],latest=True))
    app,_=fixture.prior.app_for(tmp,tree)
    transport=Transport(**kwargs)
    app.state.pipeline.term_agent.transport=transport
    return app,transport


def source(ident='in',side='internal'):
    return {'evidence_id':ident,'side':side,'document_id':ident,'metadata':{'document_name':'모의내규 A','heading':'제2장 제3조 제1항'},
        'spans':[{'text':'승인 후 보고한다. | <원문>\n단서는 보존한다.'}],'text':'승인 후 보고한다. | <원문>\n단서는 보존한다.',
        'generation_id':'g','source_artifact_hash':'fixed'}


def concept(s):
    return {'existing_id':None,'request_issue_id':'question-1','label':'승인','definition':'승인·보고',
        'scope_reason':'조건과 의무','internal_citations':[{'evidence':s['evidence_id'],'quote':s['spans'][0]['text']}],
        'external_task':'승인 원문 확인','external_queries':['승인'],'numeric':False,'work_type':'general','requested_fields':['obligation']}


@pytest.mark.parametrize('defect',['none','wrong_side','false_quote','unknown_source','unknown_issue','duplicate_field','too_many'])
def test_concept_rejects_integrity_errors_without_inventing_semantics(defect):
    s=source();row=concept(s);value={'concepts':[row],'unresolved':[]}
    if defect=='wrong_side':s['side']='external'
    if defect=='false_quote':row['internal_citations'][0]['quote']='없는 원문'
    if defect=='unknown_source':row['internal_citations'][0]['evidence']='unknown'
    if defect=='unknown_issue':row['request_issue_id']='unknown'
    if defect=='duplicate_field':row['requested_fields']*=2
    if defect=='too_many':value['concepts']*=13
    before=deepcopy(value)
    if defect=='none':
        concepts.validate(value,[s],[{'id':'question-1'}],[])
    else:
        with pytest.raises(ValueError):concepts.validate(value,[s],[{'id':'question-1'}],[])
    assert value==before


@pytest.mark.parametrize('defect',['none','acl','quote','heading','document','side','issue'])
def test_external_task_anchors_verify_actual_parent_sources(defect):
    s=source();c=concept(s);c.pop('existing_id');c['id']='concept-1'
    a=concepts.anchors({'concept_plan':{'concepts':[c]}},[s])
    task={'source_category':'external','issues':[{'id':'concept-1'}]}
    port=S(verify_all=lambda:None,evidence=lambda:[s],all_scope=['in'])
    if defect=='acl':port.all_scope=[]
    if defect=='quote':a[0]['sources'][0]['quote']='없는 원문'
    if defect=='heading':a[0]['sources'][0]['heading']='제99조'
    if defect=='document':a[0]['sources'][0]['document_id']='outside'
    if defect=='side':task['source_category']='internal'
    if defect=='issue':a[0]['issue_id']='another'
    if defect=='none':
        validate_internal_anchors(a,task);verify_anchors(port,a)
    else:
        with pytest.raises(ContractError):
            validate_internal_anchors(a,task);verify_anchors(port,a)


def test_table_has_locations_and_literal_originals_in_same_row_without_mutation():
    s=source();c=concept(s);c.pop('existing_id');c['id']='concept-1'
    state={'concept_plan':{'concepts':[c]},'question_scope':{'issues':[{'id':'question-1'}]}}
    body={'comparison_items':{'items':[]},'assembly':{'term_agent':{'source_bundle':{'sources':[]}}},
        'report':{},'answer':{},'evidence_refs':[],'evidence_summary':{},'unresolved':['외규 미확보']}
    ctx=S(request={'question':'승인 기준 대사','as_of':None})
    before=deepcopy(state)
    result=concept_report.apply(ctx,state,body,{'in':s})
    html=MarkdownIt('commonmark',{'html':True}).enable('table').render(result['answer']['text'])
    assert html.count('<th>')==3 and html.count('<td>')==3
    assert '<details>' in html and '<summary>' in html
    assert '모의내규 A' in html and '제2장 제3조 제1항' in html and '&lt;원문&gt;' in html
    assert '단서는 보존한다.' in html and '해당 규정이 없다는 뜻은 아닙니다' in html
    assert result['comparison_table']['rows'][0]['internal'][0]['quote']==s['text']
    assert state==before


@pytest.mark.parametrize('route',['/v1/rag/ask','/v1/workflows/run'])
def test_api_internal_then_concepts_then_anchored_external_saved_duplicate_and_stream(tmp_path,tree,route):
    from semantic_runtime.legal_agent.answer_stream import capture
    app,t=application(tmp_path,tree,count=2);events=[]
    with TestClient(app) as client:
        with capture(fixture.prior.BODY['request_id'],events.append):
            response=client.post(route,json=fixture.prior.BODY)
        assert response.status_code==200,response.text
        body=response.json()
        assert body.get('comparison_table'),body
        rows=body['comparison_table']['rows'];assert len(rows)==2,body
        assert all(r['internal'] and r['external'] for r in rows),body
        stages=[s for s,_ in t.views]
        index=stages.index('workflow-concepts')
        before=[v for _,v in t.views[:index] if v.get('workflow_task')]
        after=[v for _,v in t.views[index+1:] if v.get('workflow_task',{}).get('source_category')=='external']
        assert before and all(v['workflow_task']['source_category']=='internal' for v in before)
        assert after and len(after[0]['workflow_task']['internal_anchors'])==2
        assert all(a['sources'][0]['quote'] for a in after[0]['workflow_task']['internal_anchors'])
        assert ''.join(e['text'] for e in events)==body['answer']['text']
        assert views()._public_answer_text(body)==body['answer']['text']
        count=len(t.views)
        again=client.post(route,json=fixture.prior.BODY).json()
        saved=client.get('/v1/workflows/runs/'+body['run_id'],params={'session_id':'s'}).json()
        assert again['comparison_table']==saved['comparison_table']==body['comparison_table']
        assert again['answer']==saved['answer']==body['answer'] and len(t.views)==count


def test_bad_concept_exhausts_one_repair_keeps_internal_and_never_starts_external(tmp_path,tree):
    app,t=application(tmp_path,tree,bad=True)
    with TestClient(app) as client:
        result=client.post('/v1/workflows/run',json=fixture.prior.BODY)
    assert result.status_code==200,result.text
    body=result.json()
    assert body['status']=='partial' and body['comparison_table']['rows'],body
    assert sum(s=='workflow-concepts' for s,_ in t.views)==2
    assert not any(v.get('workflow_task',{}).get('source_category')=='external' for _,v in t.views)
    assert '개념 검토 추가 확인 필요' in body['answer']['text'] and body['evidence_refs']
    assert '미완료' not in body['answer']['text']


def test_resume_after_concept_commit_does_not_repeat_model_or_reset_deadline(tmp_path,tree,monkeypatch):
    app,t=application(tmp_path,tree);hits=[]
    definition=app.state.workflow_runtime.registry.resolve('risk_team_compare_workflow',None,'risk_team')
    owner=importlib.import_module(definition.entrypoint.__module__.rsplit('.',1)[0]+'.concepts')
    original=owner.prepare
    def stop(ctx,state):
        result=original(ctx,state);hits.append(len(t.views))
        if len(hits)==1:raise KeyboardInterrupt('synthetic interruption after concept commit')
        return result
    monkeypatch.setattr(owner,'prepare',stop)
    with pytest.raises(KeyboardInterrupt):
        result=app.state.workflow_runtime.execute({**fixture.prior.BODY,'workflow_id':'risk_team_compare_workflow'},
                                                 fixture.prior.prior._base.PRINCIPAL)
        pytest.fail(str({'status':result.get('status'),'error':result.get('error_code'),'unresolved':result.get('unresolved'),'stages':[s for s,_ in t.views]}))
    journal=next(app.state.workflow_runtime.root.glob('*/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        revision=db.execute('SELECT revision FROM workflow_state').fetchone()[0]
        deadline=db.execute('SELECT deadline_at FROM run').fetchone()[0]
    with TestClient(app) as client:
        result=client.post('/v1/workflows/resume',json={'run_id':journal.parent.name,'session_id':'s','expected_revision':revision})
    assert result.status_code==200,result.text
    assert result.json()['comparison_table']['rows'] and hits[0]==hits[1]
    assert sum(s=='workflow-concepts' for s,_ in t.views)==1
    with sqlite3.connect(journal) as db:
        assert db.execute('SELECT deadline_at FROM run').fetchone()[0]==deadline


def test_repaired_concept_uses_same_originals_and_does_not_repeat_on_duplicate(tmp_path,tree):
    app,t=application(tmp_path,tree,bad=1)
    with TestClient(app) as client:
        response=client.post('/v1/workflows/run',json=fixture.prior.BODY)
        assert response.status_code==200,response.text
        body=response.json();assert body['report']['rows'],body
        plans=[v for s,v in t.views if s=='workflow-concepts']
        assert len(plans)==2 and plans[0]['sources']==plans[1]['sources']
        count=len(t.views)
        assert client.post('/v1/workflows/run',json=fixture.prior.BODY).json()['comparison_table']==body['comparison_table']
        assert len(t.views)==count


def test_no_internal_does_not_start_question_only_external_search(tmp_path,tree):
    app,t=application(tmp_path,tree)
    principal={**fixture.prior.prior._base.PRINCIPAL,'document_ids':['outside']}
    value=app.state.workflow_runtime.execute({**fixture.prior.BODY,'workflow_id':'risk_team_compare_workflow'},principal)
    assert value['status']!='completed' and value['concept_plan']['status']=='NO_INTERNAL_ORIGINALS'
    assert not any(v.get('workflow_task',{}).get('source_category')=='external' for _,v in t.views)
    assert '연결할 내규' in value['answer']['text'] or '내규 원문 미확보' in value['answer']['text']


def test_budget_stop_keeps_internal_originals_without_external_call(tmp_path,tree,monkeypatch):
    app,t=application(tmp_path,tree)
    service=app.state.workflow_runtime.services
    original=service.structured
    def exhausted(work,context,stage,*args):
        if stage=='CONCEPTS':raise service.BudgetExhausted('synthetic shared budget exhausted')
        return original(work,context,stage,*args)
    monkeypatch.setattr(service,'structured',exhausted)
    with TestClient(app) as client:
        response=client.post('/v1/workflows/run',json=fixture.prior.BODY)
    assert response.status_code==200,response.text
    body=response.json()
    assert body['status']=='partial' and body['comparison_table']['rows'][0]['internal']
    assert not any(v.get('workflow_task',{}).get('source_category')=='external' for _,v in t.views)
