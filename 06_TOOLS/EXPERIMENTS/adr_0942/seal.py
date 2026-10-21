from pathlib import Path
import hashlib,json,subprocess,sys,datetime
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0942-research-decision-closure';D=A/'artifacts/design'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0942/fixed';S=C/'snapshot'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists(),'preserve earlier freeze; changed candidate needs a new experiment after results'
new='02_BACKEND/semantic_runtime/legal_agent/research_continuity.py'
names=list(read(D/'working-before.json')['files'])
for p in (S/'02_BACKEND/workflow').rglob('manifest.json'):
    value=read(p)
    if value.get('id',value.get('workflow_id'))=='risk_team_compare_workflow':value['version']='1.19.0'
    for name in value.get('files',{}):value['files'][name]=sha(S/'02_BACKEND/workflow'/name)
    put(p,value)
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
    value=read(p)
    if not isinstance(value.get('files'),dict):continue
    if '02_BACKEND/semantic_runtime/legal_agent/request_repair.py' in value['files']:value['files'][new]=sha(S/new)
    for name in value['files']:value['files'][name]=sha(S/name)
    put(p,value)
p=S/'00_SYSTEM/PIPELINE.json';value=read(p)
for engine in value['engines'].values():
    if (S/engine['manifest']).exists():engine['sha256']=sha(S/engine['manifest'])
for workflow in value.get('workflows',{}).get('registered',[]):
    workflow['sha256']=sha(S/workflow['manifest'])
    if workflow.get('workflow_id',workflow.get('id'))=='risk_team_compare_workflow':workflow['version']='1.19.0'
put(p,value)
for cmd in ('refresh','freeze','validate'):
    done=subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py',cmd,str(C)],capture_output=True,text=True)
    assert done.returncode==0,(cmd,done.stdout,done.stderr)
rev=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
candidate={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
    'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'candidate_id':'fixed',
    'arm_id':'fixed','experiment_id':'ADR-0942-experiment-v1','run_ids':['run-001'],
    'runner_path':str((T/'run_tests.py').relative_to(R)),'runner_sha256':sha(T/'run_tests.py')}
put(D/'fixed-binding.json',{'code_root':str(code.relative_to(R)),'serving_files':{n:sha(code/n) for n in names},'candidate':candidate})
before=read(D/'working-before.json')['files']
put(D/'changes.json',[{'path':n,'before':before.get(n),'after':sha(code/n)} for n in names if before.get(n)!=sha(code/n)])
files={str((code/n).relative_to(R)):sha(code/n) for n in names}
paths=[*T.glob('*.py'),*D.glob('*.json'),*R.glob('05_TESTS/**/*.py'),*R.glob('06_TOOLS/EXPERIMENTS/adr_08*/test*.py'),*R.glob('06_TOOLS/EXPERIMENTS/adr_09*/test*.py'),R/'06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py',R/'06_TOOLS/EXPERIMENTS/resource_guard.py']
for p in paths:files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'files':files,'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[candidate]);put(A/'실험/manifest.json',m)
print('Frozen',rev['revision_id'],len(names),'files;',len(read(D/'changes.json')),'changed.')
