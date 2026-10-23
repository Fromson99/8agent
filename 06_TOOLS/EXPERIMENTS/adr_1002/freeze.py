from common import *
from datetime import datetime,timezone
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
s=read(ART/'stage.json');D=ROOT/s['candidate_dir'];C=D/'snapshot'
assert not (ART/'design-freeze.json').exists()
ac.freeze(D);assert not ac.validate(D)
cm=read(D/'candidate.json');rev=cm['revisions'][-1]
m=read(ADR/'실험/manifest.json')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'candidate','arm_id':'candidate','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((D/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(D/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_1002/guard.py','runner_sha256':sha(Path(__file__).with_name('guard.py'))}])
m['dataset'].update(name='Synthetic counterfactual termination pairs and known public capital-gains request',version='20261022-answer-progress-v1',frozen_source=str((ART/'stage-inputs.json').relative_to(ROOT)),sha256=sha(ART/'stage-inputs.json'),legal_version_checked=True,reference_version_checked=False,version_scope='Synthetic stage rules and exact MAIN102 corpus; no approved real legal gold')
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
save(ADR/'실험/manifest.json',m)
# Candidate manifest registers every new source and test; no unregistered product imports.
files={str(p.relative_to(C)):sha(p) for p in C.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
runners={str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')}
save(ART/'design-freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'design':m['design'],'manifest_sha256':sha(ADR/'실험/manifest.json'),'request_sha256':sha(ART/'known-request.json'),'stage_inputs_sha256':sha(ART/'stage-inputs.json'),'stage_gold_sha256':sha(ART/'stage-gold.json'),'effective_candidate_override':{'candidate_navigation':{'answer_progress_control':True},'max_transport_retries':0},'files':{'candidate':files},'runner_hashes':runners,'client_sha256':sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py')})
print('Frozen candidate',len(files),'files; paired6 + native14 physical call ceiling; no MAIN activation')
