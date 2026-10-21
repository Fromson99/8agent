"""Synthetic API contracts; no external model or legal accuracy claim."""
from copy import deepcopy
import json,sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import importlib.util
_spec=importlib.util.spec_from_file_location('tasks_base_811',Path(__file__).parents[1]/'adr_0811/test_handoff_orchestration.py')
_base=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_base)
tree,application,BODY,Transport=_base.tree,_base.application,_base.BODY,_base.Transport
from test_legal_agent_double_harness import wire
from semantic_runtime.legal_agent.errors import TransportError

class TaskTransport(Transport):
    def __init__(self,mode='normal'):super().__init__();self.task_mode=mode;self.item_count=0
    def send_once(self,*,body,ticket):
        view=json.loads(body['messages'][1]['content'])['view'];stage=view.get('source_stage',view['phase'])
        from semantic_runtime.legal_agent.workflow_execution import has_reentry
        if self.task_mode=='failed_followup' and has_reentry():raise TransportError('synthetic followup failure',unknown=True)
        if stage=='workflow-items':
            self.views.append((stage,deepcopy(view)));self.item_count+=1;rows=[]
            for field in view['fields']:
                item={'field':field,'content_status':'MATCH','difference':'모의 확인 문구 동일','next_tasks':[]}
                for side in ('internal','external'):
                    values=[e for e in view['sources'] if e['side']==side]
                    item[side]={'status':'CONFIRMED' if values else 'MISSING','text':'승인 후 보고한다.' if values else '',
                        'citations':[{'citation_id':values[0]['citation_options'][0]['citation_id']}] if values else [],
                        'dependencies':[],'scope_sufficient':bool(values),'missing':'' if values else '대응 원문 미확보'}
                if not all(item[s]['citations'] for s in ('internal','external')):item.update(content_status='UNKNOWN',difference='')
                if self.task_mode in ('followup','failed_followup') and self.item_count==1 and field==next(iter(view['fields'])):
                    locid,loc=next((k,v) for k,v in view['locators'].items() if v['side']=='internal')
                    item['internal'].update(status='PARTIAL',scope_sufficient=False,missing='담당 확인')
                    item['next_tasks']=[{'side':'internal','operation':'read_node','locator_id':locid,'query':'담당 확인','anchor_ids':[loc['origin_evidence_id']],'reason':'해당 위치의 담당 확인'}]
                rows.append(item)
            return wire({'items':rows})
        return super().send_once(body=body,ticket=ticket)

def task_app(tmp_path,tree,mode='normal'):
    app,_=application(tmp_path,tree);t=TaskTransport(mode);app.state.pipeline.term_agent.transport=t
    return app,t

@pytest.mark.parametrize('mode',['normal','followup','failed_followup'])
def test_task_rows_native_followup_failure_and_duplicate(tmp_path,tree,mode):
    app,t=task_app(tmp_path,tree,mode)
    with TestClient(app) as c:
        r=c.post('/v1/rag/ask',json=BODY);assert r.status_code==200,r.text
        v=r.json();assert v.get('comparison_items'),v
        items=v['comparison_items']['items'];assert len(items)==5,v
        assert all(i['external']['citations'] for i in items),v
        if mode=='failed_followup':
            assert v['rag_results']['internal']['evidence_ids']
            assert v['latest_rag_attempts']['internal']['status']=='failed'
            assert all(i['internal']['citations'] for i in items)
            assert v['status']=='partial'
        if mode=='followup':assert any(a['status']=='COMPLETE' for a in v['research_attempts'].values()),v
        count=len(t.views);again=c.post('/v1/rag/ask',json=BODY)
        assert again.status_code==200 and {k:x for k,x in again.json().items() if k!='execution_stats'}=={k:x for k,x in v.items() if k!='execution_stats'} and len(t.views)==count
        saved=c.get('/v1/workflows/runs/'+v['run_id'],params={'session_id':'s'}).json()
        assert saved['answer']==v['answer'] and saved['comparison_items']==v['comparison_items']
    path=app.state.workflow_runtime.root/v['run_id']/'journal.sqlite'
    with sqlite3.connect(path) as db:
        checkpoint=json.loads(db.execute('SELECT checkpoint_json FROM workflow_state').fetchone()[0])
        assert checkpoint['task_board']['schema_version']=='comparison-research-v1'
        assert len(checkpoint['rag_valid_results']['internal'])>=1

