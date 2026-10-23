"""Fresh synthetic judgments at the native ASSESS wire and validation boundary."""
from common import *
import sys,time
sys.dont_write_bytecode=True
arm,cid=sys.argv[1:3];s=read(ART/'stage.json');C=ROOT/s['roots'][arm]
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient
from semantic_runtime.legal_agent import completion_execution as ce,completion_v8 as v8
case=next(c for c in read(ART/'assessment-cases.json') if c['id']==cid)
f=read(ART/'design-freeze.json')
assert sha(ART/'assessment-cases.json')==f['assessment_data']['cases_sha256']
for row in read(ROOT/s['candidate_dir']/'candidate.json')['files']:
 if arm=='candidate':assert sha(C/row['target_path'])==row['snapshot_sha256']
issues=[{'id':'Q1','question':case['question']}]
options=[{'id':'S'+str(i),'text':text,'source_id':'synthetic:'+cid+':'+str(i)} for i,text in enumerate(case['originals'],1)]
schema=v8.assessment_schema(issues,['B1'],options,[],case.get('previous_keys',[]))
wire,expand=ce.assessment_projection(schema)
prompt=ce.MODERN_ASSESS_PROMPT+'\n'+v8.PROMPT+'\n'+ce.CONDITION_GUIDANCE
payload={'request':case['question'],'current_request':case['question'],'issues':issues,
 'sources':[{'source_id':'synthetic:'+cid,'document_id':cid,'document_name':'모의 규정','evidence_refs':[o['id'] for o in options]}],
 'evidence_options':[{k:o[k] for k in ('id','text')} for o in options],'fact_sources':[],'gap_history':case.get('gap_history',[]),
 'saved_inventory':[{'material_id':'B1','document_name':'모의 규정'}]}
out=ART/'assessment-trials'/cid/arm;out.mkdir(parents=True,exist_ok=False)
client=ExperimentClient(ROOT,out/'model',max_calls=1,max_output_tokens=6000)
result={'case_id':cid,'arm':arm,'error':None};start=time.monotonic()
try:
 raw=client.generate(prompt,payload,wire,phase='assessment');result['raw']=raw
 value=expand(raw);accepted,model=v8.prepare(value,schema,issues,options,[])
 result['accepted']=accepted
except Exception as exc:result['error']={'type':type(exc).__name__,'message':str(exc)}
result.update(calls=client.calls,usage=client.usage,seconds=time.monotonic()-start)
save(out/'result.json',result)
print(cid,arm,'validated',result['error'] is None,flush=True)
