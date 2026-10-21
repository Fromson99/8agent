from pathlib import Path
import hashlib,json,subprocess,sys
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0874-bounded-followup-continuation';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0874/qualified'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
sys.path.insert(0,str(R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'));import adr_candidate;adr_candidate.refresh(C)
subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True)
cm=json.loads((C/'candidate.json').read_text());rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
tests=['06_TOOLS/EXPERIMENTS/adr_0874/test_followup.py','06_TOOLS/EXPERIMENTS/adr_0874/test_public_failure.py',
'06_TOOLS/EXPERIMENTS/adr_0844/test_sources.py','06_TOOLS/EXPERIMENTS/adr_0849/test_wiring.py','06_TOOLS/EXPERIMENTS/adr_0847',
'06_TOOLS/EXPERIMENTS/adr_0846/test_boundaries.py','06_TOOLS/EXPERIMENTS/adr_0870/test_contracts.py',
'06_TOOLS/EXPERIMENTS/adr_0870/test_exact.py','06_TOOLS/EXPERIMENTS/adr_0870/test_minimal_output.py',
'06_TOOLS/EXPERIMENTS/adr_0853/test_wire_boundaries.py','05_TESTS/CONTRACTS/test_investigation_budget_settings.py',
'05_TESTS/CONTRACTS/test_final_failure_logging.py']
hashes={}
for n in tests:
 p=R/n
 for f in p.rglob('*.py') if p.is_dir() else [p]:hashes[str(f.relative_to(R))]=sha(f)
put(D/'execution-plan.json',{'tests':tests,'test_hashes':hashes,'runner_sha256':sha(T/'run_tests.py'),'mode':'prospective finite technical contract census plus separately retained regressions; no legal quality claim'})
files={str(p.relative_to(R)):sha(p) for p in T.glob('*.py')}
files.update({str((code/x['target_path']).relative_to(R)):sha(code/x['target_path']) for x in cm['files']})
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(code.relative_to(R)),'files':files,'candidate':binding,'legal_holdout':False})
m=json.loads((A/'실험/manifest.json').read_text());m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{**binding,'candidate_id':'qualified','arm_id':'qualified','experiment_id':m['experiment_id'],'run_ids':['run-001'],'runner_path':str(T.relative_to(R)/'run_tests.py'),'runner_sha256':sha(T/'run_tests.py')}]);put(A/'실험/manifest.json',m)
print('Frozen candidate',rev['revision_id'],len(cm['files']))
