"""Reserve externally, then bind an unchanged parent candidate and bounded recheck."""
from common import *
import shutil, sys
sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
import adr_candidate as ac
P = ROOT / '04_EXPERIMENTS/ADR/ADR-0990-bounded-expansion-retry/artifacts'
old = read(P / 'stage.json')
parent = ROOT / old['roots']['candidate']
frozen = read(P / 'design-freeze.json')['files']['candidate']
assert all(sha(parent / n) == h for n, h in frozen.items())
m = read(ADR / '실험/manifest.json')
m['design'].update(
    hypothesis='Unchanged ADR0990 candidate may answer the original question with grounded expansion under a small bounded budget; any provider error must stop further physical requests.',
    primary_metric='One native service outcome, physical model requests, source-bearing claims and actual read headings; no paired speed claim.',
    success_criteria='Service200 with source-bound article434 and both requested thresholds, original-span citation integrity, and no unrelated585/576 company-type read. At most8 physical calls, no physical call after first provider/transport failure. Integrity failures reject the run.',
    failure_criteria='Provider failure is unavailable evaluation, not an incorrect answer or latency win. Preserve budget exhaustion, partial/error outputs and unsupported claims separately. No retries or follow-up cases in this ADR.',
    criteria_frozen_before_run=True,
    sampling='Exactly the original in-sample public question. No new baseline, synthetic batch, judge, health-check or preflight model request.',
    execution={'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'max_calls_total':8,'max_calls_per_service':8,'finalization_reserve':3,'max_transport_retries':0,'wall_seconds':480,'sequential':True,'minimum_available_gib':3,'rss_ceiling_gib':6},
    failure_recovery={'owner':'Native semantic repair stays under the shared eight-call cap. Experiment transport alone records a sticky stop for every provider/transport error and denies future dispatch. Outer runner checks saved service result, not only process exit.','resume':'Existing output directory and persistent stop reject in-place reexecution. A later model retry requires a new ADR.','final_state':'Native success, partial answer, budget exhaustion or error preserved; no forced successful finish.','consumers':'Exact native service/API and audited transport outputs, final offline report.'})
m['lineage']['hypothesis_delta'] = m['design']['hypothesis']
m['design']['arms'][0].update(changes='Historical ADR0990 candidate recorded failure only; not executed again', controls='Exact immutable parent artifacts; zero new calls')
m['design']['arms'][1].update(changes='Product419files byte-identical to ADR0990 candidate. Experiment native/physical call cap8, retries0, wall480; sticky stop and result-aware runner.', controls='Same model/provider, question, permissions, source generation, source/ACL/hash/state validators; no new product review stage')
m['runs'][0].update(arm_ids=['candidate'], selection_rule=m['design']['sampling'], artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'native-service','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
save(ADR/'실험/manifest.json',m)
D=ac.snapshot(ADR,'candidate',list(frozen),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
C=D/'snapshot'
for n in frozen: shutil.copyfile(parent/n,C/n)
ac.freeze(D)
assert not ac.validate(D)
cm=read(D/'candidate.json'); rev=cm['revisions'][-1]
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'candidate','arm_id':'candidate','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((D/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(D/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0991/full_query.py','runner_sha256':sha(Path(__file__).with_name('full_query.py'))}])
shutil.copyfile(P/'known-request.json',ART/'known-request.json')
m['dataset'].update(name='Original in-sample special-resolution request',version='bounded-recheck-v1',frozen_source=str((ART/'known-request.json').relative_to(ROOT)),sha256=sha(ART/'known-request.json'),legal_version_checked=True,reference_version_checked=True,version_scope='Same immutable public corpus; no current legal advice certification')
reason='No retrieval implementation change or new recall comparison; bounded service diagnostic records actual source reads. Prior failed reference is historical, not a contemporaneous paired execution.'
m['retrieval_accounting']['not_applicable_reason']=reason
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
save(ADR/'실험/manifest.json',m)
save(ART/'stage.json',{'base_release':old['base_release'],'roots':{'candidate':str(C.relative_to(ROOT))},'candidate_dir':str(D.relative_to(ROOT)),'parent_candidate':str(parent.relative_to(ROOT)),'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
save(ART/'design-freeze.json',{'manifest_sha256':sha(ADR/'실험/manifest.json'),'design':m['design'],'request_sha256':sha(ART/'known-request.json'),'files':{'candidate':frozen},'working_files':{n:sha(ROOT/n) for n in frozen},'runner_hashes':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')},'parent_manifest_sha256':sha(P.parent/'실험/manifest.json')})
print('Frozen one question, unchanged419productfiles, maximum8physicalrequests, stop at first provider/transport error.')
