from copy import deepcopy
import json,gzip
from pathlib import Path
import pytest
from semantic_runtime.legal_agent import corrected_memory as m, memory_methods as mm
from test_memory_runtime_v2 import Fake, command

TASK='같은 제도의 다른 소집 유형 시기는?'
class Model:
 def __init__(self):self.calls=[];self.proposals=[];self.reviews=[]
 def __call__(self,system,data,schema,phase):
  self.calls.append((phase,deepcopy(data)))
  if phase.startswith('memory-resolve'):return deepcopy(self.proposals.pop(0))
  if phase=='memory-command-check':return deepcopy(self.reviews.pop(0))
  raise AssertionError(phase)
def review(relation,task,valid=True):return {'valid':valid,'reason':'현재 발언과 적용 상태 대조','request_relation':relation,'requested_task':task}
@pytest.fixture
def env(tmp_path):
 model=Model();executor=Fake();repo=m.Memory(tmp_path/'state.sqlite',executor,model)
 principal={'user_id':'u','team_id':'t','document_ids':['d']};counter=0
 def send(proposals,reviews,question='현재 요청',request_id=None):
  nonlocal counter
  counter+=1;model.proposals=deepcopy(proposals);model.reviews=deepcopy(reviews)
  return repo.execute({'session_id':'s','request_id':request_id or 'r'+str(counter),'question':question},principal)
 yield repo,executor,model,send
 repo.close()
def initial(env):
 repo,ex,model,send=env
 return send([command('CASE_START',task='정기 소집 시기는?',facts=[])],[review('NEW_TOPIC','정기 소집 시기는?')])

def test_actual1398_false_pass_is_repaired_before_any_execution(env):
 repo,ex,model,send=env;first=initial(env);gid=first['goal_id'];old=deepcopy(repo.route(gid))
 root=Path('/home/jin/8-AGENT/04_EXPERIMENTS/ADR/ADR-1398-lifecycle-alternate-providers/artifacts/public-live/deepinfra-provider-matrix/canonical')
 wrong=json.load(gzip.open(root/'007-output.json.gz','rt'));wrong['target']=gid
 fixed=command('PURPOSE_REVISE',target=gid,task=TASK)
 result=send([wrong,fixed],[review('FOLLOWUP',TASK),review('FOLLOWUP',TASK)],question='그럼 다른 소집 유형은?')
 assert result['goal_id']==gid and result['state']['task']==TASK
 assert result['executed'][0]=='INTENT' and repo.parts(gid)['INTENT']['payload']['purpose']==TASK
 assert repo.db.execute('SELECT payload FROM route WHERE id=?',(old['id'],)).fetchone()[0]==m.encoded(old['payload'])
 repair=next(data for phase,data in model.calls if phase=='memory-resolve-repair')
 assert repair['rejected_decision']['command']==wrong
 assert repair['rejected_decision']['check']['valid'] is True
 assert any(x['code']=='FOLLOWUP_PURPOSE_NOT_APPLIED' for x in repair['repair_contract']['validation']['issues'])
 assert fixed==model.calls[-1][1]['command'] or model.calls[-1][1]['command']['task']==TASK


def test_same_bad_command_twice_preserves_goal_and_idempotent_failure(env):
 repo,ex,model,send=env;gid=initial(env)['goal_id'];before=deepcopy(repo.goal(gid,'s'));route=deepcopy(repo.route(gid))
 bad=command('RESEARCH_REENTER',target=gid,stage='SELECT')
 result=send([bad,bad],[review('FOLLOWUP',TASK),review('FOLLOWUP',TASK)],request_id='failed-current')
 assert result['status']=='CLARIFY' and repo.goal(gid,'s')==before and repo.route(gid)==route
 count=len(model.calls)
 assert send([],[],request_id='failed-current')==result and len(model.calls)==count
 assert len([p for p,d in model.calls if p=='memory-resolve-repair'])==1


def test_new_topic_cannot_be_approved_as_old_goal_reentry(env):
 repo,ex,model,send=env;gid=initial(env)['goal_id'];before=deepcopy(repo.goal(gid,'s'))
 bad=command('RESEARCH_REENTER',target=gid,stage='SELECT')
 fixed=command('CASE_START',task='관계없는 의결권 질문',facts=[])
 result=send([bad,fixed],[review('NEW_TOPIC','관계없는 의결권 질문'),review('NEW_TOPIC','관계없는 의결권 질문')])
 assert result['goal_id']!=gid and repo.goal(gid,'s')==before


def test_condition_change_must_reach_facts_and_keep_purpose(env):
 repo,ex,model,send=env;gid=initial(env)['goal_id']
 bad=command('RESEARCH_REENTER',target=gid,stage='ASSESS')
 fixed=command('FACT_UPDATE',target=gid,facts=[{'name':'보유 주식','value':'100주'}])
 r=send([bad,fixed],[review('CONDITION_CHANGE','정기 소집 시기는?'),review('CONDITION_CHANGE','정기 소집 시기는?')])
 assert r['goal_id']==gid and r['state']['facts']==fixed['facts'] and r['state']['task']=='정기 소집 시기는?'
 assert r['executed']==['ASSESS','COMPOSE']

@pytest.mark.parametrize('method,stage,relation',[
 ('ANSWER_PRESENT','NONE','PRESENTATION'),('RESEARCH_REENTER','ASSESS','REVIEW'),
 ('RESEARCH_REENTER','SELECT','REPEAT'),('HISTORY_EXPLAIN','NONE','HISTORY'),
 ('EXPERIENCE_CONFIRM','NONE','CONFIRMATION')])
def test_matching_unchanged_purpose_is_not_rejected(env,method,stage,relation):
 repo,ex,model,send=env;gid=initial(env)['goal_id'];before=len(model.calls)
 r=send([command(method,target=gid,stage=stage)],[review(relation,'정기 소집 시기는?')])
 assert r['status']!='CLARIFY' and len(model.calls)-before==2


def test_applied_state_drift_is_blocked_before_goal_mutation(env):
 repo,ex,model,send=env;gid=initial(env)['goal_id'];before=deepcopy(repo.goal(gid,'s'))
 def corrupt(state,c,utterance):return {**state,'task':'다른 목적으로 변조'}
 ex.scope_state=corrupt
 with pytest.raises(Exception,match='transition differs'):
  send([command('PURPOSE_REVISE',target=gid,task=TASK)],[review('FOLLOWUP',TASK)])
 assert repo.goal(gid,'s')==before


def test_preview_preserves_original_fields_and_does_not_mutate_inputs():
 old={'id':'g','state':{'task':'목적','facts':[{'name':'주체','value':'회사'}],'queries':['기존 검색'],'source_category':'external','document_ids':['secret-host-inventory']},'events':[]}
 context={'utterance':'그럼 예외는?','goals':[old]};raw=command('PURPOSE_REVISE',target='g',task=TASK)
 c=mm.normalize(raw,{'utterance':context['utterance'],'goals':[{**old,'status':'READY'}],'knowledge':[]})
 original=deepcopy(context);preview=mm.transition_preview(c,context)
 assert context==original and preview['after']['facts']==old['state']['facts']
 assert 'document_ids' not in preview['after'] and preview['changed_fields']==['task']
