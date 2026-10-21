from copy import deepcopy
import json
import pytest,jsonschema
from workflow.adapters import projection
from workflow.risk_team_compare_workflow import task_board as tb
from test_lossless_wire import fixture
from test_generalized import record,update_fixture,General,prior,tree
from fastapi.testclient import TestClient
from test_legal_agent_double_harness import wire


def flat_value(value,side='external',aliases=False):
    item=deepcopy(value['items'][0]);body=item[side]
    if aliases:body['assessment']=body.pop('status');body['finding']=body.pop('text')
    return {'evidence_updates':deepcopy(value['evidence_updates']),
        'items':[{'field':item['field'],'side':side,**body}]}


@pytest.mark.parametrize('form',['flat','flat_alias','nested_alias'])
def test_closed_patch_forms_keep_judgments_and_actual_citations(form):
    source,value,schema,expand,receipt=fixture()
    if form.startswith('flat'):value=flat_value(value,aliases=form=='flat_alias')
    else:
        value['items'][0].pop('internal');value['items'][0].pop('next_tasks')
        row=value['items'][0]['external'];row['assessment']=row.pop('status');row['finding']=row.pop('text')
    before=deepcopy(value);out=expand(value)
    assert value==before
    tb.checked_update(out,[source],['obligation'],{},['new'],True)
    assert out['items'][0]['external']['status']=='CONFIRMED'
    assert out['items'][0]['external']['text']=='변경 시 책임자 재검토'
    assert out['items'][0]['external']['citations']==[{'evidence':'new','quote':source['spans'][0]['text']}]
    assert 'internal' not in out['items'][0]
    assert out['items'][0]['next_tasks']==[] and out['items'][0]['task_plan_unchanged']
    assert receipt['normalizations']


@pytest.mark.parametrize('defect',['both_aliases','unknown_key','duplicate_side','unknown_side','missing_status','foreign_citation','conflicting_metadata'])
def test_patch_ambiguity_and_invalid_sources_are_not_silently_fixed(defect):
    source,value,_,expand,_=fixture();v=flat_value(value);item=v['items'][0]
    if defect=='both_aliases':item['assessment']='MISSING';item['finding']='different'
    if defect=='unknown_key':item['unexpected']='extra'
    if defect=='duplicate_side':v['items'].append(deepcopy(item))
    if defect=='unknown_side':item['side']='invented'
    if defect=='missing_status':item.pop('status')
    if defect=='foreign_citation':item['citations']=['not-offered']
    if defect=='conflicting_metadata':
        item['difference']='first';other=deepcopy(item);other.update(side='internal',difference='second',citations=[]);v['items'].append(other)
    with pytest.raises((ValueError,jsonschema.ValidationError)):expand(v)


def test_flat_opposite_side_citation_still_fails_semantic_contract():
    source,value,_,expand,_=fixture();v=flat_value(value);v['items'][0]['side']='internal';out=expand(v)
    with pytest.raises(ValueError,match='opposite-side'):tb.checked_update(out,[source],['obligation'],{},['new'],True)


def test_flat_both_sides_assemble_one_canonical_field():
    source,value,_,expand,_=fixture();v=flat_value(value)
    v['items'].append({'field':'obligation','side':'internal',**deepcopy(value['items'][0]['internal'])})
    out=expand(v);assert len(out['items'])==1
    assert out['items'][0]['internal']['status']=='MISSING'
    tb.checked_update(out,[source],['obligation'],{},['new'],True)


def test_read_only_history_uses_the_same_judgment_names():
    source,value=update_fixture();shown,_,_,_=projection.prepare('ITEMS',{'sources':[source],
        'fields':{'obligation':'의무'},'review_mode':'UPDATE','previous':value['items']},tb.review_contract(['obligation'],['new'],True))
    r=shown['read_only_history'][0]['readings']['external']
    assert r['status']=='CONFIRMED' and r['text']==value['items'][0]['external']['text']
    assert not {'assessment','finding','remaining_question'}&set(r)


def setup_need():
    board={'tasks':{},'round':0};issue={'id':'i','external_task':'해당 대상의 외부 조치 기준 조사'}
    row={'missing':'적용 조건 원문 미확인','status':'PARTIAL','text':'현재까지 확인한 조치','citations':[{'evidence':'source','quote':'원문'}]}
    def compile(proposed):
        task={'issue_id':'i','requested_fields':['condition'],'target_side':proposed['side'],'operation':proposed['operation'],
            'target_locator':None,'missing_target':proposed['query'],'anchor_refs':[],'binding_hash':'fixed'}
        return tb.register_task(board,task,proposed,True)
    return board,issue,row,compile