def test_cross_side_claim_and_unread_completion_are_rejected():
    from workflow.risk_team_compare_workflow.task_board import checked
    e={'evidence_id':'e','side':'external','spans':[{'text':'외규'}]}
    side={'status':'CONFIRMED','text':'외규','citations':[{'evidence':'e','quote':'외규'}],'dependencies':[],'scope_sufficient':True,'missing':''}
    value={'items':[{'field':'subject','internal':side,'external':side,'content_status':'MATCH','difference':'동일','next_tasks':[]}]}
    with pytest.raises(ValueError,match='opposite-side'):checked(value,[e],['subject'],{})


def test_technical_missing_is_not_legal_absence(tmp_path,tree):
    app,t=task_app(tmp_path,tree,'failed_followup')
    with TestClient(app) as c:
        out=c.post('/v1/rag/ask',json=BODY).json()
    assert '조회 실패는 규정 부재' in out['answer']['text']
    assert out['evidence_refs'] and out['quality_certified'] is False

@pytest.mark.parametrize('mutation',['request','acl','revision','result','child_record','generation'])
def test_saved_task_response_rejects_tamper(tmp_path,tree,mutation):
    principal=deepcopy(_base.PRINCIPAL);app,_=_base.application(tmp_path,tree,principal=principal)
    t=TaskTransport();app.state.pipeline.term_agent.transport=t
    with TestClient(app,raise_server_exceptions=False) as c:
        first=c.post('/v1/rag/ask',json=BODY);assert first.status_code==200,first.text
        out=first.json();count=len(t.views);body=deepcopy(BODY)
        journal=app.state.workflow_runtime.root/out['run_id']/'journal.sqlite'
        if mutation=='request':body['question']='대사: 다른 질문'
        elif mutation=='acl':principal['document_ids']=['outside']
        elif mutation=='result':
            with sqlite3.connect(journal) as db:db.execute("UPDATE workflow_state SET result_json='{}'")
        elif mutation=='child_record':
            path=next(journal.parent.glob('children/internal/legal-agent/runs/*/*/journal.sqlite'))
            with sqlite3.connect(path) as db:
                for name, in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='observation'").fetchall():db.execute('DROP TRIGGER "'+name+'"')
                db.execute("UPDATE observation SET result_json='{}'")
        elif mutation=='generation':
            p=tree[0]/'manifest.json';value=json.loads(p.read_text());value['generation_id']='changed';p.write_text(json.dumps(value))
        if mutation in ('acl','revision'):
            result=c.post('/v1/workflows/resume',json={'run_id':out['run_id'],'session_id':'s','expected_revision':out['revision']-(mutation=='revision')})
        else:result=c.post('/v1/rag/ask',json=body)
        assert result.status_code in ((422,) if mutation=='generation' else (403,404,409,500)),result.text
        assert len(t.views)==count


def test_interruption_reuses_native_child_and_original_deadline(tmp_path,tree,monkeypatch):
    from semantic_runtime import workflow_rag
    app,t=task_app(tmp_path,tree);original=workflow_rag.execute;calls=[]
    def interrupt(port,action,call_id):
        result=original(port,action,call_id);calls.append((action['side'],len(t.views)))
        if len(calls)==1:raise KeyboardInterrupt('after native commit before parent receipt')
        return result
    monkeypatch.setattr(workflow_rag,'execute',interrupt)
    with pytest.raises(KeyboardInterrupt):app.state.workflow_runtime.execute({**BODY,'workflow_id':'risk_team_compare_workflow'},_base.PRINCIPAL)
    p=next(app.state.workflow_runtime.root.glob('*/journal.sqlite'))
    with sqlite3.connect(p) as db:
        revision=db.execute('SELECT revision FROM workflow_state').fetchone()[0];deadline=db.execute('SELECT deadline_at FROM run').fetchone()[0]
    count=len(t.views)
    with TestClient(app) as c:
        out=c.post('/v1/workflows/resume',json={'run_id':p.parent.name,'session_id':'s','expected_revision':revision})
        assert out.status_code==200,out.text
        assert out.json()['comparison_items']['items'] and calls[1]==('internal',count)
    with sqlite3.connect(p) as db:assert db.execute('SELECT deadline_at FROM run').fetchone()[0]==deadline


