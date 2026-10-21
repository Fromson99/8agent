from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as S
import importlib.util,json
import jsonschema,pytest
from fastapi.testclient import TestClient
from workflow.risk_team_compare_workflow import task_board as tb,query_scope as qs
from workflow.adapters import projection
from test_legal_agent_double_harness import wire


def context():
    return S(definition=S(manifest={'research_policy':qs.POLICY,'max_recoveries':2}),repo=S(save=lambda _:None))


def test_numeric_is_not_implicit_ratio_and_legacy_stays_available():
    issue={'id':'i','numeric':True};state={'scope':{'issues':[deepcopy(issue)]}}
    tb.initialize(context(),state)
    assert state['scope']['issues'][0]['work_type']=='general'
    assert 'numerator' not in state['scope']['issues'][0]['requested_fields']
    ctx=context();ctx.definition.manifest.pop('research_policy');old={'scope':{'issues':[issue]}}
    tb.initialize(ctx,old);assert 'numerator' in issue['requested_fields']


@pytest.mark.parametrize('defect',['none','selectors','quote'])
def test_intake_requires_explicit_fields_and_literal_question_grounding(defect):
    ctx=context();ctx.request={'use_llm':True,'question':'기준이 나빠지면 필요한 조치와 예외는?','as_of':None}
    value={'issues':[{'id':'i','label':'필요 조치','numeric':True,'internal_task':'내규의 필요한 조치','external_task':'외규의 필요한 조치',
        'work_type':'general','requested_fields':['obligation','exceptions'],'requirements':[{'request_quote':'필요한 조치','need':'상태 변화에 따른 조치'}]}],
        'internal_queries':['필요 조치'],'external_queries':['필요 조치'],'scope_note':'질문 범위','facts':[],'missing_user_facts':[]}
    if defect=='selectors':value['issues'][0].pop('requested_fields')
    if defect=='quote':value['issues'][0]['requirements'][0]['request_quote']='질문에 없는 요구'
    def decide(stage,data,schema,instructions,check):
        jsonschema.validate(value,schema);check(value);return value
    ctx.model=S(decide=decide)
    if defect=='none':assert qs.prepare(ctx)['issues'][0]['requested_fields']==['obligation','exceptions']
    else:
        with pytest.raises((ValueError,jsonschema.ValidationError)):qs.prepare(ctx)


def record(ident,priority,order,exact=False,status='PENDING'):
    return {'status':status,'priority':priority,'queue_order':order,'task':{'task_id':ident,'target_locator':{'id':'x'} if exact else None}}


def test_priority_exact_tie_and_resume_order_survive_serialization():
    rows=[record('background','CONTEXT',0,True),record('search','CORE',1),record('read','CORE',2,True),record('dependency','DEPENDENCY',3,True)]
    board={'tasks':{r['task']['task_id']:r for r in rows}}
    assert [r['task']['task_id'] for r in tb.pending_tasks(board,False)]==['background','search','read','dependency']
    restored=json.loads(json.dumps(board,sort_keys=True))
    assert [r['task']['task_id'] for r in tb.pending_tasks(restored,True)]==['read','dependency','search','background']
    restored['tasks']['background']['status']='RUNNING'
    assert tb.pending_tasks(restored,True)[0]['task']['task_id']=='background'


def test_exhausted_followup_budget_does_not_reset_or_touch_pending():
    board={'round':2,'tasks':{'x':record('x','CORE',0,True)}};before=deepcopy(board)
    assert not tb.research(context(),{'task_board':board});assert board==before


def update_fixture():
    source={'evidence_id':'new','side':'external','spans':[{'text':'변경 시 책임자가 재검토한다.'}]}
    missing={'status':'MISSING','text':'','citations':[],'dependencies':[],'scope_sufficient':False,'missing':'내규 미확인'}
    found={'status':'CONFIRMED','text':'변경 시 책임자 재검토','citations':[{'evidence':'new','quote':source['spans'][0]['text']}],'dependencies':[],'scope_sufficient':True,'missing':''}
    item={'field':'obligation','internal':missing,'external':found,'content_status':'UNKNOWN','difference':'내규 미확인','next_tasks':[]}
    value={'evidence_updates':[{'evidence_id':'new','disposition':'USED','fields':['obligation'],'reason':'새 원문이 조치의 주체와 내용을 확인함'}],'items':[item]}
    return source,value


