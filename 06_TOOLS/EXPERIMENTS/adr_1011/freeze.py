from common import *
from datetime import datetime,timezone
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
s=read(ART/'stage.json');D=ROOT/s['candidate_dir'];C=D/'snapshot'
assert not (ART/'design-freeze.json').exists()
registered={r['target_path'] for r in read(D/'candidate.json')['files']}
for name in ('05_TESTS/CONTRACTS/test_source_content_completion.py','05_TESTS/CONTRACTS/test_source_content_api.py','02_BACKEND/semantic_runtime/legal_agent/delegated_content.py','05_TESTS/CONTRACTS/test_delegated_content.py','02_BACKEND/semantic_runtime/legal_agent/content_plan.py','05_TESTS/CONTRACTS/test_content_plan.py','05_TESTS/CONTRACTS/test_content_plan_api.py','05_TESTS/CONTRACTS/test_delegation_frontier.py'):
 if name not in registered:ac.register_file(D,name,upstream_state='absent')
ac.freeze(D);assert not ac.validate(D)
cm=read(D/'candidate.json');rev=cm['revisions'][-1];m=read(ADR/'실험/manifest.json')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'candidate','arm_id':'candidate','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((D/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(D/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_1011/guard.py','runner_sha256':sha(Path(__file__).with_name('guard.py'))}])
m['dataset'].update(name='Known public capital-gains request',version='20261022-visible-connection-v1',frozen_source=str((ART/'known-request.json').relative_to(ROOT)),sha256=sha(ART/'known-request.json'),legal_version_checked=True,reference_version_checked=False,version_scope='Exact MAIN102 public corpus; known exposed source coverage targets; no approved legal-answer gold')
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
m['design']['failure_recovery']['limits']='Total native model budget14 including finalization reserve3; one repair, zero transport retries. Context menus retain whole anchor originals, page groups/other originals and report omissions; identical oversized scope is unavailable until acquired signature changes.'
save(ADR/'실험/manifest.json',m)
files={str(p.relative_to(C)):sha(p) for p in C.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
runners={str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')}
save(ART/'design-freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'design':m['design'],'manifest_sha256':sha(ADR/'실험/manifest.json'),'request_sha256':sha(ART/'known-request.json'),'offline_required_content_sha256':sha(ART/'offline-required-content.json'),'effective_candidate_override':{'candidate_navigation':{'answer_progress_control':True,'source_content_review':True,'clause_content_review':True,'content_plan_execution':True,'delegation_frontier':True,'bounded_judgment_notes':True},'max_model_attempts':14,'max_transport_retries':0},'files':{'candidate':files},'runner_hashes':runners,'client_sha256':sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py')})
print('Frozen',len(files),'files,14 calls max')
