"""Freeze the already-verified working code for one user-authorized live rerun."""
from common import *
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
assert not (ART/'stage.json').exists()
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-0998-selected-scope-connection-fallback/artifacts'
previous=read(prior/'design-freeze.json')
audit=ROOT/'09_ARTIFACTS/AUDITS/20261022-decision-original-context'
verified=read(audit/'VERIFIED_CODE.json')
assert all(sha(ROOT/n)==h for n,h in verified['files'].items())
assert sha(ROOT/'00_SYSTEM/PIPELINE.json')==verified['pipeline_sha256']
p=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
r=read(ROOT/p['manifest_path'])
assert r['data_path']==read(prior/'stage.json')['base_release']['data_path']
assert sha(ROOT/r['data_path']/'manifest.json')==r['data_manifest_sha256']
files={n:sha(ROOT/n) for n in sorted(set(previous['files']['candidate'])|set(verified['files']))}
m=read(ADR/'실험/manifest.json')
m['design'].update(
 hypothesis='Showing up to five exact-scope links inline and preserving acquired original text, request, and completed-link history at decisions will permit direct linked reads and avoid the prior needless return after reading decree163.',
 primary_metric='Observed route choices, actual original body delivery, repeated no-new-evidence exploration, native published answer, source/ACL/hash integrity.',
 success_criteria='One unmodified original question completes with a published response; exact92 paragraph2 item1 inline97 connection is available and selected without coordinate search when this scope is reached; after163 is acquired, later navigation/reference decisions receive its original or explicit budget omission with reopening; no needless repeated97 exploration after acquired163. Every collected source span and grant validates. These are trace criteria, not approved legal-answer correctness.',
 failure_criteria='Record any missing expected context, unnecessary repeated exploration, skipped direct link, native failure, or integrity failure. Do not tune candidate, change budgets, or rerun whole question after results. Provider/transport failure immediately stops this run with preserved artifacts.',
 criteria_frozen_before_run=True,
 sampling='One known photo-transcribed question once through frozen service/API code. No legal coordinate or answer injection. Prior ADR0998 candidate is historical reference only, not reexecuted or a controlled paired performance estimate.',
 execution={'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'max_calls_total':40,'max_model_attempts':40,'max_output_tokens':6400,'wall_seconds':1800,'max_transport_retries':0,'concurrency':1,'rss_ceiling_gib':6,'minimum_available_gib':3},
 failure_recovery={'owner':'Existing native stage/gateway only; no new product recovery or query retry','integrity':'Propagate ACL/hash/state mismatch; no fallback success','provider':'Sticky experiment stop, zero transport retry','budget':'Preserve existing request deadline, correction and no-progress limits','native_failure':'Record limited/failed state and available originals; do not synthesize a successful answer'},
 prior_contract_audit={'path':str(audit.relative_to(ROOT)),'verified_code_sha256':sha(audit/'VERIFIED_CODE.json'),'validation_sha256':sha(audit/'VALIDATION.json'),'ordinary_contract_work_completed_before_this_experiment':True},
 retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{a:[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}] for a in ['baseline','candidate']}})
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['design']['arms'][0].update(changes='Completed ADR0998 candidate historical trace only; zero baseline rerun',controls='Same original request, corpus, model policy and budgets; no paired causal performance claim')
m['design']['arms'][1].update(changes='Current verified working code: inline small link menu, all acquired originals in reference decisions, correct already-read flags, retained-original visibility and completed-link history',controls='No new runtime edits in this ADR; same source corpus and grants/model/budgets as prior; exact snapshot/pins')
save(ADR/'실험/manifest.json',m)
save(ART/'design-before-snapshot.json',{'design':m['design'],'manifest_sha256':sha(ADR/'실험/manifest.json')})
D=ac.snapshot(ADR,'candidate',list(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
save(ART/'stage.json',{'base_release':r,'roots':{'candidate':str((D/'snapshot').relative_to(ROOT))},'candidate_dir':str(D.relative_to(ROOT)),'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_before':files})
save(ART/'working-diff-from-parent.json',{'changed':[{ 'path':n,'parent_sha256':previous['files']['candidate'].get(n),'current_sha256':h} for n,h in files.items() if previous['files']['candidate'].get(n)!=h]})
print('Prepared',len(files),'files; model calls 0')