def test_missing_internal_keeps_external_field_rows(tmp_path,tree):
    app,_=_base.application(tmp_path,tree,principal={**_base.PRINCIPAL,'document_ids':['outside']})
    t=TaskTransport();app.state.pipeline.term_agent.transport=t
    with TestClient(app) as c:out=c.post('/v1/rag/ask',json=BODY).json()
    assert out['rag_results']['internal']['status']=='not_registered'
    assert all(i['internal']['status']=='MISSING' and i['external']['citations'] for i in out['comparison_items']['items'])
    assert all(c['side']=='external' for c in out['assembly']['term_agent']['source_bundle']['sources'])
    assert out['status']=='partial'


def test_no_model_keeps_every_requested_item_unknown(tmp_path,tree):
    app,t=task_app(tmp_path,tree)
    with TestClient(app) as c:out=c.post('/v1/rag/ask',json={**BODY,'use_llm':False}).json()
    assert not t.views
    assert len(out['comparison_items']['items'])==5
    assert all(i['content_status']=='UNKNOWN' for i in out['comparison_items']['items'])


@pytest.mark.parametrize('budget',[4,9])
def test_budget_stop_keeps_rows_and_never_replenishes(tmp_path,tree,budget):
    app,_=_base.application(tmp_path,tree,limit=budget);t=TaskTransport();app.state.pipeline.term_agent.transport=t
    with TestClient(app) as c:
        r=c.post('/v1/rag/ask',json=BODY);assert r.status_code==200,r.text
        out=r.json();assert out['comparison_items']['items'] and out['status'] in ('partial','failed')
        assert out['usage']['model_reserved']<=budget
        count=len(t.views);c.post('/v1/rag/ask',json=BODY);assert len(t.views)==count

@pytest.mark.parametrize('operation',['locate_provision','lookup_definition','follow_reference','search_structure','search_subtree','search_text'])
def test_requested_native_tools_are_executed_in_child_journal(tmp_path,tree,operation,request):
    if operation=='follow_reference':tree=request.getfixturevalue('reference_tree')
    class Tools(TaskTransport):
        def send_once(self,*,body,ticket):
            view=json.loads(body['messages'][1]['content'])['view'];stage=view.get('source_stage',view['phase'])
            if operation=='follow_reference' and stage.startswith('memory-assess'):
                from test_source_span_norm import proposal
                options=view['evidence_options'];option=next(o for o in options if '승인 후 보고한다.' in o['text'])
                return wire(proposal(option['text'],'OBLIGATION',[o['id'] for o in options],option['id']))
            result=super().send_once(body=body,ticket=ticket)
            if stage=='workflow-items' and self.item_count==1:
                value=json.loads(result['body_json']['choices'][0]['message']['content'])
                row=value['items'][0];side='external' if operation=='follow_reference' else 'internal'
                lid,loc=next((k,v) for k,v in view['locators'].items() if v['side']==side and (operation!='follow_reference' or v.get('reference_id')))
                row[side].update(status='PARTIAL',scope_sufficient=False,missing='지정 범위 확인')
                row['next_tasks']=[{'side':side,'operation':operation,'locator_id':lid if operation not in ('lookup_definition','search_text','search_structure') else None,
                    'query':'제1조' if operation=='locate_provision' else '승인','anchor_ids':[loc['origin_evidence_id']],'reason':'합성 도구 연결 검사'}]
                return wire(value)
            return result
    app,_=task_app(tmp_path,tree);t=Tools();app.state.pipeline.term_agent.transport=t
    with TestClient(app) as c:
        response=c.post('/v1/rag/ask',json=BODY);assert response.status_code==200,response.text
        out=response.json();assert out['research_attempts'],out
        assert all(a['status']=='COMPLETE' for a in out['research_attempts'].values()),out
    seen=[]
    for p in (app.state.workflow_runtime.root/out['run_id']).rglob('journal.sqlite'):
        with sqlite3.connect(p) as db:
            seen.extend((kind,json.loads(payload)) for kind,payload in db.execute("SELECT kind,payload_json FROM event WHERE kind='COMPARISON_TASK_ACQUIRED'"))
    assert seen and seen[-1][1]['absence_proven'] is False


