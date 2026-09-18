"""Frozen 3-arm synthetic probe; product runner never reads grading/gold.json."""
import argparse,hashlib,importlib,importlib.util,json,sys,time
from pathlib import Path
from lawrag.platform.workspace import load_layout
R=load_layout().root;D=R/'04_EXPERIMENTS/ADR/ADR-0446-korean-legal-tool-routing';A=D/'artifacts';T=R/'06_TOOLS/EXPERIMENTS/adr_0446';ARMS=['baseline','controlled','legal']
P=R/'02_BACKEND/lawrag/research/candidates/adr_0445/structured';C=R/'02_BACKEND/lawrag/research/candidates/adr_0446';TARGET='02_BACKEND/semantic_runtime/legal_navigation.py'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(Path(p).relative_to(R))
def new(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def load(frozen=True):
 cm=read(P/'candidate.json');rev=cm['revisions'][-1]
 for f in rev['files']:
  if sha(R/f['frozen_path'])!=f['snapshot_sha256']:raise ValueError('parent revision drift')
 root=P/'revisions'/rev['revision_id']/'snapshot';name='probe446base'
 if name not in sys.modules:
  spec=importlib.util.spec_from_file_location(name,root/'02_BACKEND/semantic_runtime/__init__.py',submodule_search_locations=[str(root/'02_BACKEND/semantic_runtime')]);pkg=importlib.util.module_from_spec(spec);sys.modules[name]=pkg;spec.loader.exec_module(pkg)
 mods={k:importlib.import_module(name+'.'+k) for k in ['pipeline','structured_navigation']}
 for arm,folder in [('controlled','controlled'),('legal','routing')]:
  cr=C/folder;path=cr/'snapshot'/TARGET
  if frozen:
   cm=read(cr/'candidate.json');rev=cm['revisions'][-1]
   for f in rev['files']:
    if sha(R/f['frozen_path'])!=f['snapshot_sha256']:raise ValueError('candidate drift')
   path=cr/'revisions'/rev['revision_id']/'snapshot'/TARGET
  module_name=name+'.'+arm;spec=importlib.util.spec_from_file_location(module_name,path);module=importlib.util.module_from_spec(spec);sys.modules[module_name]=module;spec.loader.exec_module(module);mods[arm]=module
 return mods,root
class Provider:
 def __init__(self,client):self.client=client
 def call(self,role,system,data,schema):return self.client.generate(system,data,schema,phase=role),self.client.usage[-1]
 def record_local(self,value):return {'kind':'local-contract','data':value}
def prepare():
 if (A/'input-lock.json').exists():raise ValueError('already sealed')
 m=read(D/'실험/manifest.json');bindings=[]
 for arm,folder in [('controlled','controlled'),('legal','routing')]:
  path=C/folder/'candidate.json';cm=read(path);rev=cm['revisions'][-1]
  bindings.append({'candidate_id':folder,'experiment_id':m['experiment_id'],'arm_id':arm,'run_ids':['run-001'],'manifest_path':rel(path),'manifest_sha256':sha(path),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':rel(__file__),'runner_sha256':sha(__file__)})
 m['design']['code_isolation']['candidates']=bindings;(D/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 paths=[A/'dataset/product-cases.json',A/'dataset/synthetic-sources.json',A/'grading/gold.json',A/'source-inventory.json',A/'design-before-snapshot.json',A/'authorization.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',P/'candidate.json']+list(T.glob('*.py'))
 for folder in [P,C/'controlled',C/'routing']:
  cm=read(folder/'candidate.json');paths+=[folder/'candidate.json']+[R/f['frozen_path'] for f in cm['revisions'][-1]['files']]
 new(A/'input-lock.json',{'files':{rel(p):sha(p) for p in sorted(set(paths))},'gold_visible_to_product':False});new(A/'pre-call-manifest.json',m);print('sealed',len(set(paths)),'files')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--prepare',action='store_true');args=ap.parse_args()
 if args.prepare:return prepare()
 if (A/'runs').exists():raise ValueError('already run: new ADR required')
 for p,h in read(A/'input-lock.json')['files'].items():
  if sha(R/p)!=h:raise ValueError('input drift '+p)
 from lawrag.research.experiment_client import GeminiExperimentClient
 import fixtures
 cases=read(A/'dataset/product-cases.json');limits=read(A/'pre-call-manifest.json')['design']['limits'];mods,root=load();results={};(A/'runs').mkdir();start=time.monotonic()
 for i,case in enumerate(cases):
  for arm in ARMS[i%3:]+ARMS[:i%3]:
   store,matcher,glossary=fixtures.build(A/'dataset/synthetic-sources.json');client=GeminiExperimentClient(R,A/'calls'/case['id']/arm,max_calls=limits['max_calls']);began=time.monotonic()
   try:
    p=mods['pipeline'].Pipeline(root,store,Provider(client));cls=mods['structured_navigation'].StructuredAgent if arm=='baseline' else mods[arm].RoutedAgent if arm=='controlled' else mods[arm].LegalAgent
    p.term_agent=cls(p,glossary,None,matcher,limits);out=p.run(case['question'],case['scope_document_ids'],True);p.contracts.validate(out,'urn:8-agent:term-runtime-v1','Result')
    if any(s['document_id'] not in case['scope_document_ids'] for s in out['assembly']['context']):raise ValueError('scope escape')
    rec={'case_id':case['id'],'arm_id':arm,'output':out,'downstream_contract':'PASS'}
   except Exception as e:rec={'case_id':case['id'],'arm_id':arm,'output':None,'downstream_contract':'FAIL','failure':{'type':type(e).__name__,'message':str(e)}}
   finally:store.db.close()
   rec.update(calls=client.calls,usage=client.usage,elapsed_seconds=time.monotonic()-began);new(A/'runs'/f"{case['id']}-{arm}.json",rec);results.setdefault(case['id'],{})[arm]=rec
   state=(rec.get('output') or {}).get('retrieval',{}).get('term_agent',{});print(json.dumps({'case':case['id'],'arm':arm,'status':state.get('status'),'calls':client.calls,'read':state.get('read_source_ids'),'failure':rec.get('failure') or state.get('failure')},ensure_ascii=False),flush=True)
 new(A/'results.json',{'cases':results,'elapsed_seconds':time.monotonic()-start,'main_wiring':'unchanged','gold_visible_to_product':False})
if __name__=='__main__':main()
