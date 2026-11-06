"""The shared reason reviewer cannot substitute for current-request state review."""
from types import SimpleNamespace
import pytest
from test_transition import env as simple_env,initial,review,TASK
from test_memory_runtime_v2 import command

@pytest.fixture
def env(tmp_path):
 g=simple_env.__wrapped__(tmp_path);repo,executor,model,send=next(g)
 executor.pipeline=SimpleNamespace(term_agent=SimpleNamespace(profile={'candidate_navigation':{'supervisor_mode':'enforce'}}))
 original=repo.invoke;model.reason_inputs=[]
 def invoke(system,data,schema,phase):
  if phase=='memory-reason-decision-review':
   model.reason_inputs.append(data);return {'decision':'PASS'}
  return original(system,data,schema,phase)
 repo.invoke=invoke
 yield repo,executor,model,send
 try:next(g)
 except StopIteration:pass

def test_shared_reason_pass_does_not_skip_current_purpose_repair(env):
 repo,ex,model,send=env;gid=initial(env)['goal_id']
 wrong=command('RESEARCH_REENTER',target=gid,stage='SELECT')
 fixed=command('PURPOSE_REVISE',target=gid,task=TASK)
 r=send([wrong,fixed],[review('FOLLOWUP',TASK),review('FOLLOWUP',TASK)])
 assert r['goal_id']==gid and r['state']['task']==TASK and r['executed'][0]=='INTENT'
 assert len(model.reason_inputs)==3
 assert len([phase for phase,data in model.calls if phase=='memory-command-check'])==3
 assert repo.events(gid)[-1]['command']['method_id']=='PURPOSE_REVISE'

def test_repeated_invalid_intent_is_not_adopted_despite_reason_pass(env):
 repo,ex,model,send=env;gid=initial(env)['goal_id'];revision=repo.goal(gid,'s')['revision']
 wrong=command('RESEARCH_REENTER',target=gid,stage='SELECT')
 r=send([wrong,wrong],[review('FOLLOWUP',TASK),review('FOLLOWUP',TASK)])
 assert r['status']=='CLARIFY' and repo.goal(gid,'s')['revision']==revision
 assert len(model.reason_inputs)==2  # Exactly repeated proposal review reused.
