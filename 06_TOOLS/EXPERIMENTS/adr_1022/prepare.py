from common import *
from copy import deepcopy
import sys, shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1021-retained-scope-answer-progress'
pm=read(prior/'실험/manifest.json');pf=read(prior/'artifacts/design-freeze.json');ps=read(prior/'artifacts/stage.json')
m=read(ADR/'실험/manifest.json');m['design']=deepcopy(pm['design'])
m['design'].update(
 hypothesis='Before ordinary FINISH, the existing choice selects an exact delivered scope and receives its stored connection directory. Assessment target locations are selected only from source/verified-reference labels; unknown locations preserve the semantic gap with an empty locator. This prevents unseen-link termination and invented direct gap reads without forcing every link to be read.',
 primary_metric='Known question reaches stored linked delegated originals and returns cited claims, with fewer than13 physical calls and fewer than890807 input tokens; no unsupported assessment locator is executed.',
 success_criteria='All scope/target integrity and service failure contracts pass. Known question once within14 calls/1800s returns a cited answer and follows stored links; no FINISH before connection attempt, no invented gap target read, no forced article numbers. Target fewer than13 calls and890807 input tokens. Report semantic incompleteness and budget stop separately.',
 failure_criteria='Native request failure, missing needed linked originals, ungrounded assessment locator accepted, unauthorized scope expansion, changed source/hash/state/ACL, unbounded repair, or call/token target missed.',
 sampling='One exposed known public question, candidate once. Historical ADR1021 failed run and ADR1020 completed run are unpaired context only. No adaptive live rerun; no approved gold or generalization claim.',
 failure_recovery={'owner':'existing navigation schema/repair and assessment decision journal','limits':'14 physical calls;1800s;transport retry0;existing schema repair1; provider error stops request. RSS6GiB and minimum available4GiB; sequential only.', 'state':'Exact scope and prior receipts preserved; connection FAILED/PARTIAL/empty results allow bounded completion. Budget handoff remains available. Unsupported gap locator fails existing proposal validation, preserving raw proposal and semantic gap; unknown locator uses empty string and existing content search.'},
 working_integration='Candidate snapshot only for this probe; no MAIN or GENOS change. Preserve current working tree and concurrent Oracle changes.')
m['design']['arms'][0].update(derived_from=['ADR-1021-experiment-v1/candidate'],changes='Historical complete ADR1021 candidate; no new control calls.',controls='Same question/data/model/budget. Temporal unpaired observation.')
m['design']['arms'][1].update(changes='Current working code (same RAG sources as parent, answer_progress_control=false); require selected connection attempt before ordinary FINISH; evidence-bound assessment target enum and independent validation.',controls='Model/data/question/14-call limit retained; no added model stage, no answer-specific routing. Concurrent Oracle files remain as current snapshot and are not exercised by local SQLite service.')
m['design']['code_isolation']['candidates']=[]
m['lineage']['hypothesis_delta']=m['design']['hypothesis'];m['llm_policy']=deepcopy(pm['llm_policy']);m['retrieval_accounting']=deepcopy(pm['retrieval_accounting'])
for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]='PENDING_MEASUREMENT'
m['runs'][0].update(arm_ids=['candidate'],selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
save(ADR/'실험/manifest.json',m);save(ART/'design-before-snapshot.json',m['design'])
files=set(pf['files']['candidate'])
d=ac.snapshot(ADR,'candidate',sorted(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
shutil.copyfile(prior/'artifacts/known-request.json',ART/'known-request.json')
save(ART/'stage.json',{'base_release':ps['base_release'],'roots':{'candidate':str((d/'snapshot').relative_to(ROOT))},'candidate_dirs':{'candidate':str(d.relative_to(ROOT))},'working_before':{n:sha(ROOT/n) for n in files},'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'arm_order':['candidate'],'parent':str(prior.relative_to(ROOT)), 'upstream_differences_from_parent':[n for n in files if sha(ROOT/n)!=pf['files']['candidate'][n]]})
print(d/'snapshot')
