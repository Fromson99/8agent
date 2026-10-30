from common import *
import sys,time,traceback
sys.dont_write_bytecode=True
f=read(ART/'freeze.json');C=ROOT/f['code_root'];sys.path[:0]=[str(C/'02_BACKEND')]
for n,h in f['files'].items():assert sha(C/n)==h,n
for n,h in f['inputs'].items():assert sha(ROOT/n)==h,n
for n,h in f['scripts'].items():assert sha(ROOT/n)==h,n
assert read(ART/'check-001.json')['status']==0
from semantic_runtime.legal_agent import ontology_semantics as sem
from semantic_runtime.legal_agent.errors import ContractError
from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,_schema_for_api
out=ART/'build';assert not out.exists(),'Build is immutable; no retry outside the frozen two-call loop'
out.mkdir();client=ExperimentClient(ROOT,out/'raw',max_calls=2,max_output_tokens=None,max_repairs=0)
data=read(ART/'build-input.json');prompt_input={'concept':data['concept'],'originals':[{'id':s['id'],'label':s['anchor']['label'],'text':s['text']} for s in data['originals']],'judgments':[{'id':j['id'],'judgment':j['judgment']} for j in data['judgments']]}
previous=read(ART/'previous-proposal.json');assert sha(ROOT/previous['path'])==previous['sha256']
try:sem.validate(previous['proposal'],data['originals'],data['judgments'])
except ContractError as error:prompt_input.update(previous_proposal=previous['proposal'],structural_errors=[str(error)],repair_instruction='명시된 역할·방향 계약에 맞춰 수정한다. 원문·의미를 자동 추정하지 않는다.')
put(out/'input.json',prompt_input);started=time.monotonic();result={'status':'failed','quality_certified':False,'authority':'EXPERIMENT_PROPOSAL_NOT_APPROVED'}
try:
 for attempt in range(2):
  print('SEMANTIC_PROPOSAL_CALL',attempt+1,flush=True)
  try:
   phase='semantic-proposal' if not attempt else 'semantic-repair'
   payload={'model':client.model,'messages':[{'role':'system','content':sem.PROMPT},{'role':'user','content':json.dumps(prompt_input,ensure_ascii=False)}],'temperature':0,'stream':False,'response_format':{'type':'json_schema','json_schema':{'name':'ontology_semantics','strict':True,'schema':_schema_for_api(sem.SCHEMA)}}}
   raw=client.chat_completions(payload,phase=phase,timeout_seconds=600)
   try:p=json.loads(raw['body_json']['choices'][0]['message']['content'])
   except (ValueError,KeyError,IndexError) as e:raise ExperimentFormatError('Incomplete JSON',response=raw) from e
   put(out/'raw'/f'call-{client.calls:03d}-{phase}'/'output.json',p)
   bound=sem.bind(p,data['originals'],data['judgments']);put(out/'binding.json',bound)
   fragments=[{'anchor':s['anchor'],'text':s['text'],'evidence_refs':[s['id']]} for s in data['originals']]
   plan=sem.compile_plan(bound,fragments);put(out/'compiled.json',plan)
   result.update(status='complete',nodes=len(p['nodes']),dependencies=sum(len(n['dependencies']) for n in p['nodes']),exception_targets=sum(len(n['exception_targets']) for n in p['nodes']),steps=len(plan['ordered_steps']),unresolved=len(p['unresolved']),binding_sha256=sha(out/'binding.json'));break
  except (ContractError,ExperimentFormatError) as e:
   result.setdefault('failures',[]).append({'attempt':attempt+1,'error_type':type(e).__name__,'error':str(e)[:1200]})
   put(out/('failure-'+str(attempt+1)+'.json'),result['failures'][-1])
   if attempt:break
   files=sorted((out/'raw').glob('call-*/output.json'))
   if files:previous=read(files[-1])
   else:
    responses=sorted((out/'raw').glob('call-*/response.json'))
    if not responses:raise
    raw=read(responses[-1]);previous=raw.get('choices',[{}])[0].get('message',{}).get('content','')
   prompt_input={**prompt_input,'previous_proposal':previous,'structural_errors':[str(e)[:1200]],'repair_instruction':'원문과 기존 의미를 유지하고 지적된 구조/참조/인용 불일치만 보완한다. 근거가 없는 부분은 unresolved로 남긴다.'}
except Exception as e:result.update(error_type=type(e).__name__,error=str(e));(out/'error.txt').write_text(traceback.format_exc())
finally:
 result.update(calls=client.calls,usage=client.usage,seconds=time.monotonic()-started);put(out/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k!='usage'},ensure_ascii=False),flush=True)
raise SystemExit(0 if result['status']=='complete' else 1)
