from pathlib import Path
import json,hashlib
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0848-minimal-model-output';D=A/'artifacts/design'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0848/compact'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
cm=read(C/'candidate.json');rev=cm['revisions'][-1];S=C/'revisions'/rev['revision_id']/'snapshot'
binding={'candidate_id':'compact','arm_id':'compact','experiment_id':'ADR-0848-experiment-v1','run_ids':['run-001'],
 'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
 'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
 'runner_path':'06_TOOLS/EXPERIMENTS/adr_0848/run_tests.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0848/run_tests.py')}
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[binding])
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['llm_policy']['llm_calls']=[]
m['design']['technical_qualification_only']=True
put(A/'실험/manifest.json',m)
files={str(p.relative_to(R)):sha(p) for p in (R/'06_TOOLS/EXPERIMENTS/adr_0848').glob('*.py')}
files.update({str((S/x['target_path']).relative_to(R)):sha(S/x['target_path']) for x in cm['files']})
for p in list(D.glob('*.json'))+[C/'candidate.json']:
 files[str(p.relative_to(R))]=sha(p)
for p in (R/'05_TESTS').rglob('*.py'):files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(S.relative_to(R)),
 'files':files,'candidate':binding,'real_model_calls':0,'main_unchanged':True})
print('Frozen explicit candidate and prospective technical tests')
