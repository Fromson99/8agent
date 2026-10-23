"""One prospective actual-service probe of the already integrated ADR1031 code."""
from common import *
from copy import deepcopy
import sys, shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1031-small-connections-parent-context'
historical=ROOT/'04_EXPERIMENTS/ADR/ADR-1030-first-required-read-before-stop'
pm=read(parent/'실험/manifest.json'); pf=read(parent/'artifacts/design-rev-005.json')
hm=read(historical/'실험/manifest.json'); hs=read(historical/'artifacts/stage.json')
assert pm['reservation']['status']=='completed' and pm['results']['status']=='complete'
assert all(sha(ROOT/n)==h for n,h in pf['files'].items())
m=read(ADR/'실험/manifest.json'); d=m['design']
d.update(
 hypothesis='The integrated ADR1031 implementation can acquire and deliver small selected-scope connections in the actual question flow, including only ancestor own wording, without another model choice or repeated directory traversal.',
 primary_metric='Actual delegated original acquisition and model delivery, automatic-read boundary and repeated-directory audit, with calls/tokens/latency reported.',
 success_criteria='The same known question completes an answer and acquires and delivers the delegated original (observed target: decree163); any encountered complete directory with <=2 unique resolved endpoints reads them once within existing budgets, >2 remains menu-only, no recursive auto-read or sibling contamination, no dedicated auto-read model call, no duplicate equivalent directories, and zero source/hash/ACL violations. Maximum14 physical calls/1800s. Unexercised boundary cases remain unverified in this live run, backed only by parent contracts.',
 failure_criteria='Delegated original not reached or not delivered, request failure, duplicate equivalent directory, auto-read outside threshold/budgets/scope, added automatic model call, source/hash/ACL violation, or native bounded termination without the required original. Provider429/transport failure ends the run without retry and is not semantic failure proof.',
 criteria_frozen_before_run=True,
 retrieval_stage_plan=deepcopy(hm['design']['retrieval_stage_plan']),
 sampling='One unchanged exposed public capital-gains question; candidate only. ADR1031 complete contract-tested parent. ADR1030 is historical context, not paired: answer_progress_control was true there and is false in the current working profile. No gold/target injected into product, no judge call, no adaptive rerun.',
 failure_recovery=deepcopy(pm['design']['failure_recovery']),
 budgets={'per_arm_calls':14,'total_calls':14,'wall_seconds':1800,'rss_limit_gib':6,'minimum_available_gib':4},
 working_integration='No product edits: exact507 integrated working files equal ADR1031 rev005 before and after run; isolated candidate and runtime only. Selected MAIN102 and GENOS unchanged.',
 historical_comparison={'adr1030_calls':6,'adr1030_input_tokens':145695,'paired':False,'profile_difference':'answer_progress_control true in ADR1030, absent/default false here; small_connection_context true here.'})
d['failure_recovery']['live_limits']='14 physical calls/1800s; provider/transport retries0 and sticky stop; existing schema repair only; single process RSS6GiB, minimum available4GiB. Preserve failures/evidence; no new retry owner.'
d['arms'][0].update(changes='Complete ADR1031 implementation and48 candidate/29 working contracts; no baseline model call in this probe.',controls='Exact same working code/profile/data as frozen candidate; historical ADR1030 unpaired only.')
d['arms'][1].update(changes='No implementation change. Execute the integrated small_connection_context=true working profile through service.py; answer_progress_control defaults false.',controls='Unchanged known request,65 public documents, Qwen3.8/ParasailFP8/reasoningnone/no fallback;14calls/1800s.')
m['lineage']['hypothesis_delta']='Actual-question probe of exact integrated parent code and settings; no new product implementation.'
m['llm_policy']=deepcopy(hm['llm_policy'])
m['retrieval_accounting']=deepcopy(hm['retrieval_accounting'])
for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]='PENDING_MEASUREMENT'
m['runs'][0].update(arm_ids=['candidate'],selection_rule=d['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
save(ADR/'실험/manifest.json',m)
files=sorted(pf['files'])
candidate_dir=ac.snapshot(ADR,'candidate',files,experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
c=candidate_dir/'snapshot'
assert all(sha(c/n)==h for n,h in pf['files'].items())
shutil.copyfile(historical/'artifacts/known-request.json',ART/'known-request.json')
save(ART/'stage.json',{'base_release':hs['base_release'],'roots':{'candidate':str(c.relative_to(ROOT))},'candidate_dirs':{'candidate':str(candidate_dir.relative_to(ROOT))},'working_before':pf['files'],'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'arm_order':['candidate'],'parent':str(parent.relative_to(ROOT)),'same_parent_files':len(files),'parent_revision':'rev-005'})
save(ART/'design-before-snapshot.json',d)
print('Prepared exact working/parent candidate',len(files),'files; no product change')
