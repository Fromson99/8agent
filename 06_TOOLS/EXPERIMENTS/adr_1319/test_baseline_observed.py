"""Preserve the old failure mechanism, not a candidate acceptance test."""
from copy import deepcopy
from test_memory_runtime_v2 import memory,command,start
from semantic_runtime.legal_agent import output_contract as oc

def test_old_schema_accepts_authorized_reenter_loses_proposal_and_allows_goal_change(memory):
 mem,f,w,send,p=memory;gid=start(send)['goal_id'];observed=[]
 bad=command('RESEARCH_REENTER',target=gid,stage='ASSESS',document_scope_mode='AUTHORIZED')
 def invoke(system,data,schema,phase):
  observed.append(phase)
  if phase=='memory-resolve':oc.validate_shape(bad,schema);return deepcopy(bad)
  if phase=='memory-resolve-repair':
   assert data['rejected_decision'] is None
   assert data['repair_contract']['validation']['issues'][0]['path']=='/'
   return command('CASE_START',task='동일 질문',facts=[])
  return {'valid':True,'reason':'모의 승인'}
 mem.invoke=invoke
 result=mem.execute({'question':'동일 질문','session_id':'s','request_id':'baseline'},p)
 assert result['goal_id']!=gid and mem.db.execute('SELECT count(*) FROM goal').fetchone()[0]==2
 assert observed==['memory-resolve','memory-resolve-repair','memory-command-check']
