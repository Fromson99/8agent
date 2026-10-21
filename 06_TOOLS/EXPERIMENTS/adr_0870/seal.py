from pathlib import Path
import hashlib,json,subprocess,sys
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0870-host-owned-enum-contract';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0870/qualified'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
sys.path.insert(0,str(R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'));import adr_candidate;adr_candidate.refresh(C)
subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True)
cm=json.loads((C/'candidate.json').read_text());rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
old=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0853-basis-wire-integration/artifacts/design/execution-plan.json').read_text())
tests=[str(T.relative_to(R)/'test_contracts.py'),str(T.relative_to(R)/'test_exact.py'),str(T.relative_to(R)/'test_catalogue.py'),'05_TESTS/CONTRACTS/test_pipeline_unit_fulltext.py',str(T.relative_to(R)/'test_adaptive_pinned.py'),'05_TESTS/CONTRACTS/test_fulltext_location_metadata.py','05_TESTS/CONTRACTS/test_law_navigation_state_contract_adr0661.py','05_TESTS/CONTRACTS/test_genos_output_unlimited.py','05_TESTS/CONTRACTS/test_investigation_budget_settings.py']+[t.replace('06_TOOLS/EXPERIMENTS/adr_0848/test_minimal_output.py',str(T.relative_to(R)/'test_minimal_output.py')) for t in old['tests']]
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
