from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0787-risk-compare-qwen-connected';D=A/'artifacts/design'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0787/qwen'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
binding={'candidate_id':'qwen','experiment_id':'ADR-0787-experiment-v1','arm_id':'qwen','run_ids':['run-001'],
 'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
 'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
 'runner_path':'06_TOOLS/EXPERIMENTS/adr_0787/run.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0787/run.py')}
files={str(p.relative_to(R)):sha(p) for p in Path(__file__).parent.glob('*.py')}
files.update({str(p.relative_to(R)):sha(p) for p in D.glob('*.json')})
files.update({str((code/x['target_path']).relative_to(R)):sha(code/x['target_path']) for x in cm['files']})
for n in ('02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/experiment_policy.py','00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','06_TOOLS/EXPERIMENTS/adr_0785/run_tests.py','05_TESTS/CONTRACTS/test_risk_team_compare_workflow.py','05_TESTS/CONTRACTS/test_risk_team_compare_workflow_v6.py'):
 if (R/n).is_file():files[n]=sha(R/n)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']='Replace no-call mock validation with user-authorized real Qwen workflow execution on actual registered sources; original question with gold offline.'
m['design']['code_isolation']['candidates']=[binding]
m['runs'][0].update(selection_rule='One original user liquidity question, once per arm; gold offline; no adaptive retry after result.',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
put(A/'실험/manifest.json',m)
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(code.relative_to(R)),
 'candidate':binding,'files':files,'serving_files':{x['target_path']:sha(code/x['target_path']) for x in cm['files']}})
print('Frozen',rev['revision_id'],len(cm['files']),'serving files')
