from common import *
import sys
from datetime import datetime,timezone
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
assert not (ART/'design-freeze.json').exists()
s=read(ART/'stage.json');D=ROOT/s['candidate_dir'];C=D/'snapshot'
request=read(ROOT/'04_EXPERIMENTS/ADR/ADR-0999-original-context-inline-live-rerun/artifacts/known-request.json')
save(ART/'known-request.json',request)
save(ART/'query-provenance.json',read(ROOT/'04_EXPERIMENTS/ADR/ADR-0999-original-context-inline-live-rerun/artifacts/query-provenance.json'))
ac.freeze(D);assert not ac.validate(D)
cm=read(D/'candidate.json');rev=cm['revisions'][-1]
files={str(p.relative_to(C)):sha(p) for p in C.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
m=read(ADR/'실험/manifest.json')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'candidate','arm_id':'candidate','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((D/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(D/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_1000/guard.py','runner_sha256':sha(Path(__file__).with_name('guard.py'))}])
m['dataset'].update(name='Photo-derived capital-gains expenses question',version='20261022-photo-transcription-v1',frozen_source=str((ART/'known-request.json').relative_to(ROOT)),sha256=sha(ART/'known-request.json'),legal_version_checked=True,reference_version_checked=False,version_scope='Same selected corpus as ADR0999; no approved legal-answer gold')
m['llm_policy']['llm_calls']=[{'role':'native-service','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(arm_ids=['candidate'],selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
save(ADR/'실험/manifest.json',m)
save(ART/'design-freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'manifest_sha256':sha(ADR/'실험/manifest.json'),'design':m['design'],'request_sha256':sha(ART/'known-request.json'),'files':{'candidate':files},'working_files':s['working_before'],'runner_hashes':{str((Path(__file__).parent/n).relative_to(ROOT)):sha(Path(__file__).parent/n) for n in ['common.py','guard.py','stop_policy.py','trace.py','full_query.py']},'client_sha256':sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py')})
print('Frozen',len(files),'files; one real query; zero calls yet')
