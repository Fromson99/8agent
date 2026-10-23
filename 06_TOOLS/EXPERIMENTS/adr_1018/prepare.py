from common import *
import sys,shutil
from copy import deepcopy
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1017-final-scope-provider-retest'
pm=read(prior/'실험/manifest.json');pf=read(prior/'artifacts/design-freeze.json');ps=read(prior/'artifacts/stage.json')
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis='A compact directory for the final selected source scope exposes every currently verified target before any page-by-page applicability decision. Sparse choices read only model-selected scopes. Lossless shared metadata reduces repeated navigation input without deleting originals or history.',
 primary_metric='All queued connection targets visible and selectable in the first directory; exact original/ACL/state contracts and lossless input roundtrip.',
 success_criteria='Actual recorded97-scope catalog replay includes every queued group including decree163 in the first directory, with no special article rule. A scripted actual API selects a late target and returns without deciding every unrelated group. Unselected targets remain unexamined; selected scopes/hash/ACL/budget validated before reads. Lossless expansion equals the original view; total wire bytes for recorded navigation calls2-4 decrease at least10%. Native known question attempted once, at most14 calls; provider failure leaves semantic completion unverified.',
 failure_criteria='Missing catalog target without explicit incomplete/overflow status, unexecutable offered scope, invented source or SKIP, changed original bytes, unauthorized/stale read, unread history loss, partial execution before chosen-batch budget validation, hidden provider failure, or lossless roundtrip failure.',
 sampling='Offline exact parent-record input and catalog replay plus synthetic contract/API tests; then one known exposed public question through candidate service. No live control, no adaptive rerun or fallback.',
 criteria_frozen_before_run=True,
 failure_recovery={'owner':'existing request_repair/reference bounded_decision','limits':'14 physical calls, reserve3, schema repair1, transport retries0, wall1800s; no retry after provider failure','state':'Unselected groups stay queued; exact accepted choices and reads checkpointed; stale/ACL/hash errors remain blocked.'},
 budgets={'per_arm_calls':14,'total_calls':14,'wall_seconds':1800,'rss_limit_gib':6,'minimum_available_gib':4},
 working_integration='After deterministic contracts and recorded-input checks pass, integrate only changed product modules and pins, preserving other work. Native provider failure does not certify quality or change MAIN.')
m['design']['arms'][0].update(changes='Historical frozen ADR1017 candidate with recorded catalog and exact provider inputs; no new baseline calls.')
m['design']['arms'][1].update(changes='Selected-scope compact sparse connection directory and lossless shared navigation metadata. Existing source reader, recovery owner and total budget remain.',controls='Same data, model, request and profile; no article-specific ranking or forced read.')
m['design']['retrieval_stage_plan']['stages_by_arm']={a:[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}] for a in ('baseline','candidate')}
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['runs'][0].update(arm_ids=['candidate'],selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']=deepcopy(pm['llm_policy']);m['llm_policy']['llm_calls'][0]['repeats']=1
m['retrieval_accounting']=deepcopy(pm['retrieval_accounting'])
for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]='PENDING_MEASUREMENT'
save(ADR/'실험/manifest.json',m);save(ART/'design-before-snapshot.json',m['design'])
files=set(pf['files']['candidate']);files.update(str(p.relative_to(ROOT)) for p in (ROOT/'05_TESTS/CONTRACTS').glob('*reference*.py'));files.update(str(p.relative_to(ROOT)) for p in (ROOT/'05_TESTS/CONTRACTS').glob('*navigation_input*.py'))
files.update(['05_TESTS/CONTRACTS/test_relation_read_policy.py','05_TESTS/CONTRACTS/test_retained_partial_connections.py'])
files=sorted(files)
d=ac.snapshot(ADR,'candidate',files,experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
shutil.copyfile(prior/'artifacts/known-request.json',ART/'known-request.json')
save(ART/'stage.json',{'base_release':ps['base_release'],'roots':{'candidate':str((d/'snapshot').relative_to(ROOT))},'candidate_dirs':{'candidate':str(d.relative_to(ROOT))},'working_before':{n:sha(ROOT/n) for n in files},'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'arm_order':['candidate'],'parent':str(prior.relative_to(ROOT))})
print(d/'snapshot')