def test_multiple_issues_and_ratio_profiles_keep_distinct_rows():
    from types import SimpleNamespace
    from workflow.risk_team_compare_workflow.task_board import initialize,CONFIG
    state={'scope':{'issues':[{'id':'a','numeric':True},{'id':'b','numeric':False,'work_type':'authority','requested_fields':['authority','exceptions']}]}}
    initialize(SimpleNamespace(repo=SimpleNamespace(save=lambda s:None)),state)
    assert {k for k in state['task_board']['rows'] if k.startswith('a:')}=={'a:'+f for f in CONFIG['profiles']['ratio']}
    assert {k for k in state['task_board']['rows'] if k.startswith('b:')}=={'b:authority','b:exceptions'}


def test_conflict_keeps_prior_sources_and_cannot_publish_match(tmp_path,tree):
    class Changed(TaskTransport):
        def send_once(self,*,body,ticket):
            result=super().send_once(body=body,ticket=ticket)
            view=json.loads(body['messages'][1]['content'])['view']
            if view.get('source_stage')=='workflow-items' and self.item_count>1:
                value=json.loads(result['body_json']['choices'][0]['message']['content'])
                value['items'][0]['internal']['text']='보고한다.'
                return wire(value)
            return result
    app,_=task_app(tmp_path,tree);app.state.pipeline.term_agent.transport=Changed('followup')
    with TestClient(app) as c:out=c.post('/v1/rag/ask',json=BODY).json()
    row=next(i for i in out['comparison_items']['items'] if i['internal'].get('alternatives'))
    assert row['internal']['status']=='CONFLICT' and row['internal']['alternatives'][0]['citations']
    assert row['content_status']=='UNKNOWN' and not row['difference']
    assert '이전 확인(재검토)' in out['answer']['text']


def test_followup_interrupted_after_parent_save_replays_same_call(tmp_path,tree,monkeypatch):
    import importlib
    app,t=task_app(tmp_path,tree,'followup')
    definition=app.state.workflow_runtime.registry.resolve('risk_team_compare_workflow',None,'risk_team')
    retrieval=importlib.import_module(definition.entrypoint.__module__.rsplit('.',1)[0]+'.retrieval')
    original=retrieval.discover;stopped=[]
    def interrupt(*args,**kwargs):
        value=original(*args,**kwargs)
        if kwargs.get('research_task') and not stopped:stopped.append(True);raise KeyboardInterrupt('after parent result before task completion')
        return value
    monkeypatch.setattr(retrieval,'discover',interrupt)
    with pytest.raises(KeyboardInterrupt):app.state.workflow_runtime.execute({**BODY,'workflow_id':'risk_team_compare_workflow'},_base.PRINCIPAL)
    p=next(app.state.workflow_runtime.root.glob('*/journal.sqlite'))
    with sqlite3.connect(p) as db:
        revision=db.execute('SELECT revision FROM workflow_state').fetchone()[0]
        count=db.execute("SELECT count(*) FROM workflow_call WHERE kind='rag'").fetchone()[0]
    with TestClient(app) as c:
        r=c.post('/v1/workflows/resume',json={'run_id':p.parent.name,'session_id':'s','expected_revision':revision});assert r.status_code==200,r.text
    with sqlite3.connect(p) as db:assert db.execute("SELECT count(*) FROM workflow_call WHERE kind='rag'").fetchone()[0]==count
    assert all(a['status']=='COMPLETE' for a in r.json()['research_attempts'].values())

from test_successful_core_routes import routes

def test_existing_route_storage_revalidates_comparison_fields(routes):
    from semantic_runtime.legal_agent import core_evidence_route as core
    from semantic_runtime.legal_agent.workflow_execution import child_execution
    from types import SimpleNamespace
    r=routes;task={'source_category':'internal','comparison_fields':{'i1':['authority','exceptions']}}
    state=json.loads(r.cases.db.execute('SELECT state FROM goal').fetchone()[0])
    with child_execution(None,SimpleNamespace(), 'fixture',r.p['document_ids'],task=task):
        core.finalize(r.cases,r.result,r.p)
        path=core.lookup(r.host,state,r.p)
        assert path['comparison_context']['fields']==task['comparison_fields']
        assert path['comparison_context']['comparison_conclusion_reuse'] is False
        task['comparison_fields']['i1']=['authority']
        assert core.lookup(r.host,state,r.p) is None
    assert core.lookup(r.host,state,r.p) is None
    assert r.cases.db.execute('SELECT count(*) FROM sw_unit').fetchone()[0]==1


