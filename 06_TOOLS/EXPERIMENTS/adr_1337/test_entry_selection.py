from copy import deepcopy
from pathlib import Path
import importlib.util,json,gzip
import pytest
from semantic_runtime.legal_agent import memory_methods as mm,investigation_supervisor as su,corrected_memory as cm,case_repository as cr
from test_memory_runtime_v2 import command
from conftest import term_glossary
ROOT=Path(__file__).resolve().parents[3]
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path);v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v);return v
prior=module('entry_prior','06_TOOLS/EXPERIMENTS/adr_1332/test_repeat_scope.py')
finish=module('entry_finish_fixture','06_TOOLS/EXPERIMENTS/adr_1312/test_finish.py')
current_wire=prior.current_wire

def record(n):
 p=ROOT/f'04_EXPERIMENTS/ADR/ADR-1335-voting-repeat-live/artifacts/public-live/repeat-integrated/canonical/{n:03}.json.gz'
 with gzip.open(p,'rt') as f:return json.load(f)

def test_recorded_supervisor_input_restores_exact_selected_source_progress():
 general=record(3)['view'];old=record(4)['view']
 assert general['structure_selection_progress'][0]['remaining_unit_ids'] and 'structure_selection_progress' not in old
 inv,data,value,decision,_=finish.fixture();data.update(deepcopy(general));st=su.state_for(inv,data)
 before=deepcopy(general);out=su.review_payload(inv,data,general,value,st,'recorded')
 assert out['structure_selection_progress']==general['structure_selection_progress'] and general==before
 out['structure_selection_progress'][0]['remaining_unit_ids'].clear()
 assert general['structure_selection_progress'][0]['remaining_unit_ids']

@pytest.mark.parametrize('remaining,complete,ready',[([],True,True),(['u'],False,False),([],False,False),(['u'],True,False)])
def test_partial_selection_cannot_take_ready_fast_path(remaining,complete,ready):
 inv,data,value,decision,_=finish.fixture()
 data['structure_selection_progress']=[{'remaining_unit_ids':remaining,'delivered_complete':complete}]
 st=su.record(inv,data,value,'key')
 assert su.ready_for_assessment(inv,data,value,decision,st)==ready

@pytest.mark.parametrize('fault',['link','acquisition','unknown','nonrepairable'])
def test_resume_stage_distinguishes_original_acquisition_from_review(fault):
 v=prior.prior.incomplete()
 if fault=='acquisition':v['model_proposal']['failure']['issues']=[{'code':'SCOPE_ACQUISITION_INCOMPLETE'}]
 if fault=='unknown':v['model_proposal']['failure_code']='MODEL_DEADLINE_EXCEEDED'
 if fault=='nonrepairable':v['model_proposal']['failure']['repairable']=False
 before=deepcopy(v);r=mm.review_recovery(v);assert v==before
 assert r['available']==(fault in ('link','acquisition'))
 assert r['restart_stage']==('SELECT' if fault=='acquisition' else 'ASSESS' if fault=='link' else None)
 assert r['requires_source_completion']==(fault=='acquisition')
 assert r['automatic_retry'] is False
 if fault=='acquisition':assert r['all_requested_sources_acquired'] is False and not r['does_not_establish_missing_source']

def test_actual_acquisition_diagnostic_is_not_recast_as_only_link_error():
 d=record(6)['view']['repair_feedback']['validation'];v=prior.prior.incomplete();v['model_proposal']['failure']=d
 r=mm.review_recovery(v)
 assert r['failure']==d and r['restart_stage']=='SELECT'
 assert r['requires_source_completion'] and r['source_acquisition_confirmed']