@pytest.mark.parametrize('defect',['none','omitted','unknown','no_item','wrong_side','quote','duplicate','bad_field'])
def test_new_source_disposition_and_actual_changed_citation_are_bound(defect):
    source,value=update_fixture()
    if defect=='omitted':value['evidence_updates']=[]
    if defect=='unknown':value['evidence_updates'][0]['evidence_id']='invented'
    if defect=='no_item':value['items']=[]
    if defect=='wrong_side':value['items'][0]['internal'],value['items'][0]['external']=value['items'][0]['external'],value['items'][0]['internal']
    if defect=='quote':value['items'][0]['external']['citations'][0]['quote']='없는 원문'
    if defect=='duplicate':value['evidence_updates']*=2
    if defect=='bad_field':value['evidence_updates'][0]['fields']=['exceptions']
    def check():
        jsonschema.validate(value,tb.review_contract(['obligation','condition'],['new'],True))
        tb.checked_update(value,[source],['obligation','condition'],{},['new'],True)
    if defect=='none':check()
    else:
        with pytest.raises((ValueError,jsonschema.ValidationError)):check()


def test_uncertainty_is_a_valid_explanation_and_wire_keeps_delta_identity():
    source,value=update_fixture();value.update(items=[],evidence_updates=[{'evidence_id':'new','disposition':'UNRESOLVED','fields':['obligation'],'reason':'적용 시점 확인 필요'}])
    data={'sources':[source],'fields':{'obligation':'의무','condition':'조건'},'locators':{}}
    schema=tb.review_contract(list(data['fields']),['new'],True)
    shown,wire_schema,expand,_=projection.prepare('ITEMS',data,schema)
    wire_value=deepcopy(value);wire_value['evidence_updates'][0].pop('fields')
    expanded=expand(wire_value);tb.checked_update(expanded,[source],list(data['fields']),{},['new'],True)
    assert expanded['items']==[] and expanded['evidence_updates'][0]=={**value['evidence_updates'][0],'fields':[]}
    assert source['spans'] and shown['sources'][0]['citation_options']


@pytest.mark.parametrize('failure',[False,True])
@pytest.mark.parametrize('round',[0,1])
def test_incremental_review_keeps_untouched_items_and_does_not_repeat(monkeypatch,failure,round):
    from workflow import presentation
    from semantic_runtime import comparison_research_bridge as bridge
    source,value=update_fixture();old_source={**deepcopy(source),'evidence_id':'old'}
    old=deepcopy(value['items'][0]);old['field']='condition';old['external']['citations'][0]['evidence']='old'
    value['items'][0].pop('internal')
    ctx=context();ctx.request={'use_llm':True};ctx.rag=S(port=S(services=type('Services',(),{'__module__':'semantic_runtime.test_services'})()))
    issue={'id':'i','requested_fields':['obligation','condition'],'requirements':[]}
    state={'scope':{'issues':[issue]},'task_board':{'round':round,'reviewed':[],'tasks':{},'reviewed_sources':{'i':['old']},
        'rows':{'i:obligation':{'issue_id':'i','field':'obligation','current':deepcopy(old),'revisions':[]},
                'i:condition':{'issue_id':'i','field':'condition','current':deepcopy(old),'revisions':[]}}}}
    untouched=deepcopy(state['task_board']['rows']['i:condition'])
    initial_rows=deepcopy(state['task_board']['rows'])
    data={'question':'원문 비교','as_of':None,'sources':[old_source,source],'budget':{},'deadline_at':'fixed','packet':{}}
    monkeypatch.setattr(tb,'sources_for_issue',lambda *args:[old_source,source])
    monkeypatch.setattr(presentation,'packets',lambda *args,**kw:[(deepcopy(data),[old_source,source])])
    monkeypatch.setattr(presentation,'valid_results',lambda _:[])
    monkeypatch.setattr(bridge,'investigation_leads',lambda *args:{})
    monkeypatch.setattr(bridge,'lead_view',lambda _: {})
    monkeypatch.setattr(bridge,'locators',lambda *args:{})
    calls=[]
    def decide(stage,shown,schema,instructions,check):
        assert shown['review_mode']=='UPDATE' and shown['sources'][0]['evidence_id']=='new'
        calls.append(stage)
        if failure:
            from workflow.contracts import WorkflowError
            raise WorkflowError('WORKFLOW_REPAIR_EXHAUSTED','합성 검증 실패')
        jsonschema.validate(value,schema);check(value);return deepcopy(value)
    from semantic_runtime.legal_agent.errors import BudgetExhausted,TransportError
    bad=deepcopy(value);bad['items'][0]['external']['citations'][0]['quote']='없는 원문'
    ctx.model=S(decide=decide,services=S(profile={'max_context_chars':80000},BudgetExhausted=BudgetExhausted,TransportError=TransportError),
        rejected_proposals=lambda *args:[{'call_id':'failed','proposal':bad}])
    ctx.repo.work=S(event=lambda *args:None)
    tb.review(ctx,state)
    assert state['task_board']['rows']['i:condition']==untouched
    if failure:
        assert state['task_board']['rows']==initial_rows
        assert state['task_board']['evidence_updates'][0]['disposition']=='UNRESOLVED'
        assert state['task_board']['rejected_proposals']
    else:
        assert len(state['task_board']['rows']['i:obligation']['revisions'])==1
        assert state['task_board']['rows']['i:obligation']['current']['internal']==old['internal']
        assert state['review_evidence_ids']==['new','old']
        assert state['task_board']['evidence_updates'][0]['disposition']=='USED'
    tb.review(ctx,state);assert calls==['ITEMS']


