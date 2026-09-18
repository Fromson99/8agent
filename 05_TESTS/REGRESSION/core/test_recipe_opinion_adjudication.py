"""Synthetic role separation, traceability and no blind application contracts."""
import copy
import pytest
from .test_recipe_regions import make
from lawrag.core.structure import recipe_regions as r


def context():
    _,recipe=make()
    return {'recipe':recipe,'source_blocks':[{'idx':6,'text':'1. 새 양식'}], 'page_window':[2]}


def test_vlm_only_opines_llm_proposes_executable_revision():
    data=context();calls=[];saved={}
    tid='outer_number';family=next(iter(data['recipe']['templates'][tid]['heading_rules']))
    rule=copy.deepcopy(data['recipe']['templates'][tid]['heading_rules'][family]);rule['sequence']='increasing'
    def call(phase,system,request,schema,vision):
        calls.append((phase,request));assert vision
        if 'opinions' in schema['properties']:
            assert 'verdict' not in schema['properties'] and 'template_changes' not in schema['properties']
            return {'opinions':['Page 2: numbering may restart at the new format. Verify scope.'],'summary':'One possible scope defect.'}
        assert request['vlm_opinions'][0]['id']=='opinion-1'
        return {'verdict':'revise','reviewed_state_id':request['reviewed_state_id'],'issues':[],
                'opinion_decisions':[{'opinion_id':'opinion-1','decision':'accept','reason':'Visible source supports scope correction','blocks':[6]}],
                'template_changes':[{'template_id':tid,'family':family,'rule':rule}]}
    result=r.request_review('window-review-test',data,{},call,save=lambda n,v:saved.update({n:v}))
    assert result['verdict']=='revise' and result['recipe']!=data['recipe']
    assert '-vlm-opinions' in calls[0][0] and '-llm-adjudicate' in calls[1][0]
    assert any('compiled-response' in k for k in saved)


@pytest.mark.parametrize('decision,blocks,verdict,valid',[
    ('reject',[6],'approve',True),('reject',[],'approve',False),
    ('accept',[6],'approve',False),('hold',[],'approve',False),
    ('hold',[],'hold',True),('reject',[999],'approve',False),
])
def test_opinion_decision_gates_approval(decision,blocks,verdict,valid):
    data=context();calls=[]
    def call(phase,system,request,schema,vision):
        calls.append(phase)
        if 'opinions' in schema['properties']:return {'opinions':['Potential missing hierarchy on page 2'],'summary':'Verify'}
        return {'verdict':verdict,'reviewed_state_id':request['reviewed_state_id'],'issues':[],'template_changes':[],
                'opinion_decisions':[{'opinion_id':'opinion-1','decision':decision,'reason':'Source comparison result','blocks':blocks}]}
    if valid:assert r.request_review('window-review-test',data,{},call)['verdict']==verdict
    else:
        with pytest.raises(ValueError,match='review_pending'):r.request_review('window-review-test',data,{},call)
        assert len(calls)==4  # one opinion call, three adjudication attempts


def test_omitted_opinion_never_silently_disappears():
    data=context()
    def call(phase,system,request,schema,vision):
        if 'opinions' in schema['properties']:return {'opinions':['First issue','Second issue'],'summary':'Two issues'}
        return {'verdict':'approve','reviewed_state_id':request['reviewed_state_id'],'issues':[],'template_changes':[],
                'opinion_decisions':[{'opinion_id':'opinion-1','decision':'reject','reason':'Evidence','blocks':[6]}]}
    with pytest.raises(ValueError,match='review_pending'):r.request_review('window-review-test',data,{},call)


@pytest.mark.parametrize('mode',['missing_decision','unseen_evidence','stale_state'])
def test_invalid_adjudication_receives_contract_and_can_hold(mode):
    data=context();seen=[]
    opinions=[{'id':'opinion-1','text':'Possible defect'},{'id':'opinion-2','text':'Uncertain hierarchy'}]
    def call(phase,system,request,schema,vision):
        seen.append(copy.deepcopy(request))
        out={'verdict':'hold','reviewed_state_id':request['reviewed_state_id'],
             'issues':[],'template_changes':[],
             'opinion_decisions':[{'opinion_id':o['id'],'decision':'hold','blocks':[],
                                   'reason':'Uncertain, preserve for review'} for o in opinions]}
        if len(seen)==1:
            if mode=='missing_decision':out['opinion_decisions'].pop()
            if mode=='unseen_evidence':out['opinion_decisions'][0]['blocks']=[999]
            if mode=='stale_state':out['reviewed_state_id']='stale'
        return out
    result=r.adjudicate_review('test',data,{},call,opinions=opinions)
    assert len(seen)==2 and result['verdict']=='hold' and result['recipe']==data['recipe']
    contract=seen[1]['repair_feedback']['constraints']
    assert contract['allowed_evidence_blocks']==[6]
    assert contract['required_opinion_ids']==['opinion-1','opinion-2']
    assert contract['reviewed_state_id']==seen[0]['reviewed_state_id']
    assert seen[1]['invalid_review']


@pytest.mark.parametrize('stage',['opinions','adjudicate'])
def test_exhausted_call_budget_does_not_enter_validation_retry(stage):
    from lawrag.core.structure.recipe_runtime import NeedsReview
    seen=[]
    def call(phase,*args):
        seen.append(phase)
        raise NeedsReview('model_call_budget_exhausted')
    with pytest.raises(NeedsReview,match='model_call_budget_exhausted'):
        r.request_review('test',context(),{},call,opinions=[] if stage=='adjudicate' else None)
    assert len(seen)==1
