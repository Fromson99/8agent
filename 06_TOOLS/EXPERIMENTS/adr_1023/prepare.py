from common import *
from copy import deepcopy
import sys, shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1022-scope-first-grounded-navigation'
pm=read(prior/'실험/manifest.json');pf=read(prior/'artifacts/design-freeze.json');ps=read(prior/'artifacts/stage.json');parent=ROOT/ps['roots']['candidate']
m=read(ADR/'실험/manifest.json');m['design']=deepcopy(pm['design'])
m['design'].update(
 hypothesis='Persist per-scope verified directory receipts and present prior action outcomes with still-unread endpoints. Do not offer or execute unchanged FOLLOW_CONNECTION even across A-B-A, view changes, equivalent scopes, recovery or resume. Read a prior verified target directly, binding its exact anchor scope; new delivered anchor bytes may open a new scope.',
 primary_metric='Zero repeated unchanged connection directory executions; no A-B-A cycle; known query reaches stored linked originals and a cited answer with native FINISH, fewer than12 physical calls and682477 input tokens.',
 success_criteria='All relevant source/state/ACL and cycle contracts pass, including API A-B-repeat rejection and resume. Live known query once within14calls/1800s: zero duplicate directory operations, stored linked original reach, cited answer, model FINISH, <12calls and <682477 input tokens. Passing mechanics alone is not full success.',
 failure_criteria='Repeated unchanged directory operation, source/ACL/hash/state regression, lost unread target after switching scopes, unbounded repair, missing linked original or cited answer, budget stop instead of FINISH, or call/token criterion missed.',
 sampling='One exposed known public question, candidate once. Completed ADR1022/candidate is historical unpaired context, not a concurrent control. No adaptive live reruns, no legal gold or generalization claim.',
 failure_recovery={'owner':'connection_scope receipt/availability/execution guard; existing gateway alone owns schema repair','limits':'14physical calls;1800s;transport retry0;schema repair1. RSS6GiB; minimum available4GiB; sequential only.', 'state':'Record success, partial and failed directory outcome separately. Same exact anchor bytes+request+authorized scope do not rescan; partial or failed results preserve gaps and structural fallback. New anchor bytes can scan. Current target coverage recomputed from acquired originals. Receipt hash/binding/ACL checked; stale or tampered state fails closed. Accepted action resume reuses completed receipt without resetting budgets. No forced legal applicability or FINISH.'},
 working_integration='Isolated candidate based on current working code plus explicit five-module ADR1022 patch; no MAIN or GENOS cutover. Concurrent unrelated working changes preserved.')
m['design']['arms'][0].update(derived_from=['ADR-1022-experiment-v1/candidate'],changes='Completed ADR1022/candidate historical result; no new baseline model calls.',controls='Same question/data/model/budget; temporal unpaired context.')
m['design']['arms'][1].update(changes='Retain ADR1022 scope-first and grounded locator fixes. Add durable directory receipt, action outcome history, direct saved-target access, duplicate availability+execution guard and resume preservation.',controls='Current working dependencies; no answer-specific coordinates; same model/data/question/14call budget; no added model stage.')
m['design']['code_isolation']['candidates']=[]
m['lineage']['hypothesis_delta']=m['design']['hypothesis'];m['llm_policy']=deepcopy(pm['llm_policy']);m['retrieval_accounting']=deepcopy(pm['retrieval_accounting'])
for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]='PENDING_MEASUREMENT'
m['runs'][0].update(arm_ids=['candidate'],selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
save(ADR/'실험/manifest.json',m);save(ART/'design-before-snapshot.json',m['design'])
files=set(pf['files']['candidate']);present={n for n in files if (ROOT/n).is_file()}
d=ac.snapshot(ADR,'candidate',sorted(present),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001']);c=d/'snapshot'
# Explicit adoption of parent-only fixes. Preserve all other latest working files.
adopt=['02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('connection_scope.py','law_navigation.py','decision_projection.py','request_repair.py','completion_execution.py')]+['05_TESTS/CONTRACTS/test_selected_connection_scope_api.py']
for n in adopt:shutil.copyfile(parent/n,c/n)
for n in files-present:
 (c/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(parent/n,c/n);ac.register_file(d,n,upstream_state='absent')
shutil.copyfile(prior/'artifacts/known-request.json',ART/'known-request.json')
save(ART/'stage.json',{'base_release':ps['base_release'],'roots':{'candidate':str(c.relative_to(ROOT))},'candidate_dirs':{'candidate':str(d.relative_to(ROOT))},'working_before':{n:sha(ROOT/n) for n in present},'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'arm_order':['candidate'],'parent':str(prior.relative_to(ROOT)), 'explicit_parent_adoption':adopt,'upstream_differences_from_parent':[n for n in present if sha(ROOT/n)!=pf['files']['candidate'][n]]})
print(c)
