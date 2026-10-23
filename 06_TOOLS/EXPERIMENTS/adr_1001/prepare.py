"""Freeze an exact copy of selected MAIN102; never import the newer entry fix."""
from common import *
import sys, shutil
from datetime import datetime, timezone
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
assert not (ART/'design-freeze.json').exists()
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release_path=ROOT/'08_DEPLOYMENT/RELEASES/selected-connection-coverage-20261022-r1/release.json'
release=read(release_path); selected=ROOT/release['code_root']
assert pointer['release_id']==release['release_id']
assert all(sha(selected/n)==h for n,h in release['files'].items())
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1000-canonical-reference-read-coverage/artifacts'
parent=read(prior/'design-freeze.json')
files=sorted(set(parent['files']['candidate'])|set(release['files']))
working={n:sha(ROOT/n) for n in files}
tests=['05_TESTS/CONTRACTS/'+n for n in ('test_selected_connection_scope.py','test_selected_connection_scope_api.py','test_reference_endpoint_coverage.py')]
m=read(ADR/'실험/manifest.json')
m['design'].update(
 hypothesis='The selected MAIN102 canonical endpoint coverage and selected-scope connections can deliver the linked public originals without duplicate completed READ, then publish a grounded answer; measure actual phase-level model calls.',
 primary_metric='Native final answer status, linked original acquisition, exact source/ACL audit, repeated completed READ and physical call distribution.',
 success_criteria='All frozen deterministic connection-scope and native API regressions pass. One natural public question reaches income-tax97 and decree163 through valid acquired connections, does not reoffer completed READ, and publishes a source-grounded response200. All recorded original spans match source hashes and request authorization. Record every model attempt, repair, latency and usage. No legal correctness or speed improvement claim without approved gold or paired control.',
 failure_criteria='Missing linked target or final answer, repeated acquired READ, source/hash/ACL violation, or failed contracts fails the combined criteria. Provider or transport failure stops immediately with zero transport retry and no replacement run. Preserve semantic failures and usage gaps.',
 criteria_frozen_before_run=True,
 sampling='One previously exposed public capital-gains question, unchanged request and corpus; no live baseline rerun. Deterministic synthetic contracts cover direct<=5 links, larger link menu with original context, no link, lookup error, chain, exclusion, partial acquisition and resume. Known in-sample probe only.',
 execution={'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'max_calls_total':40,'max_model_attempts':40,'max_output_tokens':6400,'wall_seconds':1800,'max_transport_retries':0,'concurrency':1,'rss_ceiling_gib':6,'minimum_available_gib':3},
 failure_recovery={'owner':'Existing native stage repair; experiment sticky stop owns provider/transport failures','repair_limit':'Existing MAIN102 schema/decision repair once; no added retry','state':'Preserve raw model attempts, native journal, source and request bindings','final':'Native response/error preserved; no reconstructed answer or substituted model'},
 retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{a:[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}] for a in ('baseline','candidate')}})
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['design']['arms'][0].update(changes='Completed ADR1000 provider429 result, historical reference only',controls='No new baseline calls; no causal speed or quality comparison')
m['design']['arms'][1].update(changes='Exact selected MAIN102 release copy; observational tracing only, no product modification',controls='Same question, selected code/data, Qwen policy and native40-call capacity; transport retry disabled for provider-stop safety; fresh isolated state; request-entry working fix excluded')
m['runs'][0].update(arm_ids=['candidate'],selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
save(ADR/'실험/manifest.json',m)
save(ART/'design-before-run.json',{'design':m['design'],'release_manifest_sha256':sha(release_path),'contract_tests':tests})
D=ac.snapshot(ADR,'candidate',files,experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001']);C=D/'snapshot'
for n in release['files']:shutil.copyfile(selected/n,C/n)
assert all(sha(C/n)==h for n,h in release['files'].items())
save(ART/'stage.json',{'base_release':release,'roots':{'candidate':str(C.relative_to(ROOT))},'candidate_dir':str(D.relative_to(ROOT)),'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_before':working,'release_manifest_sha256':sha(release_path),'contract_tests':tests})
save(ART/'known-request.json',read(prior/'known-request.json'))
save(ART/'query-provenance.json',read(prior/'query-provenance.json'))
ac.freeze(D);assert not ac.validate(D)
cm=read(D/'candidate.json');rev=cm['revisions'][-1]
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'candidate','arm_id':'candidate','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((D/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(D/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_1001/guard.py','runner_sha256':sha(Path(__file__).with_name('guard.py'))}])
m['dataset'].update(name='Previously exposed public capital-gains expenses question',version='20261022-photo-transcription-v1',frozen_source=str((ART/'known-request.json').relative_to(ROOT)),sha256=sha(ART/'known-request.json'),legal_version_checked=True,reference_version_checked=False,version_scope='Exact selected MAIN102 corpus manifest; no legal-answer gold')
m['llm_policy']['llm_calls']=[{'role':'native-service','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
save(ADR/'실험/manifest.json',m)
runner_names=['common.py','guard.py','stop_policy.py','trace.py','full_query.py','run_contracts.py','analyze.py','prepare.py']
save(ART/'design-freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'manifest_sha256':sha(ADR/'실험/manifest.json'),'design':m['design'],'request_sha256':sha(ART/'known-request.json'),'files':{'candidate':{n:sha(C/n) for n in files}},'working_files':working,'runner_hashes':{str((Path(__file__).parent/n).relative_to(ROOT)):sha(Path(__file__).parent/n) for n in runner_names},'client_sha256':sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py')})
print('Frozen',len(files),'files;',len(release['files']),'selected release files exactly matched; no live calls yet')