@pytest.fixture
def reference_tree(tmp_path,term_glossary):
    folder=tmp_path/'reference';folder.mkdir()
    raw=_base.source(folder/'raw.sqlite',[
        ('inside','모의내규',['제1조(승인) 모의승인규정 제1조에 따라 승인 후 보고한다.']),
        ('outside','모의승인규정',['제1조(승인) 승인 후 보고한다.'])])
    with sqlite3.connect(raw) as db:
        for did,category in [('inside','internal'),('outside','external')]:
            db.execute('UPDATE document SET json=? WHERE document_id=?',(json.dumps({'document_category':category,
                'document_metadata':{'team':'risk_team'},'workflow_version':{'verified':True,'valid_from':'2020-01-01','valid_to':None}}),did))
    _base.build_generation(raw,term_glossary,folder/'built',serving=True)
    gen=folder/'built/generation';index=folder/'index';_base.build(gen,gen/'navigation',index,workers=1)
    return gen,_base.UnitFulltextIndex(index,json.loads((gen/'navigation/manifest.json').read_text()))


def test_same_annex_issue_spans_do_not_expand_and_exceptions_stay():
    from types import SimpleNamespace as NS
    from workflow.presentation import packets
    from workflow.risk_team_compare_workflow.task_board import sources_for_issue
    data=[]
    for n,text in enumerate(['승인 원칙','단, 긴급 보고는 예외','다른 업무의 표 항목'*1000]):
        data.append({'evidence_id':'E'+str(n),'source_id':'annex','document_id':'inside','side':'internal',
          'metadata':{'document_name':'모의 별표'},'text':text,'version_verified':True,'citation_names':[],
          'spans':[{'block_id':str(n),'start_cp':0,'end_cp':len(text),'text':text}]})
    native=type('Native',(),{'__module__':'semantic_runtime.workflow_bridge'})()
    port=NS(services=native,session=NS(tools=NS(sources={'annex':{'id':'annex','blocks':[{'block_id':str(n),'text':e['text']} for n,e in enumerate(data)]}})))
    ctx=NS(rag=NS(evidence=lambda:data,port=port),request={'question':'승인과 예외','as_of':None},
       repo=NS(work=NS(budget=lambda:{}),save=lambda _:None),context=NS(deadline_at='fixed'),model=NS(services=NS(profile={'max_context_chars':12000})))
    state={'scope':{},'gaps':[],'task_board':{'schema_version':'comparison-research-v1'},'rag_results':{'internal':{
      'side':'internal','status':'completed','evidence_ids':['E0','E1','E2'],'bundle':{'claims':[
        {'evidence_ids':['E0','E1'],'parent_issue_refs':['approval']},{'evidence_ids':['E2'],'parent_issue_refs':['other']}]}}}}
    relevant=sources_for_issue(ctx,state,'approval');assert {e['evidence_id'] for e in relevant}=={'E0','E1'}
    result=packets(ctx,state,'ITEMS',ids=['E0','E1'])
    assert {e['evidence_id'] for _,es in result for e in es}=={'E0','E1'}
    assert all(not e['source_complete'] for _,es in result for e in es)
    assert any('예외' in e['text'] for _,es in result for e in es)


