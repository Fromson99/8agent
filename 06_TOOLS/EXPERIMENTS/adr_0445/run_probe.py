"""Explicit frozen candidate injection into existing retrieve/select/assemble/answer."""
import argparse,hashlib,importlib,importlib.util,json,sys,time
from pathlib import Path
from copy import deepcopy
from lawrag.platform.workspace import load_layout
R=load_layout().root;D=R/'04_EXPERIMENTS/ADR/ADR-0445-structured-evidence-handles';A=D/'artifacts';C=R/'02_BACKEND/lawrag/research/candidates/adr_0445/structured';G=R/'01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260916-v1';ARMS=['baseline','structured']
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(Path(p).relative_to(R))
def new(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def load(frozen=True):
 cm=read(C/'candidate.json');root=C/'snapshot'
 if frozen:
  rev=cm['revisions'][-1];root=C/'revisions'/rev['revision_id']/'snapshot'
  for f in rev['files']:
   if sha(R/f['frozen_path'])!=f['snapshot_sha256']:raise ValueError('candidate code drift')
 name='probe445';spec=importlib.util.spec_from_file_location(name,root/'02_BACKEND/semantic_runtime/__init__.py',submodule_search_locations=[str(root/'02_BACKEND/semantic_runtime')]);pkg=importlib.util.module_from_spec(spec);sys.modules[name]=pkg;spec.loader.exec_module(pkg)
 return {k:importlib.import_module(name+'.'+k) for k in ['pipeline','storage','navigation_loop','navigation_agent','structured_navigation']},root
class Provider:
 def __init__(self,client):self.client=client
 def call(self,role,system,data,schema):
  value=self.client.generate(system,data,schema,phase=role);return value,self.client.usage[-1]
 def record_local(self,value):return {'kind':'local-contract','data':value}
def prepare():
 if (A/'input-lock.json').exists():raise ValueError('already sealed')
 m,root=load();cm=read(C/'candidate.json');rev=cm['revisions'][-1];manifest=read(D/'실험/manifest.json')
 manifest['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'structured','experiment_id':manifest['experiment_id'],'arm_id':'structured','run_ids':['run-001'],'manifest_path':rel(C/'candidate.json'),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':rel(__file__),'runner_sha256':sha(__file__)}])
 (D/'실험/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 paths=[R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'08_DEPLOYMENT/CONFIG/legal-source-export.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',A/'dataset/product-cases.json',A/'dataset/synthetic-sources.json',A/'authorization.json',A/'design-before-snapshot.json',A/'grading/gold.json',C/'candidate.json']
 paths += [R/'04_EXPERIMENTS/ADR/ADR-0443-structured-tool-contract-repair/artifacts/results.json',R/'04_EXPERIMENTS/ADR/ADR-0443-structured-tool-contract-repair/실험/manifest.json']
 paths+=list(Path(__file__).parent.glob('*.py'))+[R/f['frozen_path'] for f in rev['files']]+[p for p in G.rglob('*') if p.is_file()]
 lock={'files':{},'gold_visible_to_product':False}
 for p in sorted(set(paths)):lock['files'][rel(p)]=sha(p)
 new(A/'input-lock.json',lock);new(A/'pre-call-manifest.json',manifest);print('sealed inputs',len(paths),flush=True)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--prepare',action='store_true');args=ap.parse_args()
 if args.prepare:return prepare()
 if (A/'runs').exists():raise ValueError('run already started; no automatic retry')
 lock=read(A/'input-lock.json')
 for path,expected in lock['files'].items():
  if sha(R/path)!=expected:raise ValueError('input drift '+path)
 from lawrag.research.experiment_client import GeminiExperimentClient
 import fixtures
 auth=read(A/'authorization.json');cases=read(A/'dataset/product-cases.json');limits=read(A/'design-before-snapshot.json')['design']['limits']
 if not auth['authorized'] or auth['product_cases_sha256']!=sha(A/'dataset/product-cases.json'):raise ValueError('authorization drift')
 m,root=load();public_store=m['storage'].Store(G);results={};A.joinpath('runs').mkdir();began=time.monotonic()
 try:
  for number,case in enumerate(cases):
   expected=auth['synthetic_document_ids'] if case['dataset']=='synthetic' else auth['scope_document_ids']
   if sorted(case['scope_document_ids'])!=sorted(expected):raise ValueError('unauthorized document scope')
   for arm in (ARMS if number%2==0 else list(reversed(ARMS))):
    if arm=='baseline':
     import shutil
     parent=R/'04_EXPERIMENTS/ADR/ADR-0443-structured-tool-contract-repair/artifacts'
     record=deepcopy(read(parent/'results.json')['cases'][case['id']]['structured']);record['arm_id']='baseline';record['inherited_from']={'experiment_id':'ADR-0443-experiment-v1','arm_id':'structured','results_sha256':sha(parent/'results.json'),'new_model_calls':0}
     destination=A/'calls'/case['id']/'baseline';destination.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(parent/'calls'/case['id']/'structured',destination)
     new(A/'runs'/f"{case['id']}-{arm}.json",record);results.setdefault(case['id'],{})[arm]=record;continue
    client=GeminiExperimentClient(R,A/'calls'/case['id']/arm,max_calls=limits['max_calls']);start=time.monotonic();mock=None
    try:
     store=public_store
     if case['dataset']=='synthetic':mock,matcher,glossary=fixtures.build(A/'dataset/synthetic-sources.json');store=mock
     p=m['pipeline'].Pipeline(root,store,Provider(client));cfg=deepcopy(p.term_agent.config);cfg['limits']=limits;cfg['learning']={'capture':False}
     if mock:
      cls=m['navigation_loop'].NavigationAgent if arm=='baseline' else m['structured_navigation'].StructuredAgent
      p.term_agent=cls(p,glossary,None,matcher,limits)
     else:
      cls=m['navigation_agent'].ServingNavigationAgent if arm=='baseline' else m['structured_navigation'].ServingStructuredAgent
      p.term_agent=cls(p,cfg)
     out=p.run(case['question'],case['scope_document_ids'],True);p.contracts.validate(out,'urn:8-agent:term-runtime-v1','Result')
     if any(s['document_id'] not in case['scope_document_ids'] for s in out['assembly']['context']):raise ValueError('scope escape')
     record={'case_id':case['id'],'arm_id':arm,'output':out,'calls':client.calls,'usage':client.usage,'elapsed_seconds':time.monotonic()-start,'downstream_contract':'PASS'}
    except Exception as e:record={'case_id':case['id'],'arm_id':arm,'output':None,'calls':client.calls,'usage':client.usage,'elapsed_seconds':time.monotonic()-start,'downstream_contract':'FAIL','failure':{'type':type(e).__name__,'message':str(e)}}
    finally:
     if mock:mock.db.close()
    new(A/'runs'/f"{case['id']}-{arm}.json",record);results.setdefault(case['id'],{})[arm]=record;s=(record.get('output') or {}).get('retrieval',{}).get('term_agent',{})
    print(json.dumps({'case':case['id'],'arm':arm,'calls':client.calls,'status':s.get('status'),'read':s.get('read_source_ids',[]),'seconds':round(record['elapsed_seconds'],1),'failure':record.get('failure') or s.get('failure')},ensure_ascii=False),flush=True)
  for path,expected in lock['files'].items():
   if sha(R/path)!=expected:raise ValueError('input drift after execution '+path)
  new(A/'results.json',{'cases':results,'elapsed_seconds':time.monotonic()-began,'gold_visible_to_product':False,'main_wiring':'unchanged'})
 finally:public_store.close()
if __name__=='__main__':main()
