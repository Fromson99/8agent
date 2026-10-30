from copy import deepcopy
from types import SimpleNamespace
import pytest
from semantic_runtime.legal_agent import read_judgment_final as fj, output_contract as oc, request_repair as rr
from semantic_runtime.legal_agent.corrected_memory import Reenter
from semantic_runtime.legal_agent.errors import ContractError, ProposalError

def fixture(monkeypatch):
    gap={'material':True,'kind':'MISSING_SOURCE','issue_id':'Q1','identity_key':'missing',
         'target_binding_hash':'scope-hash','target_binding':{'status':'EXACT','expected':[{'document_id':'d','block_id':'b','start_cp':0,'end_cp':5}]}}
    core={'disposition':'NEEDS_INVESTIGATION','claims':[],'gaps':[gap],'issue_assessments':[]}
    impl=SimpleNamespace(prepare=lambda *a:(deepcopy(core),{}),materialize=lambda v,*a:deepcopy(v))
    monkeypatch.setattr(rr,'bind_gaps',lambda v,*a,**kw:v)
    monkeypatch.setattr(rr,'may_reopen',lambda *a:True)
    events=[];budget={'model_limit':40,'finalization_reserve':2,'model_reserved':5}
    host=SimpleNamespace(issues=[{'id':'Q1'}],reentry_counters={},verify_claims=lambda *a:None,
        s=SimpleNamespace(work=SimpleNamespace(budget=lambda:budget,event=lambda *a:events.append(a)),
            context=SimpleNamespace(remaining=lambda:120),sources=SimpleNamespace(profile={
                'candidate_navigation':{'assessment_reentry_limit':2},'selection_time_reserve_seconds':20,'max_no_progress':3})))
    args={'content_impl':impl,'options':[],'facts':[],'sources':[], 'investigation':{'binding':{'scope':['d']}},
        'rounds':[],'allowed_targets':['missing'],'decision_key':'decision'}
    value={**deepcopy(core),fj.FIELD:{'judgments':[],'needs':[],'conflicts':[]}}
    schema={'properties':{fj.FIELD:{}},'required':[fj.FIELD]}
    err=oc.OutputContractError('bad final review',[],category='FINAL_READ_REVIEW_INVALID')
    return host,err,value,schema,args,core,events,budget

@pytest.mark.parametrize('guard',['budget','deadline','counter','fact','already_read','unlocated','unrelated_error','bad_core','changed_authorization'])
def test_independent_recovery_respects_remaining_guards(monkeypatch,guard):
    h,e,v,s,a,c,events,b=fixture(monkeypatch)
    if guard=='budget':b['model_reserved']=39
    if guard=='deadline':h.s.context.remaining=lambda:0
    if guard=='counter':h.reentry_counters={'ASSESS_GAP_REENTRY':2}
    if guard=='fact':c['gaps'][0]['kind']='MISSING_FACT'
    if guard=='unlocated':c['gaps'][0]['target_binding']['status']='UNLOCATED'
    if guard=='already_read':a['options']=[{'document_id':'d','block_id':'b','start_cp':0,'end_cp':5,'text_hash':'same'}]
    if guard=='unrelated_error':e=ProposalError('unrelated')
    if guard=='bad_core':a['content_impl'].prepare=lambda *a:(_ for _ in ()).throw(ProposalError('invalid evidence'))
    if guard=='changed_authorization':
        monkeypatch.setattr(rr,'bind_gaps',lambda *a,**kw:(_ for _ in ()).throw(ContractError('changed authorization')))
        with pytest.raises(ContractError):fj.independent_research(h,e,v,s,**a)
    else:assert fj.independent_research(h,e,v,s,**a) is False
    assert events==[]

def test_same_target_and_originals_do_not_reset_on_restart(monkeypatch):
    h,e,v,s,a,c,events,b=fixture(monkeypatch);before=deepcopy(v)
    a['investigation']['no_progress']=3
    with pytest.raises(Reenter) as result:fj.independent_research(h,e,v,s,**a)
    payload=result.value.payload
    assert payload['investigation_state']['no_progress']==0
    assert payload['investigation_state']['final_review_recovery'][0]['previous_no_progress']==3
    assert payload['assessment']['claims']==[] and payload['assessment'][fj.FIELD]['review'] is None
    assert v==before and len(events)==1
    a['investigation']=deepcopy(payload['investigation_state']);a['decision_key']='new-decision'
    assert fj.independent_research(h,e,v,s,**a) is False
    assert len(events)==1
