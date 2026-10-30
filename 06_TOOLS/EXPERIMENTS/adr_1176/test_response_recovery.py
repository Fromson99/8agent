from copy import deepcopy
import json
import pytest
from jsonschema import ValidationError
from types import SimpleNamespace as NS
from semantic_runtime.legal_agent import output_contract as oc,source_goal_control as sg,investigation_supervisor as su
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
from semantic_runtime.legal_agent.schema_preparation import validate as cached_validate
from semantic_runtime.legal_agent.errors import ContractError,ProposalError
from semantic_runtime.legal_agent.answer_progress import ProgressHandoff
from test_output_contract_recovery import Journal
from test_source_goals import setup,run,acquire

SCHEMA={'type':'object','anyOf':[
 {'type':'object','properties':{'choice':{'const':'LOCATE'},'document_ref':{'enum':['D1','D2']},'coordinate_scope':{'enum':['body','addendum']},'coordinate':{'type':'string','minLength':1}},'required':['choice','document_ref','coordinate_scope','coordinate'],'additionalProperties':False},
 {'type':'object','properties':{'choice':{'const':'READ'},'target':{'enum':['T1','T2']}},'required':['choice','target'],'additionalProperties':False}]}
GOOD={'choice':'LOCATE','document_ref':'D1','coordinate_scope':'body','coordinate':'제12조'}

@pytest.mark.parametrize('change,path',[
 ({'document_ref':'D99'},'/document_ref'),({'coordinate_scope':'조'},'/coordinate_scope'),
 ({'coordinate':123},'/coordinate'),({'coordinate':''},'/coordinate'),({'choice':'INVALID'},'/choice'),
 ({'document_ref':None},'/document_ref')])
def test_branch_specific_errors(change,path):
 v={**GOOD,**change};before=deepcopy(v)
 with pytest.raises(oc.OutputContractError) as caught:oc.validate_shape(v,SCHEMA)
 rows=caught.value.issues;assert path in [r['path'] for r in rows]
 assert not any(r['path']=='/target' for r in rows)
 assert v==before

def test_all_selected_branch_failures_together():
 with pytest.raises(oc.OutputContractError) as caught:oc.validate_shape({'choice':'LOCATE','document_ref':'D99','coordinate_scope':'조'},SCHEMA)
 rows=caught.value.issues;assert {r['path'] for r in rows}=={'/document_ref','/coordinate_scope','/coordinate'}
 assert next(r for r in rows if r['path']=='/document_ref')['expected_constraint']==['D1','D2']
 assert next(r for r in rows if r['path']=='/coordinate_scope')['received']=='조'

def test_cached_validation_preserves_exception_type_and_multiple_diagnostics():
 with pytest.raises(ValidationError) as caught:cached_validate({'choice':'LOCATE'},SCHEMA,owner=NS())
 assert {r['path'] for r in oc.diagnostics(caught.value)['issues']}=={'/document_ref','/coordinate_scope','/coordinate'}

def test_wire_errors_remain_in_wire_vocabulary_and_never_add_aliases():
 from semantic_runtime.legal_agent.stable_references import identities
 r=NavigationReferences({});r.document_forward={'internal-doc':'D1'};r.document_reverse={'D1':'internal-doc'}
 with pytest.raises(oc.OutputContractError) as caught:r.decode({**GOOD,'document_ref':'D99'},SCHEMA)
 diag=oc.diagnostics(caught.value);assert diag['reference_space']=='wire'
 assert r.view({'repair_contract':{'validation':diag}})['repair_contract']['validation']==diag
 found,_=identities({'repair_contract':{'validation':diag},'rejected_decision':{'document_ref':'D99'},'target':'T1'})
 assert found=={'T1'}

@pytest.mark.parametrize('valid_second',[True,False])
def test_one_durable_correction_same_menu_and_no_effects(tmp_path,valid_second):
 path=tmp_path/'journal.sqlite';repo=Journal(path);calls=[];effects=[];data={'sources':['kept'],'menu':['D1','D2']}
 def invoke(payload,attempt):
  calls.append(deepcopy(payload));assert payload['menu']==data['menu']
  if attempt:assert payload['repair_contract']['validation']['issues'][0]['path']=='/document_ref'
  return deepcopy(GOOD) if attempt and valid_second else {**GOOD,'document_ref':'D99'}
 def perform():
  value=oc.bounded_decision(repo,'read-choice',data,SCHEMA,invoke,lambda v:oc.validate_shape(v,SCHEMA));effects.append(value)
 if valid_second:perform();assert len(effects)==1
 else:
  with pytest.raises(ProposalError):perform()
  repo.db.close();repo=Journal(path)
  with pytest.raises(ProposalError):perform()
  assert effects==[]
 assert len(calls)==2

