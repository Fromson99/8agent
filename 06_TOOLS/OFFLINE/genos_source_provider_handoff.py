"""Reproducible editor R2, preserving R1 transport and accepted judgment cards."""
import ast,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'08_DEPLOYMENT/GENOS/handoffs/workflow_source_cards_20261013_r1/GENOS_WORKFLOW_SOURCE_CARDS_20261013_R1_PASTE_ALL.txt'
BASE_SHA='e6b1a351131b6956950c88c617c76b4b32865d391745c952522c779022704e8e'
DEST=ROOT/'08_DEPLOYMENT/GENOS/handoffs/workflow_source_provider_20261013_r2'
NAME='GENOS_WORKFLOW_SOURCE_PROVIDER_20261013_R2_PASTE_ALL.txt'
METHODS=('_source_label','_card_rationale','_flush_source_candidates','_append_source_card','_flush_source_reads','_source_progress')
def extract(text,names,cls=None):
 tree=ast.parse(text);nodes=tree.body
 if cls:nodes=next(n for n in nodes if isinstance(n,ast.ClassDef) and n.name==cls).body
 lines=text.splitlines(keepends=True)
 return {n.name:''.join(lines[min([n.lineno]+[d.lineno for d in n.decorator_list])-1:n.end_lineno]) for n in nodes if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names}
def replace_function(text,name,new,cls=None):
 old=extract(text,[name],cls)[name];assert text.count(old)==1;return text.replace(old,new,1)
def build(source):
 text=BASE.read_text();assert hashlib.sha256(BASE.read_bytes()).hexdigest()==BASE_SHA
 current=Path(source).read_text();methods=extract(current,METHODS,'_ChatProgress')
 for name in METHODS:
  if name in extract(text,[name],'_ChatProgress'):text=replace_function(text,name,methods[name],'_ChatProgress')
  else:text=text.replace('    def _card_rationale(',methods[name]+'\n\n    def _card_rationale(',1)
 text=text.replace('        self.source_read_rows = []\n','        self.source_candidate_rows = []\n        self.source_candidate_context = None\n        self.source_candidate_label = ""\n        self.source_read_rows = []\n',1)
 text=text.replace('    async def progress(self, event):\n','    async def progress(self, event):\n        event = public_event(event)\n        if event is None:\n            return\n',1)
 public=extract(current,('public_event','public_failure','render_error'))
 text=replace_function(text,'render_error',public['render_error'])
 text=text.replace('def render_error(',"DISPLAY_POLICY_REVISION = 'public-display-v2'\n\n\n"+public['public_failure']+'\n\n\n'+public['public_event']+'\n\n\ndef render_error(',1)
 text=text.replace('source-cards-20261013-r1','source-provider-20261013-r2')
 compile(text,NAME,'exec');return text,methods
if __name__=='__main__':
 source=Path(sys.argv[1]);text,methods=build(source);DEST.mkdir(exist_ok=True)
 path=DEST/NAME;assert not path.exists() or path.read_text()==text;path.write_text(text)
 manifest={'purpose':'existing-workflow-python-editor-only','base_path':str(BASE.relative_to(ROOT)),'base_sha256':BASE_SHA,'editor_file':NAME,'editor_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'shared_source_path':str(source.relative_to(ROOT)),'shared_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'shared_methods_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in methods.items()},'diagnostic_storage':'Existing backend journal/request logs unchanged','grouping_basis':'contiguous source notifications with request/run/result boundary; not a model call count','model_calls':0,'backend_modified_by_delivery':False,'data_generation_modified_by_delivery':False,'field_workflow_pasted':False,'field_workflow_test':'NOT_RUN','field_code_serving_revision':None,'field_generation':None}
 (DEST/'CODE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print(path.relative_to(ROOT))
