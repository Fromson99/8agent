"""Bind unchanged parent code; restore normal capacity before the one native run."""
from common import *
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
P=ROOT/'04_EXPERIMENTS/ADR/ADR-0992-compact-prompts-acquired-handoff/artifacts'
s=read(P/'stage.json');B=ROOT/s['roots']['candidate']
frozen={n:h for n,h in read(P/'design-freeze.json')['files']['candidate'].items() if not n.startswith('05_TESTS/')}
assert len(frozen)==419 and all(sha(B/n)==h for n,h in frozen.items())
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis='With the previous eight-call experimental cap removed, existing post-ASSESS navigation may reconsider a material gap as unnecessary and finish instead of expanding the requested answer scope.',
 primary_metric='Actual first and subsequent navigation choices after a material ASSESS gap; reasons, source receipts, gap resolutions, native answer and stop reason.',
 success_criteria='The material expansion gap reaches a real subsequent navigation model call with capacity available. A working rejection must explicitly cancel/not pursue the unrequested all-subjects expansion (NOT_NEEDED or equivalent grounded finish) and retain source434/both thresholds. Record FINISH versus cancellation versus budget/no-progress stop separately. Do not infer successful reconsideration merely from a final200.',
 failure_criteria='If the gap triggers new subject searches/reads without rejecting the unnecessary expansion, the tested semantic safeguard fails. If no material gap occurs, classify not exercised; provider/transport failure or resource/normal40call1800s guard before the decision is unavailable. No forced gap, extra questions, model judge, fallback or whole-run retry.',
 criteria_frozen_before_run=True,sampling='Exactly the original user commercial-law special-resolution question, one candidate native execution. ADR0992 is historical reference only; no new baseline or synthetic question.',
 execution={'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'max_calls_total':40,'max_model_attempts':40,'finalization_reserve':3,'wall_seconds':1800,'max_transport_retries':0,'sequential':True,'minimum_available_gib':3,'rss_ceiling_gib':6},
 failure_recovery={'owner':'Existing native navigation/assessment repair owners unchanged. ExperimentClient alone performs transport; sticky stop on first provider/transport failure; no duplicate retries.',
 'capacity':'Restore MAIN100 model40 and wall1800 from prior experimental8/480. Keep source/ACL/hash/state checks, no-progress2, assessment reentry2 and final reserve3. This removes the small experimental cap, not all finite safeguards.',
 'state':'Fresh native request using exact same frozen request, corpus and unchanged candidate code; never alter old state/budget journals.',
 'final_state':'Record actual success, limited answer, expansion, native limit or provider error. No automatic MAIN promotion.'})
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['design']['arms'][0].update(changes='Historical ADR0992 candidate with experimental8call/480s cap; zero new baseline calls',controls='Exact immutable code/data/question/model historical reference')
m['design']['arms'][1].update(changes='Same419productfiles; experimental model/time capacity restored to MAIN100 normal40/1800 only',controls='Same question, source generation, permissions, prompts, schemas, model/provider; retries0 retained; no extra model stage')
save(ADR/'실험/manifest.json',m)
D=ac.snapshot(ADR,'candidate',list(frozen),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001']);C=D/'snapshot'
for n in frozen:shutil.copyfile(B/n,C/n)
ac.freeze(D);assert not ac.validate(D)
cm=read(D/'candidate.json');rev=cm['revisions'][-1]
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'candidate','arm_id':'candidate','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((D/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(D/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0994/guard.py','runner_sha256':sha(Path(__file__).with_name('guard.py'))}])
shutil.copyfile(P/'known-request.json',ART/'known-request.json')
m['dataset'].update(name='Original in-sample special-resolution question',version='normal-capacity-v1',frozen_source=str((ART/'known-request.json').relative_to(ROOT)),sha256=sha(ART/'known-request.json'),legal_version_checked=True,reference_version_checked=True,version_scope='Same frozen public corpus as ADR0992; behavior diagnostic, no legal-answer certification')
m['runs'][0].update(arm_ids=['candidate'],selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'native-service','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
reason='No retrieval code change or new recall comparison; exact native candidate choices and source reads recorded to diagnose the existing post-assessment decision path.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
save(ADR/'실험/manifest.json',m)
save(ART/'stage.json',{'base_release':s['base_release'],'roots':{'candidate':str(C.relative_to(ROOT))},'candidate_dir':str(D.relative_to(ROOT)),'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'parent_candidate':str(B.relative_to(ROOT))})
save(ART/'design-freeze.json',{'manifest_sha256':sha(ADR/'실험/manifest.json'),'design':m['design'],'request_sha256':sha(ART/'known-request.json'),'files':{'candidate':frozen},'working_files':{n:sha(ROOT/n) for n in frozen},'runner_hashes':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')},'parent_manifest_sha256':sha(P.parent/'실험/manifest.json')})
print('Frozen unchanged419files, one original question, normal40calls/1800seconds, no retries or extra cases.')
