from pathlib import Path
import json,hashlib,sys,importlib.util
from lawrag.platform.workspace import load_layout
R=load_layout().root;T=Path(__file__).parent;D=R/'04_EXPERIMENTS/ADR/ADR-0450-typed-keyword-navigation';A=D/'artifacts';C=R/'02_BACKEND/lawrag/research/candidates/adr_0450/typed'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def new(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def load(frozen=True):
 p=R/'06_TOOLS/EXPERIMENTS/adr_0449/runtime.py';lock=read(R/'04_EXPERIMENTS/ADR/ADR-0449-multi-entry-catalogue-navigation/artifacts/input-lock-adapter-fix.json');assert sha(p)==lock[str(p.relative_to(R))]
 spec=importlib.util.spec_from_file_location('parent449_runtime',p);base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base);parent,_,mods,root=base.load();name=parent.__package__;sys.modules[name+'.baseline_multi']=parent;setattr(sys.modules[name],'baseline_multi',parent)
 path=C/'snapshot'
 if frozen:
  cm=read(C/'candidate.json');rev=cm['revisions'][-1]
  for f in rev['files']:assert sha(R/f['frozen_path'])==f['snapshot_sha256']
  path=C/'revisions'/rev['revision_id']/'snapshot'
 spec=importlib.util.spec_from_file_location(name+'.typed_navigation',path/'02_BACKEND/semantic_runtime/typed_navigation.py');module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);return module,parent,mods,root

def create_conversation(pipeline,glossary,index,matcher,authorized,origin_projection=None,limits=None,*,frozen=True):
 module,parent,_,_=load(frozen);bound=parent.bind_structure(matcher,pipeline.store,origin_projection)
 return module.Conversation(pipeline,module.TypedAgent(pipeline,glossary,index,bound,limits),authorized)