def test_incremental_wire_accepts_one_changed_side_without_fabricating_the_other():
    source,value=update_fixture();value['items'][0].pop('internal')
    data={'sources':[source],'fields':{'obligation':'의무'},'locators':{},'review_mode':'UPDATE'}
    schema=tb.review_contract(['obligation'],['new'],True)
    shown,wire_schema,expand,_=projection.prepare('ITEMS',data,schema)
    wire_value=deepcopy(value);wire_value['evidence_updates'][0].pop('fields');side=wire_value['items'][0]['external']
    side.pop('dependencies');side.pop('scope_sufficient');side['citations']=[{'citation_id':'C1'}]
    expanded=expand(wire_value);tb.checked_update(expanded,[source],['obligation'],{},['new'],True)
    assert 'internal' not in expanded['items'][0]


@pytest.mark.parametrize('defect',['policy','quote','issue','task'])
def test_trusted_child_requirement_validation_rejects_forgery(defect):
    from semantic_runtime.legal_agent.workflow_execution import validate_task
    from semantic_runtime.legal_agent.errors import ContractError
    task={'source_category':'external','search_hints':['기준'],'issues':[{'id':'i','question':'외규 기준','numeric':False}],'facts':[],
        'research_policy':qs.POLICY,'research_requirements':[{'issue_id':'i','task':'외규 기준','requirements':[{'request_quote':'기준','need':'기준 확인'}]}]}
    validate_task(task,'기준 비교',verify_requirements=True)
    if defect=='policy':task['research_policy']='unsupported'
    if defect=='quote':task['research_requirements'][0]['requirements'][0]['request_quote']='없는 질문'
    if defect=='issue':task['research_requirements'][0]['issue_id']='wrong'
    if defect=='task':task['research_requirements'][0]['task']='다른 요구'
    with pytest.raises(ContractError):validate_task(task,'기준 비교',verify_requirements=True)


P=Path(__file__).parents[1]/'adr_0844/test_sources.py'
spec=importlib.util.spec_from_file_location('sources_generalized',P);prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
tree=prior.tree


class General(prior.Sources):
    def send_once(self,*,body,ticket):
        view=json.loads(body['messages'][1]['content'])['view'];stage=view.get('source_stage',view['phase'])
        result=super().send_once(body=body,ticket=ticket)
        if stage=='workflow-intake':
            value=json.loads(result['body_json']['choices'][0]['message']['content'])
            for issue in value['issues']:
                issue.update(work_type='general',requested_fields=['subject','obligation'],requirements=[{'request_quote':view['question'],'need':'승인 기준과 조치 비교'}])
            return wire(value)
        if stage=='workflow-items':
            value=json.loads(result['body_json']['choices'][0]['message']['content']);value['evidence_updates']=[]
            if view.get('review_mode')=='UPDATE':
                for item in value['items']:
                    for side in ('internal','external'):
                        if not any(s['side']==side for s in view['sources']):item.pop(side,None)
            for item in value['items']:
                for task in item['next_tasks']:task.update(priority='CORE',priority_reason='질문에 직접 필요한 담당 확인')
            for ident in view.get('new_evidence_ids',[]):
                source=next(s for s in view['sources'] if s['evidence_id']==ident)
                item=value['items'][0];citation={'citation_id':source['citation_options'][0]['citation_id']}
                if citation not in item[source['side']]['citations']:item[source['side']]['citations'].append(citation)
                value['evidence_updates'].append({'evidence_id':ident,'disposition':'USED','reason':'새 원문 확인'})
            return wire(value)
        return result


@pytest.mark.parametrize('mode',['normal','followup','failed_followup'])
def test_generalized_api_sources_save_duplicate_and_failure_preserve_originals(tmp_path,tree,mode):
    app,_=prior.app_for(tmp_path,tree);t=General(mode);app.state.pipeline.term_agent.transport=t
    with TestClient(app) as client:
        response=client.post('/v1/rag/ask',json=prior.BODY);assert response.status_code==200,response.text
        value=response.json();assert value['answer']['text'] and value['comparison_items']['items'],value
        assert len(value['comparison_items']['items'])==2,value
        assert all(value['rag_results'][s]['evidence_ids'] for s in ('internal','external'))
        assert any(v.get('workflow_task',{}).get('research_requirements') for stage,v in t.views if stage.startswith('source-law-sources'))
        count=len(t.views);again=client.post('/v1/rag/ask',json=prior.BODY)
        assert again.status_code==200 and again.json()['answer']==value['answer'] and len(t.views)==count
        saved=client.get('/v1/workflows/runs/'+value['run_id'],params={'session_id':'s'})
        assert saved.json()['answer']==value['answer'] and len(t.views)==count
        if mode=='failed_followup':assert value['latest_rag_attempts']['internal']['status']=='failed'


