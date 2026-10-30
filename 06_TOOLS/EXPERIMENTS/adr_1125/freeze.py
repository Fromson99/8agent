from pathlib import Path
import json,hashlib,sys
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1125-final-disposition-shape';ART=ADR/'artifacts';C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1125/integrated-r1';S=C/'snapshot'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
new=['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('stable_references','independent_read_recovery')]
# Added helpers were registered during preparation.
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 d=read(p);files=d.get('files',{})
 if not files:continue
 if '02_BACKEND/semantic_runtime/legal_agent/read_judgment.py' in files:
  for n in new:files[n]=sha(S/n)
 for n in files:files[n]=sha(S/n)
 put(p,d)
p=S/'00_SYSTEM/PIPELINE.json';d=read(p)
for e in d['engines'].values():e['sha256']=sha(S/e['manifest'])
put(p,d)
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
ac.freeze(C);m=read(ADR/'실험/manifest.json');v=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/v['revision_id']/'snapshot';binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
put(ART/'design/freeze.json',{'code_root':str(code.relative_to(ROOT)),'binding':binding,'files':{str((ROOT/r['frozen_path']).relative_to(code)):r['snapshot_sha256'] for r in v['files']},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')},'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'inputs':{str(p.relative_to(ROOT)):sha(p) for p in (ART/'design').glob('*.json') if p.name!='freeze.json'}})
m['design']['code_isolation']['candidates']=[dict(binding,candidate_id=C.name,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001','run-002'],runner_path='06_TOOLS/EXPERIMENTS/adr_1125/check.py',runner_sha256=sha(Path(__file__).with_name('check.py')))];put(ADR/'실험/manifest.json',m)
print(code)
