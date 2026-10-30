from copy import deepcopy
import json,gzip
import pytest
from jsonschema import validate,ValidationError
from semantic_runtime.legal_agent import source_goal_control as sg,investigation_supervisor as su
from semantic_runtime.legal_agent.errors import ProposalError,ContractError
from test_source_goals import setup,run
from common import ROOT,ART,put

@pytest.mark.parametrize('scope',['조','항','호','목','본문','',None,'body ','unknown'])
def test_invalid_scope_rejected_without_goal_or_dispatch(scope):
 z=setup();z[2]['source_targets'][0]['coordinate_scope']=scope
 with pytest.raises(ProposalError,match='coordinate_scope'):run(z)
 assert not su.state_for(z[0],z[1]).get('source_goals')
 assert not any(k=='SOURCE_GOAL_DISPATCH' for k,v in z[0].s.repo.events)

@pytest.mark.parametrize('scope',sg.COORDINATE_SCOPES)
def test_supported_scope_unchanged(scope):
 z=setup();z[2]['source_targets'][0]['coordinate_scope']=scope
 out=run(z)
 if scope=='body':assert out['targets']==['READ']
 else:assert out['structure_filter']['coordinate_scope']==scope

@pytest.mark.parametrize('route',['refresh','goal_id','preselect'])
def test_persisted_bad_scope_never_reaches_executor(route):
 z=setup();run(z);inv,data=z[:2];st=su.state_for(inv,data);st['source_goals'][0]['coordinate_scope']='조';su.save(inv,st)
 before=sum(k=='SOURCE_GOAL_DISPATCH' for k,v in inv.s.repo.events)
 with pytest.raises(ContractError,match='coordinate_scope'):
  if route=='refresh':sg.refresh(inv,st['source_goals'])
  elif route=='goal_id':sg.from_goal_id(inv,data,z[4],'SG1')
  else:sg.preselect(inv,data,z[4])
 assert sum(k=='SOURCE_GOAL_DISPATCH' for k,v in inv.s.repo.events)==before

def test_wire_contract_also_rejects_level_labels():
 z=setup();inv,d,v,p,a,de,x=z;schema=sg.fields(inv,d,a)['source_targets'];row={k:v for k,v in v['source_targets'][0].items() if k!='lookup_target'};row['document_ref']='wanted'
 validate([row],schema)
 with pytest.raises(ValidationError):validate([{**row,'coordinate_scope':'조'}],schema)

def test_actual_cm009_saved_bad_scope_rejected_without_rewriting_it():
 P=ROOT/'04_EXPERIMENTS/ADR/ADR-1174-assessment-answer-consistency/artifacts/live/cm-009'
 raw=[]
 for f in sorted((P/'canonical').glob('*-output.json.gz')):
  v=json.load(gzip.open(f,'rt'));raw.extend(v.get('source_targets',[]))
 row=next(x for x in raw if x['coordinate_scope']=='조');before=deepcopy(row)
 with pytest.raises(ProposalError):sg.validate_scope(row['coordinate_scope'])
 assert row==before
 put(ART/('cm009-replay-'+__import__('common').read(__import__('common').DES/'freeze.json')['execution_id']+'.json'),{'source':str(P.relative_to(ROOT)),'original_target':row,'rejected_before_tool':True,'auto_body_correction':False,'new_model_calls':0,'historical_live_result_preserved':True})
