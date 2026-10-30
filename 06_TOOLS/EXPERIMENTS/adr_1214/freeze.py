from pathlib import Path
import json,sys,hashlib
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1214-gold-main120-engine-implementation';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
S=R/read(D/'candidate.json')['root'];known={x.get('target_path',x.get('upstream_path')) for x in read(S/'candidate.json')['files']}
for p in (S/'snapshot/08_DEPLOYMENT/LOCAL/gold_connection_r12').glob('*.py'):
 n=str(p.relative_to(S/'snapshot'))
 if n not in known:ac.register_file(S,n,upstream_state='absent')
ac.freeze(S);assert not ac.validate(S),ac.validate(S);v=read(S/'candidate.json')['revisions'][-1];C=S/'revisions'/v['revision_id']/'snapshot'
binding={'candidate_id':'connected','experiment_id':read(A/'실험/manifest.json')['experiment_id'],'arm_id':'connected','run_ids':['run-001'],'manifest_path':str((S/'candidate.json').relative_to(R)),'manifest_sha256':sha(S/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_1214/run.py','runner_sha256':sha(Path(__file__).with_name('run.py'))}
files=list(C.rglob('*.py'))+[p for p in D.glob('*.json') if not p.name.startswith('freeze')]+list((R/'02_BACKEND/lawrag/pipeline').glob('oracle*.py'))+[Path(__file__).with_name('run.py'),A/'artifacts/term-scope/selection.json']
f={**binding,'files':{str(p.relative_to(R)):sha(p) for p in files},'entries':{p.stem.removeprefix('engine_'):str(p.relative_to(R)) for p in C.rglob('engine_*.py')}}
put(D/'freeze.json',f);put(D/('freeze-'+v['revision_id']+'.json'),f)
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[binding]);put(A/'실험/manifest.json',m);print(v['revision_id'])