def test_missing_without_next_task_creates_bound_search_and_survives_resume():
    board,issue,row,compile=setup_need();tb.reconcile_need(board,issue,'condition','external',row,'rev1',[],compile)
    need=next(iter(board['research_needs'].values()));task=board['tasks'][need['task_ids'][0]]
    assert need['missing']==row['missing'] and task['status']=='PENDING'
    assert row['missing'] in task['task']['missing_target']
    assert task['planning_receipt']['meaning_inferred'] is False
    restored=json.loads(json.dumps(board));assert tb.research_need_view(restored)[0]['execution_state']=='QUEUED'
    tb.reconcile_need(board,issue,'condition','external',row,'rev2',[],compile)
    assert len(board['tasks'])==1 and board['tasks'][need['task_ids'][0]]['status']=='PENDING'
    assert len(need['history'])==2


def test_failed_search_receipt_is_not_reopened_or_marked_resolved():
    board,issue,row,compile=setup_need();tb.reconcile_need(board,issue,'condition','external',row,'rev1',[],compile)
    task=next(iter(board['tasks'].values()));task.update(status='FAILED',result_request_id='old',acquisition_key='k')
    tb.reconcile_need(board,issue,'condition','external',row,'rev2',[],compile)
    assert len(board['tasks'])==1 and task['status']=='FAILED'
    assert tb.research_need_view(board)[0]['execution_state']=='ATTEMPT_RECORDED'
    board['round']=2;assert tb.research_need_view(board,limit=2)[0]['execution_state']=='BUDGET_EXHAUSTED'


def test_need_resolution_requires_explicit_clear_with_grounded_judgment():
    board,issue,row,compile=setup_need();tb.reconcile_need(board,issue,'condition','external',row,'rev1',[],compile)
    row.update(missing='',citations=[]);tb.reconcile_need(board,issue,'condition','external',row,'rev2',[],compile)
    assert next(iter(board['research_needs'].values()))['status']=='OPEN'
    row['citations']=[{'evidence':'new','quote':'새 원문'}];tb.reconcile_need(board,issue,'condition','external',row,'rev3',[],compile)
    assert next(iter(board['research_needs'].values()))['status']=='RESOLVED'
    assert next(iter(board['tasks'].values()))['status']=='RESOLVED'


def test_different_search_questions_have_different_ids_but_whitespace_does_not():
    board,issue,row,compile=setup_need()
    p={'side':'external','operation':'search_text','query':'첫 원문','priority':'DEPENDENCY','priority_reason':'필요'}
    a=compile(p);p['query']='두번째 원문';b=compile(p);p['query']='두번째  원문';c=compile(p)
    assert a!=b==c


def test_broad_search_fairness_uses_persisted_attempts_without_overriding_exact_or_resume():
    rows=[record('internal','CORE',0),record('external','DEPENDENCY',1),record('exact','DEPENDENCY',2,True)]
    for r in rows:r['task']['target_side']='internal' if r['task']['task_id']=='internal' else 'external'
    board={'tasks':{r['task']['task_id']:r for r in rows}}
    board['tasks']['old']={'status':'COMPLETE','acquisition_key':'used','task':{'target_side':'internal'}}
    assert [r['task']['task_id'] for r in tb.pending_tasks(board,True)]==['exact','external','internal']
    rows[0]['status']='RUNNING';assert tb.pending_tasks(board,True)[0]['task']['task_id']=='internal'


def test_actual_api_preserves_missing_need_and_accepts_flat_side_updates(tmp_path,tree):
    class Patches(General):
        def send_once(self,*,body,ticket):
            result=super().send_once(body=body,ticket=ticket)
            view=json.loads(body['messages'][1]['content'])['view']
            if view.get('source_stage')=='workflow-items':
                value=json.loads(result['body_json']['choices'][0]['message']['content'])
                if view['review_mode']=='INITIAL':
                    value['items'][0]['external']['missing']='해당 대상에 적용되는 추가 조건 원문'
                    value['items'][0]['next_tasks']=[]
                else:
                    value['items']=[{'field':row['field'],'side':side,**row[side]} for row in value['items'] for side in ('internal','external') if side in row]
                return wire(value)
            return result
    app,_=prior.app_for(tmp_path,tree);t=Patches();app.state.pipeline.term_agent.transport=t
    with TestClient(app) as client:
        response=client.post('/v1/rag/ask',json=prior.BODY);assert response.status_code==200,response.text
        body=response.json();assert body['research_needs'] and not body['update_failures']
        assert all(n['task_ids'] and n['execution_state']!='NO_TASK' for n in body['research_needs'])
        count=len(t.views);again=client.post('/v1/rag/ask',json=prior.BODY)
        assert again.json()['answer']==body['answer'] and len(t.views)==count
        saved=client.get('/v1/workflows/runs/'+body['run_id'],params={'session_id':'s'})
        assert saved.json()['answer']==body['answer'] and len(t.views)==count
