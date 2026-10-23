"""One schema-bound assessment with identical evidence; never reads grading-only."""
from common import *
import sys,time,traceback
sys.dont_write_bytecode=True
arm,cid=sys.argv[1:];s=read(ART/'stage.json');C=ROOT/s['roots'][arm];f=read(ART/'design-freeze.json')
assert not (ART/'stop.json').exists()
assert sha(ART/'cases.json')==f['cases_sha256']
assert all(sha(C/n)==h for n,h in f['files'][arm].items())
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient,ExperimentProviderError,ExperimentTransportError
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import completion_execution as ce,completion_v8 as v8,request_repair as rr
from semantic_runtime.legal_agent import narrative_answer
from prompt_text import assessment_prompt
case=next(c for c in read(ART/'cases.json') if c['id']==cid)
out=ART/'trials'/cid/arm;out.mkdir(parents=True,exist_ok=False)
client=ExperimentClient(ROOT,out/'model',max_calls=1,max_output_tokens=6000)
issues=[{'id':'Q1','question':case['question'],'request_quote':case['question']}]
spans=[{'id':'S'+str(i),'text':t,'source_id':'synthetic:'+cid+':'+str(i),'document_id':'D1','block_id':str(i),'start_cp':0,'end_cp':len(t),'text_hash':digest(t)} for i,t in enumerate(case['originals'],1)]
state={}
if case.get('previous_claim'):rr.retain_assessment_review(state,{'claims':[{'claim_id':'C1','issue_refs':['Q1'],'text':case['previous_claim'],'span_receipts':[spans[0]]}]},case['question'])
schema=v8.assessment_schema(issues,['B1'],spans,[],['K1'] if case.get('old_gap') else [])
wire,expand=ce.assessment_projection(schema)
data={'current_request':case['question'],'question':case['question'],'issues':issues,'sources':[{'source_id':o['source_id'],'document_name':'모의규정','evidence_refs':[o['id']]} for o in spans],'evidence_options':[{'id':o['id'],'text':o['text']} for o in spans],'user_fact_sources':[],'saved_inventory':[{'material_id':'B1','document_name':'모의규정'}],'previous_assessments':rr.assessment_review_context(state,case['question'],spans,issues),'gap_history':([{'round':1,'gaps':[{'gap_key':'K1','kind':'MISSING_SOURCE','reason':case['old_gap'],'navigation_status':'UNRESOLVED'}]}] if case.get('old_gap') else [])}
r={'arm':arm,'case_id':cid,'error':None};start=time.monotonic()
try:
 raw=client.generate(assessment_prompt(C,ce,v8,narrative_answer),data,wire,phase='assessment')
 r['raw']=raw;r['accepted'],r['proposal']=v8.prepare(expand(raw),schema,issues,spans,[])
except Exception as exc:
 r['error']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
 if isinstance(exc,(ExperimentProviderError,ExperimentTransportError)):
  save(ART/'stop.json',{'reason':'PROVIDER_OR_TRANSPORT_FAILURE','case_id':cid,'arm':arm,'status_code':(getattr(exc,'response',None) or {}).get('status_code')})
r.update(calls=client.calls,usage=client.usage,seconds=time.monotonic()-start)
save(out/'result.json',r);print(cid,arm,'validated',r['error'] is None,flush=True)
if (ART/'stop.json').exists():raise SystemExit(2)
