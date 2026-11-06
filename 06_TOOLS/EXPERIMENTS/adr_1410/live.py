"""Actual Qwen final-stage call using recorded real CM originals, no retrieval replay."""
from common import *
import sqlite3,time,traceback
from copy import deepcopy
from types import SimpleNamespace as S
x=read(DES/'candidate-selected.json');C=ROOT/x['code_root']
for n,h in x['selected_files'].items():assert sha(C/n)==h,n
for n,h in read(DES/'live-pins.json')['files'].items():assert sha(ROOT/n)==h,n
case=read(DES/'actual-cm003.json.gz');base=ART/'actual-final-r6';base.mkdir(exist_ok=False)
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND'),str(ROOT)]
import lawrag;lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
from semantic_runtime.legal_agent import completion_contracts as cc,guided_answer as guided
from semantic_runtime.legal_agent.completion_execution import CompletionExecution
from lawrag.research.experiment_client import ExperimentClient
from resource_guard import Guard
class Journal:
 def __init__(self):self.states={};self.events=[]
 def event(self,k,v):self.events.append((k,deepcopy(v)))
 def output_decision_state(self,k):return self.states.get(k)
 def output_decision_event(self,v):self.states[v['decision_key']]=deepcopy(v)
assert case['question']==next(c['question'] for c in read(ROOT/'01_DATA/review/cm_core_e2e_v3.json')['cases'] if c['id']=='cm-003')
auth=read(DES/'authorization.json');assert sha(ROOT/auth['question_authorization_path'])==auth['question_authorization_sha256']
source=ROOT/read(DES/'baseline.json')['release']['data_path'];manifest=read(source/'manifest.json')
assert sha(source/'store.sqlite')==manifest['store_sha256']
checks=[]
with sqlite3.connect((source/'store.sqlite').as_uri()+'?mode=ro',uri=True) as db:
 for src in case['sources']:
  assert src['document_id'] in auth['documents']
  for span in src['adopted_spans']:
   row=db.execute('SELECT text FROM source_block WHERE document_id=? AND block_id=?',(src['document_id'],str(span['block_id']))).fetchone()
   assert row and row[0][span['start_cp']:span['end_cp']]==span['text']
   checks.append({'document_id':src['document_id'],'block_id':span['block_id'],'match':True})
put(base/'source-verification.json',{'checks':checks,'generation_id':manifest['generation_id'],'store_sha256':manifest['store_sha256'],'schema':'actual CM approved public sources, no expected answers'})
guard=Guard(base);guard.start();client=ExperimentClient(ROOT,base/'model',max_calls=2,max_repairs=0,provider_policy=DES/'provider-policy.json')
def compressed(p,value):
 p=Path(p)
 if p.name in ('request.json','response.json','output.json','validation-schema.json'):
  write_raw_json(p.with_suffix('.json.gz'),value)
 else:put(p,value)
client._write=compressed
calls=[];journal=Journal()
def invoke(prompt,data,schema,phase):
 assert phase==guided.PHASE and not calls
 guard.check();calls.append({'phase':phase,'started':True});put(base/'logical-calls.json',calls)
 write_raw_json(base/'actual-input.json.gz',{'system':prompt,'data':data,'schema':schema})
 return client.generate(prompt,data,schema,phase=phase)
def verify_read(read):
 assert read==case['parts']['READ']['payload']
executor=S(s=S(work=journal,sources=S(profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'))),host=S(binding=case['parts']['READ']['payload']['binding'],verify=verify_read),
    invoke=invoke,selected_originals=lambda _:deepcopy(case['sources']))
parts=deepcopy(case['parts']);begin=time.monotonic()
try:
 assessment=CompletionExecution.completion_stage(executor,'ASSESS',case['state'],parts,case['question'],None,{})
 parts['ASSESS']={'payload':assessment}
 answer=CompletionExecution.completion_stage(executor,'COMPOSE',case['state'],parts,case['question'],None,{})
 cc.verify_composition(assessment,answer)
 before=client.calls
 again=CompletionExecution.completion_stage(executor,'ASSESS',case['state'],parts,case['question'],None,{})
 assert again==assessment and client.calls==before
 put(base/'assessment.json',assessment);put(base/'answer.json',answer)
 (base/'사용자답변.txt').write_text(answer['text']+'\n')
 put(base/'result.json',{'case_id':'cm-003','environment':'new final ASSESS/COMPOSE, recorded real CM originals; full retrieval/multiturn not rerun','question':case['question'],'seconds':time.monotonic()-begin,'model_calls':client.calls,'logical_calls':len(calls),'review_calls':0,'repair_calls':0,'extra_calls_on_repeat':client.calls-before,'unknown':0,'usage':client.usage,'answer_coverage':assessment['answer_coverage'],'needs_guidance':assessment['guided_reply']['needs_guidance'],'source_checks':len(checks),'source_mismatches':0,'claims':len(answer['claims'])})
 print(answer['text'],flush=True)
except Exception as exc:
 put(base/'failure.json',{'type':type(exc).__name__,'error':str(exc),'unknown':getattr(exc,'unknown',False),'calls':client.calls,'usage':client.usage,'traceback':traceback.format_exc()})
 raise
finally:
 guard.done.set();guard.thread.join(2);put(base/'journal.json',journal.events)
 put(base/'resources.json',{'sample':guard.check(),'baseline':guard.baseline})
