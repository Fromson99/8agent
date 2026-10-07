"""Correct a preflight data binding using byte-equivalent indexed source rows; no model calls."""
from pathlib import Path
import json,hashlib,sqlite3,shutil,os,unicodedata
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0523-gemma-scoped-exploration-probe'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,v):
 if p.exists():p.unlink() # copied generations use immutable hard links
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(A/'artifacts/frozen-design.json');old=R/f['generations']['baseline'];parent=R/f['generations']['guarded']
def fingerprint(g):
 h=hashlib.sha256();n=0
 db=sqlite3.connect('file:'+str(g/'navigation/navigation.sqlite')+'?mode=ro',uri=True)
 for sid,raw in db.execute('SELECT id,json FROM source ORDER BY id'):
  row=json.loads(raw);v=[sid,unicodedata.normalize('NFKC',row.get('heading') or ''),unicodedata.normalize('NFKC',row.get('text') or '')];h.update(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode());h.update(b'\n');n+=1
 db.close();return {'source_rows':n,'indexed_inputs_sha256':h.hexdigest()}
before=fingerprint(old);after=fingerprint(parent);assert before==after
new=R/'01_DATA/TERM_RELEASES/adr0523-gemma-bound-fulltext-v1/generation';new.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(parent,new,copy_function=os.link)
fm=read(new/'fulltext/manifest.json');fm.update(navigation_index_sha256=read(new/'navigation/manifest.json')['index_sha256'],rebound_from_manifest_sha256=sha(parent/'fulltext/manifest.json'),rebind_basis={'indexed_source_rows_identical':before,'operation':'metadata rebind; FTS binary and tokenizer unchanged'})
write(new/'fulltext/manifest.json',fm)
code=A/'artifacts/runtime-guarded';shutil.copytree(R/f['runtime_roots']['guarded'],code,ignore=shutil.ignore_patterns('__pycache__'))
pipeline=read(code/'00_SYSTEM/PIPELINE.json');changed=[]
def visit(v):
 if isinstance(v,list):
  for x in v:visit(x)
 elif isinstance(v,dict):
  if isinstance(v.get('fulltext'),dict):
   v['fulltext'].update(navigation_index_sha256=fm['navigation_index_sha256'],manifest_sha256=sha(new/'fulltext/manifest.json'));changed.append(v['fulltext'])
  for x in v.values():visit(x)
visit(pipeline);write(code/'00_SYSTEM/PIPELINE.json',pipeline)
write(R/'02_BACKEND/lawrag/research/candidates/adr_0523/transport/snapshot/00_SYSTEM/PIPELINE.json',pipeline)
write(A/'artifacts/fulltext-rebinding.json',{'preflight_only':True,'model_calls_before_change':0,'baseline_index_inputs':before,'candidate_index_inputs':after,'generation':str(new.relative_to(R)),'code_root':str(code.relative_to(R)),'fulltext_binary_unchanged':True,'updated_profile_bindings':len(changed),'parent_generation':str(parent.relative_to(R))})
print('Verified identical FTS inputs',before,'new generation',new,flush=True)
