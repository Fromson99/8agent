from common import *
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
old=ROOT/'04_EXPERIMENTS/ADR/ADR-1002-answer-progress-termination/artifacts';prior=read(old/'design-freeze.json');s=read(old/'stage.json');base=ROOT/s['roots']['candidate']
m=read(ADR/'실험/manifest.json');parent=read(old.parent/'실험/manifest.json')
m['design'].update({k:v for k,v in parent['design'].items() if k not in ('arms','code_isolation')})
m['design'].update(hypothesis='Binding termination status and next action in a single schema branch prevents contradictory ANSWERABLE+READ and NEEDS_SOURCE+FINISH from creating avoidable repair loops; preserve explicit missing-source continuation and original handoff.',primary_metric='Frozen raw-response offline replay integrity, native stop reason, call count and required source coverage.',success_criteria='All inherited and added contract checks pass; six saved stage inputs/responses revalidate against exact original and correlated contracts without another model call. One new candidate public native request returns200 within14physicalcalls, reaches income-tax97 and decree163, preserves source/hash/ACL, and ends without MODEL_DECISION_UNRESOLVED caused by status/action conflict. No legal truth or out-of-sample claim.',failure_criteria='Any source/state/ACL defect, semantic/schema repair exhaustion, premature missing-source termination, missing97/163, unfinished by14calls, or changed replay input fails criteria. First provider/transport error stops; no fallback, no adaptive rerun.',sampling='Offline replay of the six raw model replies already produced in ADR1002; these are exposed compatibility checks, not new behavior trials. One fresh candidate native run on same public question; compare historical runs descriptively only.',execution={'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'stage_probe_calls':0,'native_physical_call_ceiling':14,'max_calls_total':14,'native_profile_model_attempts':40,'max_transport_retries':0,'concurrency':1,'rss_ceiling_gib':6,'minimum_available_gib':3})
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['design']['arms'][0].update(changes='Completed ADR1002 observed responses and product snapshot',controls='Historical native result only; no new baseline model calls')
m['design']['arms'][1].update(changes='Correlated status/action schema only; saved progress state, source delivery and native budgets preserved',controls='Original source/data/model; no query/article special cases, no monitor LLM')
m['runs'][0].update(selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'native-only','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
save(ADR/'실험/manifest.json',m);save(ART/'design-before-implementation.json',{'design':m['design'],'parent_freeze_sha256':sha(old/'design-freeze.json')})
files=list(prior['files']['candidate']);existing=[n for n in files if (ROOT/n).is_file()]
D=ac.snapshot(ADR,'candidate',existing,experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001']);C=D/'snapshot'
for n in files:
 (C/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(base/n,C/n)
 if n not in existing:ac.register_file(D,n,upstream_state='absent')
save(ART/'stage.json',{'base_release':s['base_release'],'roots':{'baseline':s['roots']['baseline'],'candidate':str(C.relative_to(ROOT))},'candidate_dir':str(D.relative_to(ROOT)),'pointer_sha256':s['pointer_sha256'],'working_before':{n:sha(ROOT/n) for n in existing},'parent_artifacts':str(old.relative_to(ROOT))})
for n in ['known-request.json','stage-inputs.json','stage-gold.json']:shutil.copyfile(old/n,ART/n)
# Freeze inputs to replay before changing the candidate; output judgments never become product inputs.
save(ART/'replay-input-hashes.json',{str(p.relative_to(ROOT)):sha(p) for p in sorted((old/'paired').rglob('*.json'))})
print('Reserved isolated correlated candidate; no new model calls')
