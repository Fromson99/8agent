from copy import deepcopy
import gzip,json
from pathlib import Path
import pytest
from semantic_runtime.legal_agent import output_contract as oc, memory_methods as mm, corrected_memory as cm
from test_memory_runtime_v2 import memory, command, start
ROOT=Path('/home/jin/8-AGENT')
OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1318-integration-search-r2-answer-check/artifacts/public-live/b03-27-selected-main/canonical'

def closed(context):
 value=deepcopy(cm.COMMAND);value['properties'].pop('action');value['required'].remove('action')
 from semantic_runtime.legal_agent.query_scope import model_change_schema
 value['properties']['search_scope_change']=model_change_schema()
 if 'search_scope_change' not in value['required']:value['required'].append('search_scope_change')
 value['properties']['document_scope_mode']={'enum':['KEEP','AUTHORIZED']};value['properties']['document_ids']={'type':'null'}
 value['anyOf']=[mm.command_branch(value,name,context) for name in mm.offered(context)]
 return value

def test_recorded_call009_is_precisely_rejected_and_same_goal_keep_is_valid():
 raw=json.loads(gzip.decompress((OLD/'009-output.json.gz').read_bytes()))
 ctx={'goals':[{'id':raw['target'],'status':'PENDING','events':[]}],'knowledge':[]}
 schema=closed(ctx)
 with pytest.raises(oc.OutputContractError) as e:oc.validate_shape(raw,schema)
 assert any(i['path']=='/document_scope_mode' and i['expected_constraint']=='KEEP' for i in e.value.issues)
 fixed={**raw,'document_scope_mode':'KEEP'};oc.validate_shape(fixed,schema)
 result=mm.normalize(fixed,ctx);assert result['target']==raw['target'] and result['action']=='FOLLOW'

@pytest.mark.parametrize('name',['ANSWER_PRESENT','HISTORY_EXPLAIN','EXPERIENCE_CONFIRM','RESEARCH_REENTER','FACT_UPDATE','PURPOSE_REVISE','STATE_RESTORE','NEED_TARGET'])
def test_authorized_only_for_methods_which_normalize_allows(name):
 ctx={'goals':[{'id':'g','status':'READY','events':[{'id':1,'after':{'task':'x'}}]}],'knowledge':[]}
 schema=mm.command_branch(closed(ctx),name,ctx)
 assert schema['properties']['document_scope_mode']=={'type':'string','const':'KEEP'}

@pytest.mark.parametrize('drift',[False,True])
def test_actual_memory_repair_preserves_proposal_and_cannot_change_goal(memory,drift):
 mem,f,w,send,p=memory;gid=start(send)['goal_id'];seen=[]
 bad=command('RESEARCH_REENTER',target=gid,stage='ASSESS',document_scope_mode='AUTHORIZED')
 def invoke(system,data,schema,phase):
  seen.append((phase,deepcopy(data),deepcopy(schema)))
  if phase=='memory-resolve':return bad
  if phase=='memory-resolve-repair':
   assert data['rejected_decision']=={'command':bad,'check':None}
   assert schema['properties']['method_id']=={'const':'RESEARCH_REENTER'}
   assert schema['properties']['target']=={'const':gid}
   return command('CASE_START',task='새 질문') if drift else {**bad,'document_scope_mode':'KEEP'}
  assert phase=='memory-command-check';return {'valid':True,'reason':'same goal'}
 mem.invoke=invoke
 result=mem.execute({'question':'같은 질문을 다시 검토해줘','session_id':'s','request_id':'repair'},p)
 assert mem.db.execute('SELECT count(*) FROM goal').fetchone()[0]==1
 if drift:
  assert result['status']=='CLARIFY'
  assert len(seen)==2
 else:
  assert result['goal_id']==gid and result['executed']==['ASSESS','COMPOSE']
  assert len(seen)==3
  again=mem.execute({'question':'같은 질문을 다시 검토해줘','session_id':'s','request_id':'repair'},p)
  assert again==result and len(seen)==3


def test_semantic_command_check_can_reselect_a_new_topic(memory):
 mem,f,w,send,p=memory;gid=start(send)['goal_id'];checks=0
 def invoke(system,data,schema,phase):
  nonlocal checks
  if phase=='memory-resolve':return command('RESEARCH_REENTER',target=gid,stage='ASSESS')
  if phase=='memory-resolve-repair':
   assert 'const' not in schema['properties']['method_id']
   return command('CASE_START',task='별도 주제',facts=[])
  checks+=1;return {'valid':checks==2,'reason':'다른 주제이므로 새 질문'}
 mem.invoke=invoke
 result=mem.execute({'question':'전혀 다른 질문','session_id':'s','request_id':'semantic'},p)
 assert result['goal_id']!=gid and checks==2


def test_repair_diagnostic_does_not_adopt_or_erase_any_original_claim():
 from semantic_runtime.legal_agent import read_judgment_final as rjf
 value={'claims':[{'claim_id':'C1','evidence_refs':['S1']}],
  'read_judgment_review':{'judgments':[{'id':'J1','disposition':'UNRESOLVED','basis_refs':['S1']}]},
  'gaps':[{'material':True,'reason':'보존할 미확인'}]}
 before=deepcopy(value);error=oc.OutputContractError('link',[oc.issue('NEED_CLAIM_LINK')])
 rows=rjf.repair_choices(value,error)
 assert value==before and rows[0]['path']=='/read_judgment_review/judgments/0'
 assert rows[0]['claims_sharing_evidence']==['C1'] and len(rows[0]['alternatives'])==2
 assert rjf.repair_choices(value,oc.OutputContractError('unrelated',[oc.issue('CLAIM_EVIDENCE_INVALID')]))==[]


def test_exception_proposal_survives_journal_restart(tmp_path):
 from test_output_contract_recovery import Journal
 path=tmp_path/'journal.sqlite';repo=Journal(path);calls=[]
 schema={'type':'object','properties':{'ok':{'const':True}},'required':['ok']}
 raw={'ok':False}
 def invoke(payload,attempt):
  calls.append(attempt)
  if not attempt:
   error=oc.OutputContractError('bad',[oc.issue('SCHEMA_CONST','/ok')]);error.proposal=raw;raise error
  assert payload['rejected_decision']==raw
  return {'ok':True}
 assert oc.bounded_decision(repo,'test',{},schema,invoke,lambda v:oc.validate_shape(v,schema))=={'ok':True}
 repo.db.close();repo=Journal(path)
 assert oc.bounded_decision(repo,'test',{},schema,lambda *_:pytest.fail('duplicate'),lambda v:oc.validate_shape(v,schema))=={'ok':True}
 assert calls==[0,1]
