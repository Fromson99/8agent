from pathlib import Path
import json,hashlib,sys,importlib.util
from lawrag.platform.workspace import load_layout
R=load_layout().root;T=Path(__file__).parent;D=R/'04_EXPERIMENTS/ADR/ADR-0451-llm-expression-mapping';A=D/'artifacts';C=R/'02_BACKEND/lawrag/research/candidates/adr_0451/mapped'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def new(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def load(frozen=True):
 p=R/'06_TOOLS/EXPERIMENTS/adr_0450/runtime.py';lock=read(R/'04_EXPERIMENTS/ADR/ADR-0450-typed-keyword-navigation/artifacts/input-lock.json');assert sha(p)==lock[str(p.relative_to(R))]
 spec=importlib.util.spec_from_file_location('parent450_runtime',p);r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r);parent,multi,mods,root=r.load();name=parent.__package__;sys.modules[name+'.baseline_typed']=parent;setattr(sys.modules[name],'baseline_typed',parent)
 path=C/'snapshot'
 if frozen:
  cm=read(C/'candidate.json');rev=cm['revisions'][-1]
  for f in rev['files']:assert sha(R/f['frozen_path'])==f['snapshot_sha256']
  path=C/'revisions'/rev['revision_id']/'snapshot'
 for module,file in [('navigation_learning','navigation_learning.py'),('mapping_base_store','learning_store.py'),('expression_mapping','expression_mapping.py'),('mapped_navigation','mapped_navigation.py')]:
  spec=importlib.util.spec_from_file_location(name+'.'+module,path/'02_BACKEND/semantic_runtime'/file);loaded=importlib.util.module_from_spec(spec);sys.modules[spec.name]=loaded;setattr(sys.modules[name],module,loaded);spec.loader.exec_module(loaded)
 return loaded,parent,multi,mods,root

def create_conversation(pipeline,glossary,index,matcher,authorized,origin_projection=None,*,ledger,actor,limits=None,frozen=True):
 mod,parent,multi,_,_=load(frozen);bound=multi.bind_structure(matcher,pipeline.store,origin_projection);bound.navigation_store=pipeline.store
 return mod.Conversation(pipeline,mod.MappedAgent(pipeline,glossary,index,bound,limits,ledger=ledger,actor=actor),authorized)
