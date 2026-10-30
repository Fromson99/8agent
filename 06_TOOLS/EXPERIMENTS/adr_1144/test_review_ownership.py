from copy import deepcopy
import pytest
from jsonschema import validate,ValidationError
from test_stable_recovery_isolated import new_setup,fresh,RefRepo
from semantic_runtime.legal_agent import read_judgment as rj,output_contract as oc

@pytest.mark.parametrize('relation,refs_count,allowed',[('DIRECT',0,True),('DIRECT',1,True),('DEPENDENCY',0,False),('DEPENDENCY',1,True)])
def test_model_schema_matches_dependency_reference_requirement(relation,refs_count,allowed):
 inv,data,*_=new_setup();ctx=rj.context(inv,data,'a');current={s['id']:s for s in data['sources']};raw=fresh(ctx);raw.update(choice='FOLLOW_CONNECTION',relation=relation,judgment_refs=ctx['new_review_ids'][:refs_count])
 base={'anyOf':[{'type':'object','properties':{'choice':{'const':'FOLLOW_CONNECTION'},'relation':{'enum':['DIRECT','DEPENDENCY']}},'required':['choice','relation']}]}
 schema=rj.attach(base,ctx,current,['Q1'])
 if allowed:validate(raw,schema)
 else:
  with pytest.raises(ValidationError):validate(raw,schema)

@pytest.mark.parametrize('resubmit',[False,True])
def test_rejected_judgment_is_not_a_retained_head(tmp_path,resubmit):
 inv,data,*_=new_setup();ctx=rj.context(inv,data,'a');current={s['id']:s for s in data['sources']};raw=fresh(ctx);raw.update(choice='FOLLOW_CONNECTION',relation='DEPENDENCY',issue_id='Q1',judgment_refs=[]);repo=RefRepo(tmp_path/'journal');calls=[]
 def invoke(payload,attempt):
  calls.append(payload);v=deepcopy(raw)
  if attempt:
   expected=payload['repair_contract']['validation']['issues'][0]['expected_constraint']
   assert expected['retained_judgment_ids']==[] and expected['rejected_response_is_not_committed']
   v['judgment_refs']=ctx['new_review_ids'][:1]
   if not resubmit:v['read_review']={'new_reviews':{}}
  return v
 def check(v):
  n,_=rj.normalize_review(v,ctx);rj.validate_review(n,ctx,current,['Q1'])
 if not resubmit:
  with pytest.raises(oc.OutputContractError):oc.bounded_decision(repo,'read',data,{},invoke,check)
  assert not inv.p.get('read_judgments')
 else:
  v=oc.bounded_decision(repo,'read',data,{},invoke,check);n,ch=rj.normalize_review(v,ctx);rj.record(inv,data,n,'a',ctx,{})
  state=rj.state_for(inv,data);assert len(state['heads'])==1 and next(iter(state['heads'].values()))['version']==1
 assert len(calls)==2
