"""Explicit user-authorized model configuration on the unchanged ADR0438 harness."""
import importlib.util,json,hashlib,sys,time
from pathlib import Path
from copy import deepcopy
from lawrag.platform.workspace import load_layout
from lawrag.research.experiment_client import GeminiExperimentClient
R=load_layout().root;D=R/'04_EXPERIMENTS/ADR/ADR-0440-task-harness-flash-medium';A=D/'artifacts';OLD=R/'04_EXPERIMENTS/ADR/ADR-0438-task-harness-live-validation/artifacts'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def new(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
class ScopedClient(GeminiExperimentClient):
 def __init__(self,root,output,**kw):
  super().__init__(root,output,**kw)
  design=read(A/'frozen-design.json');m=read(D/'실험/manifest.json');override=m['llm_policy']['experiment_override']
  if sha(A/'frozen-design.json')!=override['frozen_design_sha256'] or design['scope_authorization']!=override['authorization']:raise ValueError('scoped authorization drift')
  config=design['configs']['flash-medium']
  if config['model'] not in override['allowed_models'] or design['scope_authorization']['fallback_allowed'] is not False:raise ValueError('unauthorized model')
  self.policy=deepcopy(self.policy);self.policy.update(config,allowed_models=[config['model']])
  self.model=config['model'];self.policy['authorization']=design['scope_authorization'];self.policy['parent_policy_sha256']=self.policy_hash
  self.policy_hash=hashlib.sha256(json.dumps(self.policy,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
  self._write(self.output/'scoped-policy.json',{'effective_policy':self.policy,'effective_policy_sha256':self.policy_hash,'frozen_design_sha256':sha(A/'frozen-design.json')})
def main():
 if (A/'runs').exists():raise ValueError('already started; new ADR required for rerun')
 lock=read(A/'input-lock.json')
 for p,h in lock['files'].items():
  if sha(R/p)!=h:raise ValueError('input drift '+p)
 print('all frozen inputs verified',flush=True)
 spec=importlib.util.spec_from_file_location('parent438',R/'06_TOOLS/EXPERIMENTS/adr_0438/run_probe.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
 modules,root=old.load();store=modules['storage'].Store(OLD/'generation');auth=read(A/'authorization.json')
 if not auth['authorized'] or store.manifest['store_sha256']!=auth['source_store_sha256']:raise ValueError('source authorization drift')
 p=modules['pipeline'].Pipeline(root,store,old.Provider(None));config=deepcopy(p.term_agent.config);config.update(implementation='definition-scope-harness-v1',task_policy=read(OLD/'policy-binding.json'));config['limits']=read(A/'frozen-design.json')['limits'];config['learning']={'capture':False}
 p.term_agent=modules['task_harness_agent'].ServingTaskHarnessAgent(p,config);p.task_harness_journal=A/'execution.sqlite'
 prior=read(OLD/'results.json')['cases'];results={};A.joinpath('runs').mkdir();started=time.monotonic()
 try:
  for c in read(A/'dataset/product-cases.json'):
   if c['scope_document_ids']!=auth['scope_document_ids']:raise ValueError('scope drift')
   cid=c['id'];base=deepcopy(prior[cid]['harness']);base['arm_id']='baseline';base['historical_origin']='ADR-0438-experiment-v1/harness';new(A/'runs'/f'{cid}-baseline.json',base)
   client=ScopedClient(R,A/'calls'/cid/'flash-medium',max_calls=config['limits']['max_calls']);p.provider=old.Provider(client);start=time.monotonic()
   try:
    out=p.run(c['question'],c['scope_document_ids'],True);p.contracts.validate(out,'urn:8-agent:term-runtime-v1','Result')
    if any(s['document_id'] not in c['scope_document_ids'] for s in out['assembly']['context']):raise ValueError('scope escape')
    record={'case_id':cid,'arm_id':'flash-medium','output':out,'calls':client.calls,'usage':client.usage,'elapsed_seconds':time.monotonic()-start,'downstream_contract':'PASS'}
   except Exception as exc:record={'case_id':cid,'arm_id':'flash-medium','output':None,'calls':client.calls,'usage':client.usage,'elapsed_seconds':time.monotonic()-start,'downstream_contract':'FAIL','failure':{'type':type(exc).__name__,'message':str(exc)[:2000]}}
   new(A/'runs'/f'{cid}-flash-medium.json',record);results[cid]={'baseline':base,'flash-medium':record};s=(record.get('output') or {}).get('retrieval',{}).get('term_agent',{})
   print(json.dumps({'case':cid,'calls':client.calls,'status':s.get('status'),'phase':s.get('task_state',{}).get('phase'),'read':len(s.get('read_source_ids',[])),'seconds':round(record['elapsed_seconds'],2),'failure':record.get('failure') or s.get('failure')},ensure_ascii=False),flush=True)
  for path,h in lock['files'].items():
   if sha(R/path)!=h:raise ValueError('input drift after execution '+path)
  new(A/'results.json',{'cases':results,'elapsed_seconds':time.monotonic()-started,'baseline':'Historical ADR0438 harness outputs, no new baseline calls','main_wiring':'unchanged','gold_visible_to_product':False})
 finally:store.close()
if __name__=='__main__':main()
