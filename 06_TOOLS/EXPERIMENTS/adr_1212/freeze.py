from pathlib import Path
import hashlib,json,sys
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1212-gold-main120-engine-check';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
S=R/read(D/'candidate.json')['root'];target='08_DEPLOYMENT/LOCAL/gold_connection_r12/engine_probe.py'
if target not in [x.get('target_path',x.get('upstream_path')) for x in read(S/'candidate.json')['files']]:ac.register_file(S,target,upstream_state='absent')
ac.freeze(S);assert not ac.validate(S),ac.validate(S)
v=read(S/'candidate.json')['revisions'][-1];C=S/'revisions'/v['revision_id']/'snapshot'
files=[p for p in D.glob('*.json') if not p.name.startswith('freeze')]
files+=[p for p in C.rglob('*') if p.is_file()]
files+=[Path(__file__).with_name('run.py')]
binding={'candidate_id':'gold-engine','experiment_id':read(A/'실험/manifest.json')['experiment_id'],'arm_id':'gold-engine','run_ids':['run-001'],'manifest_path':str((S/'candidate.json').relative_to(R)),'manifest_sha256':sha(S/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256'],'runner_path':str(Path(__file__).with_name('run.py').relative_to(R)),'runner_sha256':sha(Path(__file__).with_name('run.py'))}
f={'entry':str((C/target).relative_to(R)),'files':{str(p.relative_to(R)):sha(p) for p in files},**binding}
put(D/'freeze.json',f);put(D/('freeze-'+v['revision_id']+'.json'),f)
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[binding]);put(A/'실험/manifest.json',m)
print('Frozen',v['revision_id'])