def test_bad_internal_proposal_keeps_verified_external_and_failed_receipts(tmp_path,tree):
    class BadSide(TaskTransport):
        def send_once(self,*,body,ticket):
            result=super().send_once(body=body,ticket=ticket)
            view=json.loads(body['messages'][1]['content'])['view']
            if view.get('source_stage')=='workflow-items':
                value=json.loads(result['body_json']['choices'][0]['message']['content'])
                for item in value['items']:
                    item['internal'].update(status='MISSING',text='확인되지 않음',citations=[],scope_sufficient=False,missing='내규 담당 확인')
                    item['content_status']='DIFFERENT';item['difference']='한쪽 미확보는 차이가 아니다';item['next_tasks']=[]
                return wire(value)
            return result
    app,_=task_app(tmp_path,tree);t=BadSide();app.state.pipeline.term_agent.transport=t
    with TestClient(app) as c:
        response=c.post('/v1/rag/ask',json=BODY);assert response.status_code==200,response.text
        out=response.json();rows=out['comparison_items']['items']
        assert all(r['external']['citations'] and r['internal']['status']=='MISSING' and r['content_status']=='UNKNOWN' for r in rows)
        assert out['status']=='partial' and len(out['item_validation_failures'])==2
        assert out['assembly']['term_agent']['source_bundle']['sources']
        count=len(t.views);again=c.post('/v1/rag/ask',json=BODY);assert again.json()['answer']==out['answer'] and len(t.views)==count
    with sqlite3.connect(app.state.workflow_runtime.root/out['run_id']/'journal.sqlite') as db:
        rejected=db.execute("SELECT status FROM workflow_call WHERE kind='model' AND json_extract(input_json,'$.stage')='ITEMS'").fetchall()
        assert rejected==[('FAILED',),('FAILED',)]
    assert all(not e['original_proposal_accepted'] for e in out['item_validation_failures'])


def test_saved_live_qwen_proposals_keep_own_source_and_reject_invalid_side():
    from workflow.risk_team_compare_workflow.task_board import partial_items
    root=Path(__file__).parents[3]/'04_EXPERIMENTS/ADR/ADR-0820-comparison-task-live-check/artifacts/run-001/risk-104/raw'
    for folder in sorted(root.glob('*workflow-items*')):
        request=json.loads((folder/'request.json').read_text())
        view=next(json.loads(m['content'])['view'] for m in request['messages'] if m.get('role')=='user')
        sources=[];citations={}
        for source in view['sources']:
            sources.append({**source,'spans':[{'text':c['text']} for c in source['citation_options']]})
            for c in source['citation_options']:citations[c['citation_id']]={'evidence':source['evidence_id'],'quote':c['text']}
        raw=json.loads(json.loads((folder/'response.json').read_text())['choices'][0]['message']['content'])
        def resolve(v):
            if isinstance(v,list):return [resolve(x) for x in v]
            if isinstance(v,dict):return deepcopy(citations[v['citation_id']]) if set(v)=={'citation_id'} else {k:resolve(x) for k,x in v.items()}
            return v
        value,errors=partial_items(resolve(raw),sources,list(view['fields']),view['locators'])
        assert errors and len(value['items'])==4
        assert all(i['external']['citations'] and i['external']['text'] and i['internal']['status']=='MISSING' and not i['internal']['text'] and i['content_status']=='UNKNOWN' for i in value['items'])


@pytest.mark.parametrize('failure',['budget','transport'])
def test_partial_valid_side_survives_repair_interruption(tmp_path,tree,failure):
    from semantic_runtime.legal_agent.errors import BudgetExhausted
    class Interrupted(TaskTransport):
        def send_once(self,*,body,ticket):
            view=json.loads(body['messages'][1]['content'])['view']
            if view.get('source_stage')=='workflow-items' and self.item_count:
                if failure=='budget':raise BudgetExhausted('synthetic exhausted correction budget')
                raise TransportError('synthetic unknown correction outcome',unknown=True)
            result=super().send_once(body=body,ticket=ticket)
            if view.get('source_stage')=='workflow-items':
                value=json.loads(result['body_json']['choices'][0]['message']['content'])
                for item in value['items']:
                    item['internal'].update(status='MISSING',text='not a finding',citations=[],scope_sufficient=False,missing='담당 확인')
                    item.update(content_status='UNKNOWN',difference='',next_tasks=[])
                return wire(value)
            return result
    app,_=task_app(tmp_path,tree);app.state.pipeline.term_agent.transport=Interrupted()
    with TestClient(app) as c:
        response=c.post('/v1/rag/ask',json=BODY);assert response.status_code==200,response.text
        out=response.json();assert out['status']=='partial'
        assert all(i['external']['citations'] and not i['internal']['citations'] for i in out['comparison_items']['items'])
        assert out['item_validation_failures']
