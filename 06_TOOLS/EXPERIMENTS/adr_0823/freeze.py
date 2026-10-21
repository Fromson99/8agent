from pathlib import Path
import json,hashlib,shutil
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0823-comparison-partial-qualification';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0823/connected';T=Path(__file__).parent
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
# Pin the already-debugged execution harness, model fixture and actual service adapter.
for name in ('run_tests.py','consumer_check.py','test_tasks.py'):
 s=(R/('06_TOOLS/EXPERIMENTS/adr_0819' if name=='consumer_check.py' else '06_TOOLS/EXPERIMENTS/adr_0822')/name).read_text()
 if name=='consumer_check.py':s=s.replace('ADR-0819-comparison-task-qualification','ADR-0823-comparison-partial-qualification').replace('adr0818-consumer-','adr0819-consumer-')
 if name=='run_tests.py':s=s.replace('adr_0822/connected','adr_0823/connected').replace("str(R/'06_TOOLS/EXPERIMENTS/adr_0822')","str(R/'06_TOOLS/EXPERIMENTS/adr_0823')")
 (T/name).write_text(s)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];binding=read(D/'verification-binding.json');code=R/binding['code_root']
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',production_paths_modified_before_decision=False,runtime_import_allowed=False,production_registry_registered=False,main_wiring_unchanged=True,candidates=[{
 'candidate_id':'connected','arm_id':'connected','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str((T/'matrix.py').relative_to(R)),'runner_sha256':sha(T/'matrix.py')}]);put(A/'실험/manifest.json',m)
paths=list(T.glob('*.py'))+list(D.glob('*.json'))+[C/'candidate.json']+list((R/'05_TESTS').rglob('*.py'))+list((R/'06_TOOLS/EXPERIMENTS/adr_0811').glob('*.py'))
put(D/'freeze.json',{**binding,'frozen_at':datetime.now(timezone.utc).isoformat(),'files':{str(p.relative_to(R)):sha(p) for p in paths},'inherited_code_sha256':read(R/'04_EXPERIMENTS/ADR/ADR-0822-comparison-partial-item-preservation/artifacts/run-001/result.json')['revision_sha256']})
print('Frozen154 cases,342 serving files and exact runners')
