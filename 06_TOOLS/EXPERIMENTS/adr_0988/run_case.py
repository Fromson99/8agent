"""One frozen native decision, one actual Qwen call. Gold never enters product."""
from common import *
import sys,time,importlib.util,traceback
sys.dont_write_bytecode=True
arm,cid=sys.argv[1:3];s=read(ART/'stage.json');C=ROOT/s['roots'][arm]
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import completion_execution as ce,completion_v8 as v8,request_repair as rr,decision_projection as dp,output_contract as oc
case=next(c for c in read(ART/'cases.json') if c['id']==cid)
f=read(ART/'design-freeze.json');assert sha(ART/'cases.json')==f['cases_sha256']
assert all(sha(C/n)==h for n,h in f['files'][arm].items())
out=ART/'trials'/cid/arm;out.mkdir(parents=True,exist_ok=False)
client=ExperimentClient(ROOT,out/'model',max_calls=1,max_output_tokens=6000)
issues=[{'id':'Q1','question':case['question'],'request_quote':case['question']}]
spans=[{'id':'S'+str(i),'text':t,'source_id':'synthetic:'+cid+':'+str(i),'document_id':'D1','block_id':str(i),'start_cp':0,'end_cp':len(t),'text_hash':digest(t)} for i,t in enumerate(case['originals'],1)]
state={}
if case.get('previous_claim'):rr.retain_assessment_review(state,{'claims':[{'claim_id':'C1','issue_refs':['Q1'],'text':case['previous_claim'],'span_receipts':[spans[0]]}]},case['question'])
result={'case_id':cid,'arm':arm,'phase':case['phase'],'error':None};start=time.monotonic()
try:
 if case['phase']=='assessment':
  schema=v8.assessment_schema(issues,['B1'],spans,[],['K1'] if case.get('old_gap') else [])
  wire,expand=ce.assessment_projection(schema)
  payload={'request':case['question'],'current_request':case['question'],'issues':issues,'sources':[{'source_id':o['source_id'],'document_id':'D1','document_name':'모의 규정','evidence_refs':[o['id']]} for o in spans], 'evidence_options':[{'id':o['id'],'text':o['text']} for o in spans],'user_fact_sources':[],'saved_inventory':[{'material_id':'B1','document_name':'모의 규정'}],'previous_assessments':rr.assessment_review_context(state,case['question'],spans,issues),'gap_history':([{'round':1,'gaps':[{'gap_key':'K1','kind':'MISSING_SOURCE','reason':case['old_gap'],'navigation_status':'UNRESOLVED'}]}] if case.get('old_gap') else [])}
  raw=client.generate(ce.MODERN_ASSESS_PROMPT+'\n'+v8.PROMPT+'\n'+ce.CONDITION_GUIDANCE,payload,wire,phase='assessment')
  result['raw']=raw;accepted,proposal=v8.prepare(expand(raw),schema,issues,spans,[]);result['accepted']=accepted
 else:
  import pytest
  spec=importlib.util.spec_from_file_location('fixture_0988',ROOT/'06_TOOLS/EXPERIMENTS/adr_0885/test_focus.py');unit=importlib.util.module_from_spec(spec);spec.loader.exec_module(unit)
  mp=pytest.MonkeyPatch();inv,data,actions,_,_=unit.fixture(mp,{})
  inv.question=case['question'];inv.p.update(state);inv.control=False;inv.left=lambda:180
  data['current_request']=case['question'];data['issues']=issues;data['investigation_scope']={'request':case['question']}
  o=spans[0];data['sources']=[{**o,'id':'E1','branch_id':'B1','spans':[o]}]
  data['structure_catalogue']={'items':[{'document_id':'D1','document_name':'모의 규정','read_action':x['target'],'title':x['heading'],'preview':x['preview']} for x in case.get('candidates',[])]}
  if not case.get('candidates'):actions.pop('T1')
  if case.get('old_gap'):
   data['assessment_gaps']=[{'gap_id':'G1','gap_key':'K1','issue_id':'Q1','kind':'MISSING_SOURCE','material':True,'reason':case['old_gap'],'suggested_action':'READ_SCOPE'}]
  def invoke(system,payload,schema,phase,timeout):
   save(out/'decision-input.json',payload);raw=client.generate(system,payload,schema,phase='navigation');result['raw']=raw;return raw
  inv.invoke=invoke
  def once(repo,phase,payload,schema,call,verify,**kwargs):
   value=call(payload,0);verify(value);return value
  mp.setattr(oc,'bounded_decision',once)
  try:result['accepted']=dp.choose_read(inv,data,actions,'source-law-navigation-probe')
  finally:mp.undo()
except Exception as exc:result['error']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
result.update(calls=client.calls,usage=client.usage,seconds=time.monotonic()-start)
save(out/'result.json',result);print(cid,arm,'valid',result['error'] is None,flush=True)
