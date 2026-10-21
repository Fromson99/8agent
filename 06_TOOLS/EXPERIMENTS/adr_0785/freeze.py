"""Freeze the final implementation and prospective finite verification run."""
from pathlib import Path
import hashlib,json,subprocess
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0785-risk-team-compare-workflow';D=A/'artifacts/design'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0785/integrated';S=C/'snapshot'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
registered={x['target_path'] for x in read(C/'candidate.json')['files']}
new=[p for p in S.rglob('*') if p.is_file() and p.suffix in ('.py','.json') and '__pycache__' not in p.parts and str(p.relative_to(S)) not in registered]
for p in new:
 target=str(p.relative_to(S))
 subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',target,
  '--upstream-state','present' if (R/target).is_file() else 'absent'],check=True,stdout=subprocess.DEVNULL)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
cm=read(C/'candidate.json');revision=cm['revisions'][-1];code=C/'revisions'/revision['revision_id']/'snapshot'
binding={'candidate_id':'integrated','experiment_id':'ADR-0785-experiment-v1','arm_id':'workflow','run_ids':['run-001'],
 'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
 'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],
 'runner_path':'06_TOOLS/EXPERIMENTS/adr_0785/audit.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0785/audit.py')}
files={str(p.relative_to(R)):sha(p) for p in (R/'06_TOOLS/EXPERIMENTS/adr_0785').glob('*.py')}
files.update({str(p.relative_to(R)):sha(p) for p in (R/'05_TESTS').rglob('*.py')})
files.update({str(p.relative_to(R)):sha(p) for p in D.glob('*.json')})
files[str((A/'artifacts/data-staged-binding.json').relative_to(R))]=sha(A/'artifacts/data-staged-binding.json')
files.update({str((code/x['target_path']).relative_to(R)):sha(code/x['target_path']) for x in cm['files']})
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']='Introduce explicit shared workflow runtime and Risk comparison stages; verify finite safety contracts without semantic accuracy claims.'
m['design']['code_isolation']['candidates']=[binding]
for arm in m['design']['arms']:
 arm['changes']='Selected MAIN66 reference and known legacy regressions' if arm['id']=='baseline' else 'Workflow package, RAG source port, API/consumer integration and new DOCX data binding'
 arm['controls']='No external model calls; exact synthetic model responses; source, ACL, code and state hashes; MAIN pointer unchanged'
m['runs'][0].update(selection_rule='Frozen protocol suite and baseline-parity diagnostics; real DOCX source-only connection check',
 artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
put(A/'실험/manifest.json',m)
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(code.relative_to(R)),
 'candidate':binding,'files':files,'serving_files':{x['target_path']:sha(code/x['target_path']) for x in cm['files']},
 'upstream':{x['target_path']:x.get('upstream_sha256') for x in cm['files']}})
print('Frozen candidate',revision['revision_id'],'files',len(cm['files']))
