from pathlib import Path
import json,hashlib,importlib.util,sys
from lawrag.platform.workspace import load_layout
R=load_layout().root;T=Path(__file__).parent;D=R/'04_EXPERIMENTS/ADR/ADR-0449-multi-entry-catalogue-navigation';A=D/'artifacts';C=R/'02_BACKEND/lawrag/research/candidates/adr_0449/multi';ARMS=['baseline','multi']
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def new(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def load(frozen=True):
 p=R/'06_TOOLS/EXPERIMENTS/adr_0448/binding_runtime.py';lock=read(R/'04_EXPERIMENTS/ADR/ADR-0448-inherited-structure-coordinate-binding/artifacts/input-lock.json');assert sha(p)==lock[str(p.relative_to(R))]
 spec=importlib.util.spec_from_file_location('parent448_runtime',p);parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent);base,mods,root=parent.load();name=base.__package__;sys.modules[name+'.baseline_inherited']=base;setattr(sys.modules[name],'baseline_inherited',base)
 path=C/'snapshot'
 if frozen:
  cm=read(C/'candidate.json');rev=cm['revisions'][-1]
  for f in rev['files']:assert sha(R/f['frozen_path'])==f['snapshot_sha256']
  path=C/'revisions'/rev['revision_id']/'snapshot'
 spec=importlib.util.spec_from_file_location(name+'.folder_navigation',path/'02_BACKEND/semantic_runtime/folder_navigation.py');folder=importlib.util.module_from_spec(spec);sys.modules[spec.name]=folder;spec.loader.exec_module(folder);setattr(sys.modules[name],"folder_navigation",folder)
 spec=importlib.util.spec_from_file_location(name+'.multi_entry',path/'02_BACKEND/semantic_runtime/multi_entry_navigation.py');multi=importlib.util.module_from_spec(spec);sys.modules[spec.name]=multi;spec.loader.exec_module(multi);return multi,base,mods,root

def create_conversation(pipeline,glossary,index,matcher,authorized,origin_projection=None,limits=None,*,frozen=True):
 """Explicit integration entrypoint, one object per authenticated conversation."""
 module,_,_,_=load(frozen);bound=module.bind_structure(matcher,pipeline.store,origin_projection)
 return module.Conversation(pipeline,module.MultiAgent(pipeline,glossary,index,bound,limits),authorized)