def test_generalized_resume_preserves_deadline_and_completed_child(tmp_path,tree,monkeypatch):
    original=prior.app_for
    def app_for(*args,**kwargs):
        app,_=original(*args,**kwargs);t=General();app.state.pipeline.term_agent.transport=t;return app,t
    monkeypatch.setattr(prior,'app_for',app_for)
    prior.test_after_terminal_commit_resumes_without_model(tmp_path,tree,monkeypatch)


def test_history_is_read_only_and_canonical_state_is_unchanged():
    source,value=update_fixture();old=deepcopy(value['items'][0]);original=deepcopy(old)
    data={'sources':[source],'fields':{'obligation':'의무'},'locators':{},'review_mode':'UPDATE','previous':[old]}
    shown,schema,expand,_=projection.prepare('ITEMS',data,tb.review_contract(['obligation'],['new'],True))
    assert 'previous' not in shown and old==original
    entry=shown['read_only_history'][0]['readings']['external']
    assert entry['finding']==old['external']['text']
    assert entry['source_history'][0]['quoted_original']==source['spans'][0]['text']
    assert not {'scope_sufficient','dependencies','citations','next_tasks'} & set(entry)
    bad=deepcopy(value);bad['items'][0]['external']['citations']=[{'citation_id':'C1','evidence_id':'new'}]
    with pytest.raises(jsonschema.ValidationError):expand(bad)


@pytest.mark.parametrize('bad_update',[False,True])
def test_actual_api_late_initial_packet_updates_and_wire_failure_preserve_sources(tmp_path,tree,monkeypatch,bad_update):
    import importlib
    app,_=prior.app_for(tmp_path,tree)
    definition=app.state.workflow_runtime.registry.resolve('risk_team_compare_workflow',None,'risk_team')
    presentation=importlib.import_module(definition.entrypoint.__module__.rsplit('.',2)[0]+'.presentation')
    original=presentation.packets
    def packets(ctx,state,stage,**kwargs):
        values=original(ctx,state,stage,**kwargs)
        if stage!='ITEMS':return values
        result=[]
        for data,visible in values:
            for e in visible:
                d=deepcopy(data);d['sources']=[s for s in d['sources'] if s['evidence_id']==e['evidence_id']]
                d['packet']['dependency_closure_complete']=False
                result.append((d,[e]))
        return result
    monkeypatch.setattr(presentation,'packets',packets)
    class Transport(General):
        def send_once(self,*,body,ticket):
            result=super().send_once(body=body,ticket=ticket)
            view=json.loads(body['messages'][1]['content'])['view']
            if bad_update and view.get('review_mode')=='UPDATE':
                value=json.loads(result['body_json']['choices'][0]['message']['content'])
                item=value['items'][0];side=next(s for s in ('internal','external') if s in item)
                item[side]['scope_sufficient']=True
                return wire(value)
            return result
    t=Transport('normal');app.state.pipeline.term_agent.transport=t
    with TestClient(app) as client:
        response=client.post('/v1/rag/ask',json=prior.BODY);assert response.status_code==200,response.text
        body=response.json();views=[v for stage,v in t.views if stage=='workflow-items']
        assert views[0]['review_mode']=='INITIAL' and views[0]['new_evidence_ids']
        assert any(v['review_mode']=='UPDATE' and v['investigation_budget']['used']==0 for v in views)
        assert all('previous' not in v and 'read_only_history' in v for v in views)
        assert body['evidence_updates']
        if bad_update:
            assert body['status']=='partial' and body['update_failures']
            failed={r['evidence_id'] for r in body['evidence_updates'] if r.get('origin')=='SYSTEM_FAILURE'}
            assert failed and failed<=set(body['evidence_refs'])
            assert failed<={r['evidence_id'] for r in body['unreviewed_sources']}
        else:
            assert all(r['disposition']=='USED' for r in body['evidence_updates'])
            assert all(i[s]['citations'] for i in body['comparison_items']['items'] for s in ('internal','external'))
        count=len(t.views);again=client.post('/v1/rag/ask',json=prior.BODY)
        assert again.json()['answer']==body['answer'] and len(t.views)==count

