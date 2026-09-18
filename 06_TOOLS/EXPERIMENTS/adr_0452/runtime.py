from pathlib import Path
import json,hashlib,importlib.util,sys
from lawrag.platform.workspace import load_layout
R=load_layout().root;T=Path(__file__).parent;D=R/'04_EXPERIMENTS/ADR/ADR-0452-gemini-expression-routing-probe';A=D/'artifacts';C=R/'02_BACKEND/lawrag/research/candidates/adr_0452/mapped';ARMS=['baseline','mapped']
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(Path(p).relative_to(R))
def new(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def load():
 p=R/'06_TOOLS/EXPERIMENTS/adr_0451/runtime.py';lock=read(R/'04_EXPERIMENTS/ADR/ADR-0451-llm-expression-mapping/artifacts/input-lock.json');assert sha(p)==lock[rel(p)]
 spec=importlib.util.spec_from_file_location('parent451_runtime',p);parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent);mod,typed,multi,mods,root=parent.load()
 cm=read(C/'candidate.json');rev=cm['revisions'][-1]
 for f in rev['files']:assert sha(R/f['frozen_path'])==f['snapshot_sha256']
 path=C/'revisions'/rev['revision_id']/'snapshot/02_BACKEND/semantic_runtime/expression_probe_binding.py';spec=importlib.util.spec_from_file_location('probe452binding',path);binding=importlib.util.module_from_spec(spec);spec.loader.exec_module(binding)
 return mod,typed,multi,mods,root,binding

def build(multi):
 import fixtures
 store,m,g=fixtures.build(A/'dataset');store.manifest['generation_id']='synthetic-expression-routing-452-v1'
 projection={**store.manifest,'documents':{}}
 for d in m.documents:
  folder='internal/hr' if d in ('pay','leave','approval') else 'internal/admin' if d in ('travel','safety','privacy') else 'kofia/규정' if d in ('customer','vendor') else 'krx/사례' if d=='archive' else None
  if folder:projection['documents'][d]={'document_id':d,'status':'verified','raw_relative_path':folder+'/'+m.documents[d]+'.html'}
 m=multi.bind_structure(m,store,projection);m.navigation_store=store;return store,m,g
