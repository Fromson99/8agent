"""Real native API: false PASS, primary repair, source scope, durable state, duplicate."""
import json,sqlite3
from copy import deepcopy
import pytest
from test_multiturn_structured_scope import tree
from test_memory_runtime_v2 import command
from test_legal_agent_double_harness import wire
from semantic_runtime.legal_agent.shortcut_store import selected_store

def test_native_repaired_command_controls_actual_task_and_scope(tree,tmp_path,monkeypatch):
 import test_scoped_multiturn_api as fixture
 from api_fixture_integrated import decode
 original=fixture.create_app;seen=[];checks=[];primary=[];repairs=[];runtimes=[];active=[]
 from semantic_runtime.legal_agent.gateway import ModelGateway
 generate=ModelGateway.generate
 def capture(self,phase,view,schema_name,**kwargs):
  active.append({'stage':view.get('source_stage',phase),'view':deepcopy(view)})
  try:return generate(self,phase,view,schema_name,**kwargs)
  finally:active.pop()
 monkeypatch.setattr(ModelGateway,'generate',capture)
 def create(*a,**kw):
  transport=kw['legal_agent_transport'];send=transport.send_once
  kw['legal_agent_profile']['candidate_navigation'].update(supervisor_mode='enforce',minimal_input=True)
  runtimes.append(kw['runtime_root'])
  def current(*,body,ticket):
   view=decode(json.loads(body['messages'][1]['content'])['view']);phase=view.get('source_stage') or active[-1]['stage']
   schema=body['response_format']['json_schema']['schema']
   if phase in ('memory-reason-decision-review','source-reason-decision-review','memory-final-reason-review'):
    return wire({'decision':'PASS'})
   if phase=='source-law-navigation-supervisor-read-choice' and '"PASS"' in json.dumps(schema):
    return wire({'decision':'PASS'})
   if phase in ('memory-resolve','memory-resolve-repair'):
    target=transport.command['target']
    if target:
     fixed=deepcopy(transport.command);fixed['task']=view['utterance']
     primary.append(deepcopy(view))
     if phase=='memory-resolve-repair':repairs.append(deepcopy(view));return wire(fixed)
     return wire(command('RESEARCH_REENTER',target=target,stage='SELECT'))
   if phase=='memory-command-check':
    checks.append(deepcopy(view));return wire({'valid':True,'reason':'Scripted reviewer intent, deliberately false first PASS',
     'request_relation':'FOLLOWUP','requested_task':view['context']['utterance']})
   if phase.startswith('memory-intent'):seen.append(deepcopy(view))
   # Minimal native packets omit the host-owned dispatch stage. Restore only
   # that label for the legacy scripted fixture; the recorded request and all
   # product schemas/validators remain unchanged.
   adapted=deepcopy(body);packet=json.loads(adapted['messages'][1]['content'])
   packet['view']=deepcopy(active[-1]['view']);packet['view']['source_stage']=phase
   adapted['messages'][1]['content']=json.dumps(packet,ensure_ascii=False)
   return send(body=adapted,ticket=ticket)
  transport.send_once=current
  return original(*a,**kw)
 monkeypatch.setattr(fixture,'create_app',create)
 fixture.test_scope_survives_actual_ask_correction_and_duplicate(tmp_path,tree,True,True)
 assert len(checks)==2 and len(repairs)==1
 assert repairs[0]['rejected_decision']['command']['method_id']=='RESEARCH_REENTER'
 assert checks[0]['transition']['after']['task']!=checks[0]['context']['utterance']
 assert checks[1]['transition']['after']['task']==checks[1]['context']['utterance']
 with sqlite3.connect(selected_store(runtimes[0])) as db:
  state=json.loads(db.execute('SELECT state FROM goal').fetchone()[0])
 assert state['task']==checks[1]['context']['utterance']
 assert seen and seen[-1]['current_request']==state['task']
