"""Public route, durable replay, current acquisition, and typed scenario checks."""
from copy import deepcopy
import json
import pytest
from fastapi.testclient import TestClient
from conftest import term_glossary
from test_main50_request_repair import tree
from test_assessment_source_reply import EmptyAssessment, settings, ROOT
from semantic_runtime.app import create_app
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import review_explanation as review
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from semantic_runtime.legal_agent import ontology_assessment as ontology
from semantic_runtime.legal_agent.scenario_branch import compare
from semantic_runtime.ontology_work.evaluation_plan import compile_plan, run
from test_domain_profile_workflow import env, add_observation, proposal, save, approve_stage


def test_acquisition_and_review_are_independent_and_history_not_rewritten():
    value = {'read_judgment_review': {'status':'INCOMPLETE', 'review':None,
        'prior_needs':[{'id':'N1','text':'제1조 원문을 확보해야 한다','issue_refs':['I1'],'target_refs':['T1']},
                       {'id':'N2','text':'없음. 모두 확보하였다','issue_refs':['I1']}],
        'need_continuity':{'targets':[{'id':'T1','document_id':'d','coordinate':'제1조', 'acquired':True,'available_complete':True}]}}}
    original=deepcopy(value);items=review.need_items(value)
    assert value==original
    assert items[0]['acquisition']=='ACQUIRED' and items[0]['review']=='INCOMPLETE'
    assert items[0]['next_action']=='REVIEW_AGAIN'
    assert '확보해야' not in items[0]['reason'] and '없음' not in items[1]['reason']
    value['read_judgment_review']['review']={'needs':[{'id':'N1','status':'RESOLVED','claim_refs':['C1']}]}
    assert review.need_items(value)[0]['next_action'] is None
    value['read_judgment_review']['need_continuity']['targets'][0]['available_complete']=False
    assert review.need_items(value)[0]['acquisition']=='PARTIAL'


