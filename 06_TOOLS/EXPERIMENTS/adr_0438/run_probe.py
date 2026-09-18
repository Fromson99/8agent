"""Explicit frozen code injection, real serving adapters, gold-free product execution."""
import argparse
from copy import deepcopy
import hashlib,importlib,importlib.util,json,os,shutil,sys,time
from pathlib import Path
from lawrag.platform.workspace import load_layout
R=load_layout().root;C=R/'02_BACKEND/lawrag/research/candidates/adr_0438/harness';D=R/'04_EXPERIMENTS/ADR/ADR-0438-task-harness-live-validation';A=D/'artifacts';G=R/'01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260916-v1';LOCAL=A/'generation';ARMS=['baseline','harness']
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def new(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def rel(p):return str(p.relative_to(R))
def load():
 cm=read(C/'candidate.json');rev=cm['revisions'][-1]
 for item in rev['files']:
  if sha(R/item['frozen_path'])!=item['snapshot_sha256']:raise ValueError('frozen code drift')
 root=C/'revisions'/rev['revision_id']/'snapshot';name='probe438'
 spec=importlib.util.spec_from_file_location(name,root/'02_BACKEND/semantic_runtime/__init__.py',submodule_search_locations=[str(root/'02_BACKEND/semantic_runtime')]);pkg=importlib.util.module_from_spec(spec);sys.modules[name]=pkg;spec.loader.exec_module(pkg)
 return {key:importlib.import_module(name+'.'+key) for key in ['pipeline','storage','task_policy','task_harness_agent','navigation_agent']},root
class Provider:
 def __init__(self,client):self.client=client
 def call(self,role,system,data,schema):
  value=self.client.generate(system,data,schema,phase=role)
  return value,self.client.usage[-1]
 def record_local(self,value):return {'kind':'local-contract','data':value}
def prepare():
 if (A/'input-lock.json').exists():raise ValueError('already sealed')
 m,root=load()
 if LOCAL.exists():raise ValueError('candidate generation already exists')
 # Read-only hardlink view preserves all original data bytes and flags. Only new
 # experiment policy is written here; original immutable source is never edited.
 shutil.copytree(G,LOCAL,copy_function=os.link)
 policy=m['task_policy'];db=LOCAL/'task-policy.sqlite'
 proposal=policy.propose_definition(db,policy.DEFAULT)
 review=policy.review_definition(db,'definition_scope',1,'Codex experiment-only protocol review','Unchanged first implementation definition reviewed before live calls; no gold, source coordinates, mappings or operating approval')
 binding={k:proposal[k] for k in ['id','version','definition_sha256']};binding.update(path='task-policy.sqlite',sha256=sha(db),review_sha256=review['review_sha256'])
 policy.load_bound_definition(LOCAL,binding);new(A/'policy-binding.json',binding)
 manifest=read(D/'실험/manifest.json');cm=read(C/'candidate.json');rev=cm['revisions'][-1]
 isolation=manifest['design']['code_isolation'];isolation.update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'harness','experiment_id':manifest['experiment_id'],'arm_id':'harness','run_ids':['run-001'],'manifest_path':rel(C/'candidate.json'),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':rel(Path(__file__)),'runner_sha256':sha(__file__)}])
 (D/'실험/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 paths=[R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'08_DEPLOYMENT/CONFIG/legal-source-export.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',A/'dataset/product-cases.json',A/'authorization.json',A/'design-before-snapshot.json',A/'policy-binding.json',C/'candidate.json']
 paths += list(Path(__file__).parent.glob('*.py'))+[R/f['frozen_path'] for f in rev['files']]+[p for p in LOCAL.rglob('*') if p.is_file()]
 lock={'files':{},'gold_visible_to_product':False,'data_view':'hardlinked immutable exact generation; no data edits','definition_review_scope':'this experiment only'}
 for p in sorted(set(paths)):
  lock['files'][rel(p)]=sha(p)
  if p.stat().st_size>1024**3:print('sealed',rel(p),flush=True)
 new(A/'input-lock.json',lock);print('input lock sealed; no model calls',len(paths),flush=True)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--prepare',action='store_true');args=ap.parse_args()
 if args.prepare:return prepare()
 if (A/'runs').exists():raise ValueError('run already started; no automatic rerun')
 lock=read(A/'input-lock.json')
 for path,expected in lock['files'].items():
  if sha(R/path)!=expected:raise ValueError('input drift '+path)
 auth=read(A/'authorization.json');cases=read(A/'dataset/product-cases.json');design=read(A/'design-before-snapshot.json')['design']
 if not auth['authorized'] or auth['product_cases_sha256']!=sha(A/'dataset/product-cases.json'):raise ValueError('authorization drift')
 if any(c['scope_document_ids']!=auth['scope_document_ids'] for c in cases):raise ValueError('unauthorized document scope')
 from lawrag.research.experiment_client import GeminiExperimentClient
 m,root=load();store=m['storage'].Store(LOCAL)
 if store.manifest['store_sha256']!=auth['source_store_sha256']:raise ValueError('source hash drift')
 runtimes={}
 for arm in ARMS:
  p=m['pipeline'].Pipeline(root,store,Provider(None));config=deepcopy(p.term_agent.config);config['limits']=design['limits'];config['learning']={'capture':False}
  if arm=='harness':
   config.update(implementation='definition-scope-harness-v1',task_policy=read(A/'policy-binding.json'))
   p.term_agent=m['task_harness_agent'].ServingTaskHarnessAgent(p,config);p.task_harness_journal=A/'execution.sqlite'
  else:p.term_agent=m['navigation_agent'].ServingNavigationAgent(p,config)
  runtimes[arm]=p
 results={};A.joinpath('runs').mkdir();started=time.monotonic()
 try:
  for number,case in enumerate(cases):
   order=ARMS if number%2==0 else list(reversed(ARMS))
   for arm in order:
    client=GeminiExperimentClient(R,A/'calls'/case['id']/arm,max_calls=design['limits']['max_calls']);p=runtimes[arm];p.provider=Provider(client);start=time.monotonic()
    try:
     out=p.run(case['question'],case['scope_document_ids'],True);p.contracts.validate(out,'urn:8-agent:term-runtime-v1','Result')
     for s in out['assembly']['context']:
      if s['document_id'] not in case['scope_document_ids']:raise ValueError('scope escape')
     record={'case_id':case['id'],'arm_id':arm,'output':out,'calls':client.calls,'usage':client.usage,'elapsed_seconds':time.monotonic()-start,'downstream_contract':'PASS'}
    except Exception as exc:
     record={'case_id':case['id'],'arm_id':arm,'output':None,'calls':client.calls,'usage':client.usage,'elapsed_seconds':time.monotonic()-start,'downstream_contract':'FAIL','failure':{'type':type(exc).__name__,'message':str(exc)[:2000]}}
    new(A/'runs'/f"{case['id']}-{arm}.json",record);results.setdefault(case['id'],{})[arm]=record
    state=(record.get('output') or {}).get('retrieval',{}).get('term_agent',{})
    print(json.dumps({'case':case['id'],'arm':arm,'calls':client.calls,'status':state.get('status'),'phase':state.get('task_state',{}).get('phase'),'read':len(state.get('read_source_ids',[])),'selected':len(state.get('selected_ids',[])),'seconds':round(record['elapsed_seconds'],2),'failure':record.get('failure') or state.get('failure')},ensure_ascii=False),flush=True)
  for path,expected in lock['files'].items():
   if sha(R/path)!=expected:raise ValueError('input drift after execution '+path)
  new(A/'results.json',{'cases':results,'elapsed_seconds':time.monotonic()-started,'main_wiring':'unchanged','gold_visible_to_product':False})
 finally:store.close()
if __name__=='__main__':main()
