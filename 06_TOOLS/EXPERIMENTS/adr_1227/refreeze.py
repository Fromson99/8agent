from pathlib import Path
import json,sys,hashlib,ast
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1227-source-first-authoring-semantics';D=ADR/'artifacts/design'
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1227/source-first';S=C/'snapshot'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
files=read(D/'freeze.json')['product_changes'];changes={n:sha(S/n) for n in files}
for n in files:ast.parse((S/n).read_text())
hashes={}
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if not set(files)&set(v.get('files',{})):continue
 before=sha(p);v['files'].update(changes);put(p,v);hashes[before]=sha(p)
p=S/'00_SYSTEM/PIPELINE.json';text=p.read_text()
for before,after in hashes.items():text=text.replace(before,after)
p.write_text(text)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.freeze(C);assert not ac.validate(C)
v=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/v['revision_id']/'snapshot'
binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
f={'code_root':str(code.relative_to(ROOT)),'files':{str((ROOT/x['frozen_path']).relative_to(code)):x['snapshot_sha256'] for x in v['files']},'candidate_revision':binding,'product_changes':changes}
out=D/('freeze-'+v['revision_id']+'.json');assert not out.exists();put(out,f);put(D/'freeze-current.json',f)
m=read(ADR/'실험/manifest.json');m['design']['code_isolation']['candidates']=[dict(binding,candidate_id='source-first',experiment_id=m['experiment_id'],arm_id='source-first',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'check.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'check.py'))];put(ADR/'실험/manifest.json',m)
print(v['revision_id'])