def test_native_review_view_is_model_free_and_replay_bound(tmp_path, tree):
    gen,idx=tree; transport=EmptyAssessment('repaired')
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,
            'completion_contract':True,'completion_policy_version':'investigation-completion-v8',
            'compact_input':True,'assessment_reentry_limit':0}}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile=profile,legal_agent_transport=transport,runtime_root=tmp_path/'runtime',
        memory_identity=lambda _:{'user_id':'synthetic','team_id':'risk_team','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'review','request_id':'initial'}
    with TestClient(app) as api:
        response=api.post('/v1/rag/ask',json=body)
        assert response.status_code==200,response.text
        out=response.json();view=out['assembly']['term_agent']['review_explanation']
        review.verify(view); calls=list(transport.phases)
        action=next(a for a in view['actions'] if a['kind']=='VIEW_REVIEW')
        request={**body,'question':action['label'],'request_id':'view','use_llm':False,
            'review_action':{'schema_version':'review-action-v1','action_id':action['id'],'view_hash':view['content_sha256'],
                'case_id':view['case']['question_id'],'revision':view['case']['revision'],'operation_id':'view','input':{}}}
        shown=api.post('/v1/rag/ask',json=request)
        assert shown.status_code==200,shown.text
        assert transport.phases==calls
        assert shown.json()['assembly']['term_agent']['review_explanation']==view
        duplicate=api.post('/v1/rag/ask',json=request)
        assert duplicate.status_code==200,duplicate.text
        assert duplicate.json()['answer']==shown.json()['answer'] and transport.phases==calls
        changed=deepcopy(request);changed['question']='다른 행동'
        assert api.post('/v1/rag/ask',json=changed).status_code==409
        stale=deepcopy(request);stale['request_id']='stale';stale['review_action'].update(operation_id='stale',revision=999)
        assert api.post('/v1/rag/ask',json=stale).status_code==409
        assert transport.phases==calls


def spec():
    money=lambda x:{'type':'money','unit':'KRW','value':x}
    return {'fields':{
        'cost':{'kind':'FACT','type':'money','unit':'KRW','concept':'비용','period':'건별','as_of':'2026-11-02','baseline':None},
        'limit':{'kind':'RULE','type':'money','unit':'KRW','concept':'한도','period':'건별','as_of':'2026-11-02','baseline':money('1000000')}},
        'rules':[{'node_id':'N1','expression':{'op':'lte','args':[{'field':'cost'},{'field':'limit'}]},'source_ids':['S1'],'rounding':'EXACT_ONLY'}]}


def test_evaluation_spec_requires_new_approval_and_preserves_baseline(env):
    from semantic_runtime.ontology_work import assembly_compiler as compiler
    obs=add_observation(env);draft=save(env,obs,proposal(env,obs))
    approved=approve_stage(env,draft)
    before=env.w.preview(draft['bundle_id']);old_hash=before['package_sha256']
    edit=env.w.save_evaluation_spec(draft['bundle_id'],draft['revision'],draft['work_hash'],spec())
    assert edit['status']=='DRAFT'
    with pytest.raises(ContractError):env.w.stage_publication(edit['bundle_id'],edit['revision'],edit['work_hash'],0)
    approve_stage(env,edit);package=env.w.preview(edit['bundle_id'])
    compiler.verify_package(package,approved=True,recompile=True)
    assert package['evaluation_plan']['approval_ref'] and before['package_sha256']==old_hash
    catalog=compiler.bind_current(package,[{'anchor':env.source['anchor'],'text':env.source['text'],'evidence_refs':['S-current']}])
    state={'facts':[{'name':'cost','value':'1500000','typed_value':{'type':'money','unit':'KRW','value':'1500000'}}]}
    explanation=review.seal({'schema_version':review.VERSION,'ontology':{'bundles':[{'assembly':catalog}]},
        'items':[{'id':'approval','review':'OPEN','reason':'별도 승인 요건 미확인','next_action':'RESEARCH'}], 'outcome':'INSUFFICIENT'})
    base=deepcopy((explanation,state,package))
    result=compare(explanation,state,{'limit':{'type':'money','unit':'KRW','value':'2000000'}},kind='RULE',operation_id='op1')
    assert result['comparisons'][0]['before']['status']=='FALSE'
    assert result['comparisons'][0]['after']['status']=='TRUE'
    assert result['legal_conclusion']=='UNCONFIRMED' and result['unresolved']
    assert (explanation,state,package)==base and result['model_calls']==0
    assert compare(explanation,state,result['changes'],kind='RULE',operation_id='op1')==result
    with pytest.raises(ContractError):compare(explanation,state,result['changes'],kind='FACT',operation_id='bad')
    missing=compiler.bind_current(package,[])
    assert 'evaluation_plan' not in missing and missing['withheld']


@pytest.mark.parametrize('fault',['wrong_node','wrong_claim','wrong_evidence','duplicate'])
def test_ontology_adoption_requires_explicit_exact_binding(fault):
    payload={'ontology_bundles':[{'payload':{'assembly_catalog':{'package_sha256':'p','paths':[
        {'id':'path','nodes':[{'id':'n'}],'source_refs':['S1']}]}}}]}
    row={'package_sha256':'p','path_id':'path','node_ids':['n'],'claim_id':'C1'}
    value={'claims':[{'claim_id':'C1','evidence_refs':['S1']}],'ontology_usage':[row]}
    if fault=='wrong_node':row['node_ids']=['other']
    if fault=='wrong_claim':row['claim_id']='C2'
    if fault=='wrong_evidence':value['claims'][0]['evidence_refs']=['S2']
    if fault=='duplicate':value['ontology_usage'].append(deepcopy(row))
    with pytest.raises(ProposalError):ontology.usage_core(value,{'properties':{}},payload)

@pytest.fixture(autouse=True)
def current_normalizer_wire(monkeypatch):
    import test_domain_profile_workflow as fixture
    old=fixture.normalized_output
    def normalized(context):
        value=old(context)
        for row in value['observations']:
            for key in ('reason','purpose'):
                assert row.pop(key)['state']=='NOT_RECORDED'
                row['recorded_'+key]=None
        value['coverage']={r['pointer']:{k:v for k,v in r.items() if k!='pointer'} for r in value['coverage']}
        def walk(v):
            if isinstance(v,dict):
                if set(v)=={'payload_hash','pointer','start','end','quote'}:
                    return {'pointer':v['pointer'],'quote':v['quote'],'occurrence':0}
                return {k:walk(x) for k,x in v.items()}
            if isinstance(v,list):return [walk(x) for x in v]
            return v
        return walk(value)
    monkeypatch.setattr(fixture,'normalized_output',normalized)


@pytest.mark.parametrize('scenario_fault',['missing_receipt','wrong_condition','stale_value','repair_success','rule_stale','rule_success'])
def test_native_typed_scenario_and_explicit_ontology_use(env,tmp_path,term_glossary,monkeypatch,scenario_fault):
    import sqlite3
    from semantic_runtime import app as app_module
    from semantic_runtime.ontology_work import runtime
    from semantic_runtime.legal_agent.ontology_compiler import content_hash
    monkeypatch.syspath_prepend(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1188'))
    monkeypatch.setenv('WORKFLOW_TEST_CODE_ROOT',str(ROOT))
    monkeypatch.setenv('GENOS_AUTO_WARMUP','0');monkeypatch.setenv('AD_WORKER_ENABLED','0')
    real_create=app_module.create_app
    def create(*args,**kwargs):
        with sqlite3.connect(tmp_path/'raw.sqlite') as db:
            version=db.execute("SELECT source_artifact_sha256 FROM document WHERE document_id='d'").fetchone()[0]
            text=db.execute("SELECT text FROM source_block WHERE document_id='d' AND unit_id='1'").fetchone()[0]
        env.source.update(id='S1',anchor={'document_id':'d','version':version,'unit_id':'1',
            'content_sha256':content_hash(text),'label':'합성 규정 제2조'},text=text)
        env.w.document_ids=frozenset(['d']);env.w.source_reader=lambda a:text if a==env.source['anchor'] else None
        observation=add_observation(env);draft=save(env,observation,proposal(env,observation))
        draft=env.w.save_evaluation_spec(draft['bundle_id'],draft['revision'],draft['work_hash'],spec())
        stage=approve_stage(env,draft);receipt=env.w.verify_publication(stage['publication_id'])
        env.w.activate_publication(stage['publication_id'],0,receipt)
        kwargs['legal_agent_profile']['candidate_navigation'].update(ontology_enabled=True,ontology_direct_assessment=True,ontology_context={'mode':'DB'})
        transport=kwargs['legal_agent_transport'];send=transport.send_once
        def wrapped(*,body,ticket):
            from api_fixture_integrated import decode
            view=decode(json.loads(body['messages'][1]['content'])['view'])
            if view.get('hypothetical_scenario'):
                from test_agent_loop_fault_recovery import unresolved_assessment
                from test_legal_agent_double_harness import wire
                transport.calls.append(view['source_stage']);transport.views.append(deepcopy(view))
                view=deepcopy(view)
                for n in view['read_judgments']['needs']:n['target_refs']=n.get('target_refs') or []
                if scenario_fault in ('repair_success','rule_success'):
                    response=send(body=body,ticket=ticket)
                    # send records its own call, unlike the failure fixtures.
                    transport.calls.pop();transport.views.pop()
                    value=json.loads(response['body_json']['choices'][0]['message']['content'])
                else:value=unresolved_assessment(view)
                from semantic_runtime.legal_agent.scenario_review import results
                if scenario_fault != 'missing_receipt':
                    value['scenario_review']={'condition_results':results(view['hypothetical_scenario']),'outcome':'UNCONFIRMED'}
                    if scenario_fault=='wrong_condition' or scenario_fault=='repair_success' and not view['source_stage'].endswith('-repair'):value['scenario_review']['condition_results'][0]['status']='FALSE'
                    if scenario_fault=='stale_value':value['claims']=[{'claim_id':'C1','issue_refs':[view['issues'][0]['id']], 'evidence_refs':[view['evidence_options'][0]['id']], 'rule':None,'content_contract':'source-modality-v4','explanation':'현재 비용은 1500000원이다.'}]
                if scenario_fault in ('rule_stale','rule_success'):
                    if scenario_fault=='rule_stale':
                        value['claims']=[{'claim_id':'C1','issue_refs':[view['issues'][0]['id']], 'evidence_refs':[view['evidence_options'][0]['id']], 'rule':None,'content_contract':'source-modality-v4','explanation':'현재1000000원 한도에서 비용1500000원은 불충족이다.'}]
                    else:
                        value['claims'][0]['rule']=None
                        value['claims'][0]['explanation']='가정한도2450000원에서 비용1500000원은 금액조건 충족, 승인은 미확인이다.'
                    value['scenario_review']['application_links']=[{'claim_id':value['claims'][0]['claim_id'],'condition_ids':['scenario-condition:1']}]
                return wire(value)
            response=send(body=body,ticket=ticket)
            if view.get('source_stage')=='request-entry':
                value=json.loads(response['body_json']['choices'][0]['message']['content'])
                value['intent']['issues'][0]['request_quote']='원문검토검증규정의 적용 기준은? 작업 비용은 1500000원, 서면 승인은 미확인입니다.'
                value['command']['facts']=[{'name':'작업 비용','value':'1500000원','user_quote':'작업 비용은 1500000원'},{'name':'서면 승인','value':'미확인','user_quote':'서면 승인은 미확인'}]
                response['body_json']['choices'][0]['message']['content']=json.dumps(value,ensure_ascii=False)
            if view.get('source_stage','').startswith('memory-assess'):
                catalogs=[c['payload']['assembly_catalog'] for c in view.get('ontology_bundles',[]) if c.get('payload',{}).get('assembly_catalog')]
                if catalogs:
                    raw=response['body_json']['choices'][0]['message']['content'];value=json.loads(raw)
                    path=catalogs[0]['paths'][0];claim=value['claims'][0]
                    claim['evidence_refs']=list(dict.fromkeys(claim['evidence_refs']+path['source_refs']))
                    value['ontology_usage']=[{'package_sha256':catalogs[0]['package_sha256'],'path_id':path['id'],
                        'node_ids':[path['nodes'][0]['id']],'claim_id':claim['claim_id']}]
                    response['body_json']['choices'][0]['message']['content']=json.dumps(value,ensure_ascii=False)
            return response
        transport.send_once=wrapped
        return real_create(*args,**kwargs)
    monkeypatch.setattr(app_module,'create_app',create);monkeypatch.setattr(runtime,'repository',lambda:env.repo)
    import need_continuity_fixture as fixture
    old=fixture.change_review
    def changes(head):
        head=deepcopy(head)
        if not head.get('change_from'):head['change_from']={'version':0,'finding':''}
        head['review_purposes']=head.get('review_purposes') or []
        return old(head)
    monkeypatch.setattr(fixture,'change_review',changes)
    def exercise(api,transport,request,runtime_path):
        request={**request,'question':request['question']+' 작업 비용은 1500000원, 서면 승인은 미확인입니다.'}
        response=api.post('/v1/rag/ask',json=request)
        assert response.status_code==200,response.text
        out=response.json();view=out['assembly']['term_agent']['review_explanation'];calls=list(transport.calls)
        assert view['ontology']['status']=='RESPONSE_RECEIVED'
        assert view['ontology']['adoption']=='RECORDED'
        assert view['ontology']['bundles'][0]['claim_uses']
        action=next(a for a in view['actions'] if a['kind']=='WHAT_IF')
        body={**request,'question':action['label'],'request_id':'scenario-1','use_llm':False,
            'review_action':{'schema_version':'review-action-v1','action_id':action['id'],'view_hash':view['content_sha256'],
                'case_id':view['case']['question_id'],'revision':view['case']['revision'],'operation_id':'scenario-1',
                'input':{'kind':'FACT','changes':{'cost':{'type':'money','unit':'KRW','value':'500000'}},
                    'bindings':{'cost':[r['id'] for r in action['fact_options'] if r['name']=='작업 비용']}}}}
        response=api.post('/v1/rag/ask',json=body)
        assert response.status_code==200,response.text
        result=response.json();scenario=result['assembly']['term_agent']['scenario_comparison']
        assert scenario['comparisons'][0]['before']['status']=='FALSE'
        assert scenario['comparisons'][0]['after']['status']=='TRUE'
        assert scenario['legal_conclusion']=='UNCONFIRMED'
        assert result['revision']==out['revision'] and transport.calls==calls
        duplicate=api.post('/v1/rag/ask',json=body)
        assert duplicate.status_code==200,duplicate.text
        assert duplicate.json()['assembly']['term_agent']['scenario_comparison']==scenario
        assert transport.calls==calls
        from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
        from semantic_runtime.legal_agent.unified_publication import validate_saved
        journal=next(runtime_path.glob('legal-agent/runs/*/'+result['run_id']+'/journal.sqlite'))
        repo=UnifiedRepository(journal)
        try:
            forged=deepcopy(result);forged['assembly']['term_agent']['scenario_comparison']['legal_conclusion']='CONFIRMED'
            with pytest.raises(ContractError):validate_saved(repo,forged)
        finally:repo.close()
        action=next(a for a in view['actions'] if a['kind']=='SCENARIO_REVIEW')
        semantic=deepcopy(body);semantic.update(question=action['label'],request_id='scenario-review',use_llm=True)
        semantic['review_action'].update(action_id=action['id'],operation_id='scenario-review')
        unbound=deepcopy(semantic);unbound['request_id']='unbound';unbound['review_action']['operation_id']='unbound'
        unbound['review_action']['input'].pop('bindings')
        blocked=api.post('/v1/rag/ask',json=unbound)
        assert blocked.status_code in (409,422),blocked.text
        assert transport.calls==calls
        if scenario_fault in ('rule_stale','rule_success'):
            semantic['review_action']['input'].update(kind='RULE',changes={'limit':{'type':'money','unit':'KRW','value':'2450000'}})
        checked=api.post('/v1/rag/ask',json=semantic)
        assert checked.status_code==200,checked.text
        branch=checked.json()
        assert branch['goal_id'] != out['goal_id']
        assert branch['assembly']['term_agent']['scenario_context']['baseline']['question_id']==out['goal_id']
        added=transport.calls[len(calls):]
        assert len(added)==(1 if scenario_fault=='rule_success' else 2) and all(p.startswith('memory-assess') for p in added), added
        assert bool(branch['answer']['claims']) == (scenario_fault in ('repair_success','rule_success'))
        failed=branch['assembly']['term_agent']['review_explanation']
        codes={'missing_receipt':'SCHEMA_REQUIRED','wrong_condition':'SCENARIO_CONDITION_CONFLICT','stale_value':'SCENARIO_SUPERSEDED_FACT','rule_stale':'SCENARIO_SUPERSEDED_RULE'}
        if scenario_fault in ('repair_success','rule_success'):assert failed['scenario_review']['outcome']=='UNCONFIRMED'
        else:assert codes[scenario_fault] in [r['code'] for r in failed['failed_checks']],failed
        for model_view in transport.views[-len(added):]:
            if scenario_fault in ('rule_stale','rule_success'):
                assert any('1500000' in str(f['value']) for f in model_view['current_facts'])
                continue
            assert '1500000' not in str(model_view['current_facts'])
            assert all('1500000' not in f['text'] for f in model_view['user_fact_sources'])
        repeat=api.post('/v1/rag/ask',json=semantic)
        assert repeat.status_code==200 and repeat.json()['answer']==branch['answer']
        assert len(transport.calls)==len(calls)+len(added)
        original=api.post('/v1/rag/ask',json=request)
        assert original.status_code==200 and original.json()['answer']==out['answer']
    fixture.run_api(tmp_path,term_glossary,'goal_control',monkeypatch,exercise=exercise)


def test_explicit_review_is_bounded_and_reuses_acquired_originals(tmp_path,term_glossary,monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1188'))
    monkeypatch.setenv('WORKFLOW_TEST_CODE_ROOT',str(ROOT))
    from need_continuity_fixture import run_api
    def exercise(api,transport,request,runtime):
        from api_fixture_integrated import decode
        send=transport.send_once
        def reject(*,body,ticket):
            view=decode(json.loads(body['messages'][1]['content'])['view'])
            if view.get('source_stage','').startswith('memory-assess'):
                from test_agent_loop_fault_recovery import unresolved_assessment
                from test_legal_agent_double_harness import wire
                transport.calls.append(view['source_stage']);transport.views.append(deepcopy(view))
                value=unresolved_assessment(view)
                value['read_judgment_review']['needs']=[]
                return wire(value)
            return send(body=body,ticket=ticket)
        transport.send_once=reject
        initial=api.post('/v1/rag/ask',json=request)
        assert initial.status_code==200,initial.text
        out=initial.json();view=out['assembly']['term_agent']['review_explanation']
        acquired=[i for i in view['items'] if i['targets'] and i['acquisition']=='ACQUIRED']
        assert acquired and all(i['next_action']=='REVIEW_AGAIN' for i in acquired)
        action=next(a for a in view['actions'] if a.get('item_id')=='final-review')
        follow={**request,'question':action['label'],'request_id':'retry-review',
            'review_action':{'schema_version':'review-action-v1','action_id':action['id'],'view_hash':view['content_sha256'],
                'case_id':view['case']['question_id'],'revision':view['case']['revision'],'operation_id':'retry-review','input':{}}}
        calls=len(transport.calls)
        response=api.post('/v1/rag/ask',json=follow)
        assert response.status_code==200,response.text
        assert all(p.startswith('memory-assess') for p in transport.calls[calls:])
        assert not response.json()['answer']['claims']
        after=len(transport.calls)
        assert api.post('/v1/rag/ask',json=follow).status_code==200
        assert len(transport.calls)==after
        view=response.json()['assembly']['term_agent']['review_explanation']
        assert any(a['kind']=='REVIEW_AGAIN' for a in view['actions']),json.dumps(view,ensure_ascii=False)
        action=next(a for a in view['actions'] if a['kind']=='REVIEW_AGAIN')
        repeat=deepcopy(follow);repeat['request_id']='retry-again'
        repeat['review_action'].update(action_id=action['id'],view_hash=view['content_sha256'],revision=view['case']['revision'],operation_id='retry-again')
        assert api.post('/v1/rag/ask',json=repeat).status_code==409
        assert len(transport.calls)==after
    run_api(tmp_path,term_glossary,'goal_control',monkeypatch,exercise=exercise)


@pytest.mark.parametrize('op,left,right,expected',[
    ('divide','1','0','DIVISION_BY_ZERO'),('divide','1','3','ROUNDING_POLICY_REQUIRED')])
def test_registered_evaluator_keeps_unknown_causes(op,left,right,expected):
    from lawrag.legal_knowledge.ontology import evaluate
    lit=lambda value:{'literal':{'type':'decimal','unit':'','value':value}}
    result=evaluate({'op':op,'args':[lit(left),lit(right)]},{},binding='test')
    assert result['status']=='UNKNOWN' and expected in result['missing']


def test_short_circuit_keeps_missing_and_unsupported_expression_is_rejected():
    from lawrag.legal_knowledge.ontology import evaluate
    from lawrag.legal_knowledge.contracts import KnowledgeError
    expression={'op':'all','args':[{'literal':{'type':'boolean','unit':'','value':False}},{'field':'approval'}]}
    result=evaluate(expression,{},binding='test')
    assert result['status']=='FALSE' and result['missing']==['approval']
    with pytest.raises(KnowledgeError):evaluate({'op':'exec','args':[]},{},binding='test')


def test_archived_real_1277_acquired_need_is_not_a_new_source_request():
    path=ROOT/'04_EXPERIMENTS/ADR/ADR-1277-qwen-followup-derived-context/artifacts/live/review-followup/experiment-client/call-006-memory-assess/request.json'
    def unpack(value):
        if isinstance(value,dict):
            if set(value)=={'table_columns','table_rows'}:
                return [dict(zip(value['table_columns'],map(unpack,row))) for row in value['table_rows']]
            return {k:unpack(v) for k,v in value.items()}
        if isinstance(value,list):return list(map(unpack,value))
        return value
    wire=json.loads(json.loads(path.read_text())['messages'][1]['content'])['view']
    ctx=unpack(wire['read_judgments']);before=deepcopy(ctx)
    rows=review.need_items({'read_judgment_review':{'status':'INCOMPLETE','review':None,
        'prior_needs':ctx['needs'],'need_continuity':ctx['need_continuity']}})
    original=next(n for n in ctx['needs'] if '원문을 확보하여' in n['text'])
    current=next(i for i in rows if i['id']==original['id'])
    assert current['acquisition']=='ACQUIRED' and current['next_action']=='REVIEW_AGAIN'
    assert current['review']=='INCOMPLETE' and '원문을 확보하여' not in current['reason']
    assert all('없음.' not in i['reason'] for i in rows)
    assert ctx==before


def test_exact_gap_range_uses_current_acquisition_and_preserves_declaration():
    sources=[{'source_id':'S1','document_id':'d','text':'원문', 'adopted_spans':[
        {'block_id':'1','start_cp':0,'end_cp':2,'text':'원문','evidence_id':'E1'}]}]
    gap={'kind':'MISSING_SOURCE','issue_id':'I1','material_id':None,'missing_target':'제1조',
        'reason':'원문 확보 필요','target_binding':{'status':'EXACT','expected':[
            {'document_id':'d','block_id':'1','start_cp':0,'end_cp':2}]}}
    before=deepcopy(gap)
    ident='L'+digest(['I1','MISSING_SOURCE',None,'제1조'])[:20]
    assessment={'gaps':[gap],'limitation_items':[{'id':ident,'text':'원문 확보 필요'}]}
    review.current_gap_limitations(assessment,sources)
    assert gap==before and review.gap_acquired(gap,sources)
    assert '원문 확보 완료' in assessment['limitations'][0]
    gap['target_binding']['expected'][0]['end_cp']=3
    assert not review.gap_acquired(gap,sources)


def test_genos_review_contract_render_and_action_passthrough():
    from test_genos_chat_flow import workflow
    w=workflow()
    view=review.bind_case(review.build({'read_judgment_review':{'status':'INCOMPLETE'},
        'model_proposal':{'review_status':'INCOMPLETE'},'issue_assessments':[],'gaps':[]},[]),
        {'question_id':'G1','revision':1,'route_id':1})
    body={'assembly':{'term_agent':{'review_explanation':view}}}
    assert w._review_explanation_text(body)==''
    text=w._review_explanation_text(body,diagnostics=True)
    assert '읽은 조문과 답 문장이 맞는지 마지막 확인' in text and '검토 다시 하기' in text
    altered=deepcopy(view);altered['items'][0]['reason']='<script>attack()</script>'
    assert w._review_explanation_text({'assembly':{'term_agent':{'review_explanation':altered}}})==''
    altered.pop('content_sha256');altered=review.seal(altered)
    assert '<script>' not in w._review_explanation_text({'assembly':{'term_agent':{'review_explanation':altered}}},diagnostics=True)
    action={'schema_version':'review-action-v1','operation_id':'op'}
    request=w._request_body('검토 상태 보기',{'session_id':'review','team_id':'risk_team','review_action':action,'use_llm':False})
    assert request['review_action']==action and request['use_llm'] is False
