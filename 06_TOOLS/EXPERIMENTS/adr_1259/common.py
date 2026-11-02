from pathlib import Path
import sys,json,hashlib,importlib.util,os,gzip,time
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1259-wiki-typed-proposal-oracle-live';D=A/'artifacts/design';O=A/'artifacts/run-001';T=Path(__file__).resolve().parent
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')
def raw(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with gzip.open(p,'wb') as z:z.write(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str).encode())
 put(str(p)+'.ref.json',{'sha256':sha(p),'bytes':p.stat().st_size,'encoding':'gzip/json'})
def module(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m

def frozen_gold():
 f=read(D/'freeze.json');C=R/f['code_root']
 for n,h in f['files'].items():assert sha(C/n)==h,n
 for n,h in f['inputs'].items():assert sha(R/n)==h,n
 for n,h in f['scripts'].items():assert sha(R/n)==h,n
 import importlib.abc
 class ExactImports(importlib.abc.MetaPathFinder):
  def find_spec(self,fullname,path=None,target=None):
   paths={'lawrag.research':R/'02_BACKEND/lawrag/research/__init__.py','lawrag.research.experiment_client':R/'02_BACKEND/lawrag/research/experiment_client.py','lawrag.research.openrouter_legal_adapter':R/'02_BACKEND/lawrag/research/openrouter_legal_adapter.py','lawrag.core.request_deadline':C/'02_BACKEND/lawrag/core/request_deadline.py'}
   if fullname not in paths:return None
   p=paths[fullname]
   return importlib.util.spec_from_file_location(fullname,p,submodule_search_locations=[str(p.parent)] if p.name=='__init__.py' else None)
 sys.meta_path.insert(0,ExactImports())
 gold=module('workspace_candidate_gold',R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py')
 original=gold.engine_binding()
 # Explicit research binding only. No operational pointer or connector is edited,
 # and no candidate is represented as a qualified MAIN release.
 binding={**original,'engine_root':str(C.relative_to(R)),'engine_files':f['files'],
          'engine_release_id':'UNQUALIFIED_RESEARCH_ADR1259','engine_manifest_sha256':f['candidate_revision']['revision_sha256']}
 def verified():
  for n,h in f['files'].items():assert sha(C/n)==h,n
  return binding
 gold.engine_binding=verified
 return gold,C,f