@pytest.mark.parametrize('error',[ContractError('ACL'),ContractError('hash'),ContractError('revision')])
def test_internal_integrity_errors_do_not_request_model_correction(tmp_path,error):
 repo=Journal(tmp_path/'journal.sqlite');calls=[]
 def invoke(p,a):calls.append(a);return GOOD
 def check(v):raise error
 with pytest.raises(ContractError):oc.bounded_decision(repo,'test',{},SCHEMA,invoke,check)
 assert calls==[0]

def looked_up():
 z=setup();inv,d,v,p,a,de,x=z;a.pop('READ');out=run(z);sg.after_execute(inv,d,out,True)
 d['presentation_id']='next';v['source_targets']=[]
 return z

def test_completed_lookup_without_read_yields_existing_selector_and_retains_goal():
 z=looked_up();inv,d,v,p,a,de,x=z;before=deepcopy(su.state_for(inv,d)['source_goals'])
 assert sg.preselect(inv,d,a) is None
 assert su.state_for(inv,d)['source_goals']==before
 assert su.state_for(inv,d)['halt'] is None
 assert inv.s.repo.events[-1][0]=='SOURCE_GOAL_SELECTION_REQUIRED'
 # Restart and ASSESS re-entry do not erase the failed lookup or invent arrival.
 inv.p=json.loads(json.dumps(inv.p));assert sg.preselect(inv,d,a) is None
 assert su.state_for(inv,d)['source_goals'][0]['routes']==['LOOKUP']

@pytest.mark.parametrize('choice',['FINISH','PENDING'])
def test_terminal_proposal_requests_repair_when_alternative_menu_remains(choice):
 z=looked_up();inv,d,v,p,a,de,x=z
 with pytest.raises(oc.OutputContractError) as caught:sg.validate_recovery_choice(inv,d,a,{'choice':choice})
 assert caught.value.issues[0]['code']=='REQUIRED_SOURCE_RECOVERY_CHOICE'
 assert su.state_for(inv,d)['source_goals'][0]['status']=='REQUIRED'

def test_exhausted_bridges_allow_explicit_limited_handoff_without_reset():
 z=looked_up();inv,d,v,p,a,de,x=z
 for i in range(2):
  d['presentation_id']='bridge'+str(i);de.update(next_action='RESEARCH',targets=[],queries=['different '+str(i)])
  assert run(z)==de
 d['presentation_id']='end';assert sg.preselect(inv,d,a) is None
 sg.validate_recovery_choice(inv,d,a,{'choice':'FINISH'})
 de.update(next_action='FINISH')
 with pytest.raises(ProgressHandoff,match='SOURCE_GOALS_UNRESOLVED:SG1'):run(z)
 assert len(su.state_for(inv,d)['source_goal_bridges'])==2

def test_changed_reason_does_not_create_new_route():
 z=looked_up();inv,d,v,p,a,de,x=z;de.update(next_action='RESEARCH',queries=['same query'],targets=[])
 run(z);d['presentation_id']='again';de['reason']='different prose'
 with pytest.raises(ProgressHandoff):run(z)
 assert len(su.state_for(inv,d)['source_goal_bridges'])==1

def test_new_exact_read_still_precedes_selector():
 z=looked_up();inv,d,v,p,a,de,x=z
 a['READ']={'action':'READ_ARTICLES','identity':{'document_id':'wanted','unit_id':'13','source_id':'wanted-source'}}
 # Native expansion requires real presentation; isolate scheduling with the unchanged executor adapter.
 out=sg.resolve(inv,d,a,p,{}, {'next_action':'FINISH'},x,su.state_for(inv,d),preselection=True)
 assert out['targets']==['READ'];acquire(inv,d,a);sg.after_execute(inv,d,out,True)
 assert sg.preselect(inv,d,a) is None and su.state_for(inv,d)['source_goals'][0]['status']=='ACQUIRED'

@pytest.mark.parametrize('field',['validation','rejected_assessment','rejected_proposal','rejected_output'])
def test_all_correction_payloads_are_not_new_reference_authority(field):
    from semantic_runtime.legal_agent.stable_references import identities
    found,_=identities({field:{'document_ref':'D9999','claim_refs':['C9999']},'target':'T1'})
    assert found=={'T1'}
