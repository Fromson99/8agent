from common import *
from datetime import datetime,timezone
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
assert not (DES/'freeze.json').exists()
assert read(ART/'contracts-002/result.json')['status']=='PASS'
assert read(ART/'reuse-mode-contracts.json')['status']=='PASS'
meta=read(DES/'candidate.json');P=ROOT/meta['path'];ac.refresh(P);ac.freeze(P);assert not ac.validate(P),ac.validate(P)
cm=read(P/'candidate.json');rev=cm['revisions'][-1];runner=Path(__file__).with_name('e2e.py')
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'candidate','arm_id':'candidate','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((P/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(P/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner)}])
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((RUN/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
files=[*DES.glob('*.json'),ART/'offline/criteria.json',ART/'agent_layer/corrected-experiences.json',*Path(__file__).parent.glob('*.py'),ROOT/'06_TOOLS/EXPERIMENTS/resource_guard.py']
put(DES/'freeze.json',{'at':datetime.now(timezone.utc).isoformat(),'revision_sha256':rev['revision_sha256'],'candidate_manifest_sha256':sha(P/'candidate.json'),'files':{str(p.relative_to(ROOT)):sha(p) for p in files},'model_calls_at_freeze':0})
print('FROZEN',len(rev['files']),'files; same delivery and gates; assessment prompt differs')
