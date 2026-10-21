from copy import deepcopy
from types import SimpleNamespace as S
import pytest,jsonschema
from workflow.adapters import projection
from workflow.risk_team_compare_workflow import task_board as tb
from test_generalized import update_fixture,context


def test_side_only_patch_has_no_invented_comparison_or_task_deletion():
    source,value=update_fixture();value['evidence_updates'][0].pop('fields')
    item=value['items'][0]
    for key in ('internal','content_status','difference','next_tasks'):item.pop(key)
    item['external'].pop('dependencies');item['external'].pop('scope_sufficient');item['external']['citations']=['C1']
    data={'sources':[source],'fields':{'obligation':'의무'},'locators':{},'review_mode':'UPDATE'}
    schema=tb.review_contract(['obligation'],['new'],True)
    _,_,expand,receipt=projection.prepare('ITEMS',data,schema);out=expand(value)
    jsonschema.validate(out,schema);tb.checked_update(out,[source],['obligation'],{},['new'],True)
    actual=out['items'][0]
    assert 'internal' not in actual and actual['content_status']=='UNKNOWN' and actual['difference']==''
    assert actual['next_tasks']==[] and actual['task_plan_unchanged'] is True
    assert any(r['rule']=='partial-review-patch-v1' for r in receipt['normalizations'])
    value['items'][0]['task_plan_unchanged']=True
    with pytest.raises(jsonschema.ValidationError):expand(value)


@pytest.mark.parametrize('keep',[True,False])
def test_omitted_or_empty_plan_alone_preserves_existing_queue(monkeypatch,keep):
    from workflow import presentation
    from semantic_runtime import comparison_research_bridge as bridge
    source,value=update_fixture();old_source={**deepcopy(source),'evidence_id':'old'}
    old=deepcopy(value['items'][0]);old['external']['citations'][0]['evidence']='old'
    old['next_tasks']=[{'previous_plan':'already validated in earlier packet'}]
    value['items'][0].pop('internal')
    if keep:value['items'][0]['task_plan_unchanged']=True
    ctx=context();ctx.request={'use_llm':True};ctx.rag=S(port=S(services=type('Services',(),{'__module__':'semantic_runtime.test_services'})()))
    pending={'status':'PENDING','priority':'DEPENDENCY','priority_reason':'기존 원문 확인','task':{'task_id':'prior','issue_id':'i',
        'requested_fields':['obligation'],'target_side':'external','missing_target':'기존에 선택한 조건 원문','target_locator':None}}
    state={'scope':{'issues':[{'id':'i','requested_fields':['obligation'],'requirements':[]}]},
        'task_board':{'round':0,'reviewed':[],'tasks':{'prior':deepcopy(pending)},'reviewed_sources':{'i':['old']},
            'rows':{'i:obligation':{'issue_id':'i','field':'obligation','current':deepcopy(old),'revisions':[]}}}}
    data={'question':'원문 비교','as_of':None,'sources':[old_source,source],'budget':{},'deadline_at':'fixed','packet':{}}
    monkeypatch.setattr(tb,'sources_for_issue',lambda *args:[old_source,source])
    monkeypatch.setattr(presentation,'packets',lambda *args,**kw:[(deepcopy(data),[old_source,source])])
    monkeypatch.setattr(presentation,'valid_results',lambda _:[])
    monkeypatch.setattr(bridge,'investigation_leads',lambda *args:{})
    monkeypatch.setattr(bridge,'lead_view',lambda _: {})
    monkeypatch.setattr(bridge,'locators',lambda *args:{})
    def decide(stage,shown,schema,instructions,check):
        jsonschema.validate(value,schema);check(value);return deepcopy(value)
    ctx.model=S(decide=decide,services=S(profile={'max_context_chars':80000}))
    tb.review(ctx,state)
    current=state['task_board']['rows']['i:obligation']['current']
    assert current['internal']==old['internal']
    if keep:
        assert state['task_board']['tasks']['prior']==pending and current['next_tasks']==old['next_tasks']
    else:
        assert state['task_board']['tasks']['prior']['status']=='PENDING' and current['next_tasks']==[]
