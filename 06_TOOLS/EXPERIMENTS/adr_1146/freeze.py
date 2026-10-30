from pathlib import Path
import json,hashlib,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1146-source-recovery-main-qualification';D=A/'artifacts/design';T=Path(__file__).parent;C=R/'02_BACKEND/lawrag/research/candidates/adr_1146/integrated-r1';S=C/'snapshot'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for p in list(S.rglob('*.py'))+list(T.glob('*.py')):compile(p.read_text(),str(p),'exec')
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 d=read(p)
 for n in d.get('files',{}):d['files'][n]=sha(S/n)
 put(p,d)
p=S/'00_SYSTEM/PIPELINE.json';d=read(p)
for e in d['engines'].values():e['sha256']=sha(S/e['manifest'])
put(p,d)
sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac

if not read(C/'candidate.json')['revisions']:ac.freeze(C)
assert not ac.validate(C),ac.validate(C)
c=read(C/'candidate.json');v=c['revisions'][-1];code=C/'revisions'/v['revision_id']/'snapshot';files={str((R/r['frozen_path']).relative_to(code)):r['snapshot_sha256'] for r in v['files']};binding={k:x for k,x in {'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}.items()}
base=read(D/'baseline.json');serving={n:files[n] for n in set(base['manifest']['files'])|{n for n in files if n.endswith(('schema_preparation.py','stable_references.py','independent_read_recovery.py'))}};stage=A/'artifacts/staged-code'
for n,h in serving.items():p=stage/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(code/n,p)
(stage/'01_DATA').symlink_to(R/'01_DATA',target_is_directory=True)
put(D/'staging.json',{'code_root':str(stage.relative_to(R)),'files':serving,'changed':sorted(n for n,h in serving.items() if h!=base['manifest']['files'].get(n))})
m=read(A/'실험/manifest.json');m['design']['code_isolation']['candidates']=[dict(binding,candidate_id=C.name,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'],runner_path=str((T/'check_integrated_bootstrap.py').relative_to(R)),runner_sha256=sha(T/'check_integrated_bootstrap.py'))];put(A/'실험/manifest.json',m)
put(D/'freeze.json',{'code_root':str(code.relative_to(R)),'files':files,'binding':binding,'candidate':binding,'scripts':{str(p.relative_to(R)):sha(p) for p in T.glob('*.py')},'inputs':{str(p.relative_to(R)):sha(p) for p in D.glob('*.json') if p.name!='freeze.json'},'pointer_sha256':base['pointer_sha256']})
print('FROZEN',len(files),'serving',len(serving))
