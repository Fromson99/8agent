"""Explicit frozen parent imports and candidate injection, never registry-discovered."""
from pathlib import Path
import hashlib,importlib.util,sys,json
from lawrag.platform.workspace import load_layout
R=load_layout().root;T=Path(__file__).parent;D=R/'04_EXPERIMENTS/ADR/ADR-0448-inherited-structure-coordinate-binding';A=D/'artifacts';C=R/'02_BACKEND/lawrag/research/candidates/adr_0448/inherited'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(frozen=True):
 p=R/'06_TOOLS/EXPERIMENTS/adr_0447/run_probe.py';record=read(R/'04_EXPERIMENTS/ADR/ADR-0447-template-bound-tool-handles/artifacts/input-lock.json');assert sha(p)==record['files'][str(p.relative_to(R))]
 spec=importlib.util.spec_from_file_location('parent447_runner',p);parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent);mods,root=parent.load();name=mods['bound'].__package__;sys.modules[name+'.baseline_bound']=mods['bound'];setattr(sys.modules[name],'baseline_bound',mods['bound'])
 path=(parent.checked_root(C) if frozen else C/'snapshot')/'02_BACKEND/semantic_runtime/inherited_navigation.py'
 spec=importlib.util.spec_from_file_location(name+'.inherited',path);module=importlib.util.module_from_spec(spec);sys.modules[name+'.inherited']=module;spec.loader.exec_module(module)
 return module,mods,root

def create_agent(pipeline,glossary,index,matcher,limits=None,*,frozen=True):
 module,_,_=load(frozen);bound=module.bind_structure(matcher,pipeline.store)
 return module.InheritedAgent(pipeline,glossary,index,bound,limits)
