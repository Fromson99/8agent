from common import *
import sys, shutil
from copy import deepcopy
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1018-complete-connection-directory'
pm=read(prior/'실험/manifest.json'); pf=read(prior/'artifacts/design-freeze.json'); ps=read(prior/'artifacts/stage.json')
m=read(ADR/'실험/manifest.json')
m['design']=deepcopy(pm['design'])
m['design'].update(hypothesis='Expose the complete selected-scope directory directly to parent read selection without a nested model decision. Bound assessment commentary and terminate length-truncated review with verified source excerpts, preserving failure and no legal conclusion.',
 primary_metric='Zero nested reference model calls; actual question reaches linked originals and publishes a bounded outcome without retrying length-truncated review.',
 success_criteria='Synthetic actual API exposes late targets for the exact selected scope without nested reference calls; acquired spans and ACL/hash/replay remain verified. Length-truncated assessment causes one failed assessment attempt, zero repair or composition calls, source-only LIMITED_ANSWER with INSUFFICIENT coverage and durable duplicate/restart reuse. Other schema errors retain bounded repair. Known public question executed once <=14 physical calls; full legal answer success and bounded source-only outcome reported separately.',
 failure_criteria='Hidden or forced reference choice; lost originals or source witnesses; source-only reply marked legally complete; invalid identifiers, authorization, hashes or stale state accepted; spent budget reset; length-truncated review retried; missing output failure audit.',
 sampling='Synthetic failure-injection contracts and parent response classification; then one known exposed public question, historical ADR1018 control, no adaptive rerun or fallback.',
 failure_recovery={'owner':'existing completion assessment owner; gateway labels typed finish reason only','limits':'14 physical calls, transport retries0, wall1800s; length-truncated assessment is not retried; other output errors retain at most1 repair','state':'Failed raw response and source evidence remain durable. Only exact verified excerpts are published when review truncates; no claim inferred from partial JSON.'},
 working_integration='Integrate only verified changed modules with compare-and-swap against snapshot upstream hashes; preserve unrelated work and MAIN102 pointer. Probe does not certify legal quality.')
m['design']['arms'][0].update(changes='Historical ADR1018 exact candidate and native record; no new control calls.',controls='Same data/question/model; historical unpaired run.')
m['design']['arms'][1].update(changes='Direct complete selected connection cards; bounded assessment reasons; typed length failure source-only termination.',controls='Same model/data/question; no article-specific rule, no increased budgets.')
m['design']['code_isolation']['candidates']=[]
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['runs'][0].update(arm_ids=['candidate'],selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']=deepcopy(pm['llm_policy']);m['retrieval_accounting']=deepcopy(pm['retrieval_accounting'])
for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]='PENDING_MEASUREMENT'
save(ADR/'실험/manifest.json',m);save(ART/'design-before-snapshot.json',m['design'])
files=set(pf['files']['candidate'])
files.update(['05_TESTS/CONTRACTS/test_assessment_source_reply.py','05_TESTS/CONTRACTS/test_bounded_source_main.py','05_TESTS/CONTRACTS/test_bounded_delivered_handoff.py'])
d=ac.snapshot(ADR,'candidate',sorted(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
shutil.copyfile(prior/'artifacts/known-request.json',ART/'known-request.json')
save(ART/'stage.json',{'base_release':ps['base_release'],'roots':{'candidate':str((d/'snapshot').relative_to(ROOT))},'candidate_dirs':{'candidate':str(d.relative_to(ROOT))},'working_before':{n:sha(ROOT/n) for n in files},'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'arm_order':['candidate'],'parent':str(prior.relative_to(ROOT))})
print(d/'snapshot')