@pytest.mark.parametrize('inject_stale',[False,True])
def test_real_shortcut_api_binds_current_request_before_repeat_resolver(tmp_path,term_glossary,monkeypatch,current_wire,inject_stale):
 from need_continuity_fixture import run_api
 if inject_stale:
  execute=cr.CaseRepository.execute
  def stale(self,body,principal):
   self._resolve_request={'body':{'question':'다른 요청','request_id':'old'},'principal':{'document_ids':[]}}
   return execute(self,body,principal)
  monkeypatch.setattr(cr.CaseRepository,'execute',stale)
 seen=[];resolve=cm.Memory.resolve
 def exercise(api,transport,request,runtime):
  first=api.post('/v1/rag/ask',json=request);assert first.status_code==200,first.text
  a=first.json();gid=a['question_id'];assert a['answer']['claims']
  # The original single-request fixture never implemented conversation routing.
  import test_legal_agent_double_harness as harness
  original_send=transport.send_once
  def send_once(*,body,ticket):
   view=json.loads(body['messages'][1]['content'])['view']
   if view.get('source_stage')=='source-request-route':
    transport.calls.append('source-request-route')
    return harness.wire({'mode':'CASE','answer':'','reason':'same conversation request','catalogue':None})
   return original_send(body=body,ticket=ticket)
  transport.send_once=send_once

  def observed(self,context):
   assert self._resolve_request['body']['request_id']=='r2'
   assert self._resolve_request['body']['question']==request['question']
   assert mm.literal_repeat_target(context,self._resolve_request['body'],self._resolve_request['principal'])==gid
   parts=self.parts(gid);before={k:deepcopy(parts[k]) for k in ('READ','SELECT')}
   old=self.invoke
   def invoke(system,view,schema,phase):
    if phase.startswith('memory-resolve'):
     assert view['literal_repeat_target']==gid and 'CASE_START' not in view['offered_methods']
     seen.append(phase);return command('ANSWER_PRESENT',target=gid)
    if phase=='memory-command-check':return {'valid':True,'reason':'scripted exact repeat presentation'}
    return old(system,view,schema,phase)
   self.invoke=invoke
   try:result=resolve(self,context)
   finally:self.invoke=old
   assert all(self.parts(gid)[k]==before[k] for k in before)
   return result
  monkeypatch.setattr(cm.Memory,'resolve',observed)
  second={**request,'request_id':'r2'};response=api.post('/v1/rag/ask',json=second)
  assert response.status_code==200,response.text
  b=response.json();assert b['question_id']==gid and b['executed']==['COMPOSE'] and b['answer']['claims']
  n=len(transport.calls);again=api.post('/v1/rag/ask',json=second)
  assert again.status_code==200 and again.json()['answer']==b['answer'] and len(transport.calls)==n
  assert seen==['memory-resolve']
  return a,b
 result=run_api(tmp_path,term_glossary,'goal_control',monkeypatch,exercise=exercise)
 assert result

def test_recorded_partial_selection_finish_requires_supervisor_without_changing_original(monkeypatch):
 from semantic_runtime.legal_agent import read_judgment as rj
 path=ROOT/'04_EXPERIMENTS/ADR/ADR-1309-main136-sqlite-latency/artifacts/live/ontology-369-after/canonical'
 with gzip.open(path/'005.json.gz','rt') as f:data=json.load(f)['view']
 with gzip.open(path/'005-output.json.gz','rt') as f:value=json.load(f)
 inv,_,_,decision,_=finish.fixture();inv.question=data['current_request'];inv.s.scope={s['document_id'] for s in data['sources']}
 visible=rj.originals(inv,data);ctx=data['read_judgments'];heads={}
 for jid,row in visible.items():heads[jid]=deepcopy(next(h for h in ctx['judgments'] if h['source_id']==row['source_id'] and h['document_id']==row['document_id']))
 state={'version':rj.VERSION,'heads':heads,'needs':{n['id']:n for n in ctx['needs']},'conflicts':{n['id']:n for n in ctx['conflicts']},'receipts':{}}
 state['state_hash']=rj.seal(state);inv.p['read_judgments']={rj.request_key(inv,data):state}
 st=su.state_for(inv,data);st['source_goals']=deepcopy(data['source_goal_context']['goals']);st['calls']=1;st['since_review']=2;su.save(inv,st)
 assert any(r['remaining_unit_ids'] or not r['delivered_complete'] for r in data['structure_selection_progress'])
 before=deepcopy((data,value))
 with pytest.raises(finish.Called):finish.gate(inv,data,value,decision)
 assert (data,value)==before and any(k=='SUPERVISOR_REQUESTED' for k,v in inv.s.repo.events)
