from common import *
from copy import deepcopy
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1020-direct-connections-bounded-review';pm=read(prior/'실험/manifest.json');pf=read(prior/'artifacts/design-freeze.json');ps=read(prior/'artifacts/stage.json');pc=ROOT/ps['roots']['candidate']
m=read(ADR/'실험/manifest.json');m['design']=deepcopy(pm['design'])
m['design'].update(hypothesis='Refreshing delivered spans only inside the exact previously selected structural scope preserves the selected connection directory across additional reads. Existing answer progress review within the same choice call distinguishes necessary gaps from exploratory expansion, and the narrow choice contract remains usable with two investigation calls left.',
 primary_metric='Same-scope acquired extension keeps dependency cards; no nested reference model calls; known query uses fewer than13 calls and fewer than890807 input tokens while delivering cited claims and linked delegated originals.',
 success_criteria='Same-scope extension updates verified spans without a new model selection; different structural scope/exclusion and removed or changed original spans never auto-refresh. Hash/ACL/resume failures remain blocked. Existing answer progress contracts pass, including two no-change opinions handing originals to assessment. Last two investigation calls keep narrow choice/progress contract. One actual known query <=14 calls, no provider fallback/retry; report semantic answer and INVESTIGATION_BUDGET separately. Target: fewer than13 calls and fewer than890807 input tokens, no forced article read.',
 failure_criteria='Lost selected cards after a verified same-scope extension; auto-expansion outside selected structure; fabricated source/status; disabled integrity checks; no-call-progress state reset; native request fails or total cost not improved.',
 sampling='Synthetic scope-refresh and progress/budget/API contracts followed by one actual exposed known question; historical ADR1020 control. No adaptive rerun.',
 failure_recovery={'owner':'existing source choice/progress and assessment owners','limits':'14 calls, 1800s, transportretry0, existing repair1; progress handoff uses existing assessment reserve','state':'Original exact selected structure stays fixed; only newly verified delivered spans inside it refresh. Preserve original selection and host refresh as distinct events.'},
 working_integration='Integrate only verified scope, selector and profile diffs with current upstream guards; unrelated Oracle changes excluded. MAIN/GENOS unchanged.')
m['design']['arms'][0].update(derived_from=['ADR-1020-experiment-v1/candidate'],changes='Historical complete ADR1020 candidate/native record; no live control.',controls='Same data/model/question; temporal unpaired comparison.')
m['design']['arms'][1].update(changes='Same-structure delivered scope refresh; answer_progress_control=true; keep narrow choice with two investigation calls left.',controls='Same model/data/request and14-call total; answer_first=false; no additional LLM stage.')
m['design']['code_isolation']['candidates']=[];m['lineage']['hypothesis_delta']=m['design']['hypothesis'];m['llm_policy']=deepcopy(pm['llm_policy']);m['retrieval_accounting']=deepcopy(pm['retrieval_accounting'])
for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]='PENDING_MEASUREMENT'
m['runs'][0].update(arm_ids=['candidate'],selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
save(ADR/'실험/manifest.json',m);save(ART/'design-before-snapshot.json',m['design'])
files=set(pf['files']['candidate']);files.update(['05_TESTS/CONTRACTS/test_answer_progress.py','05_TESTS/CONTRACTS/test_answer_progress_api.py'])
d=ac.snapshot(ADR,'candidate',sorted(files),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
# Exact completed parent implementation, excluding unrelated concurrent Oracle work.
for n in pf['files']['candidate']:shutil.copyfile(pc/n,d/'snapshot'/n)
shutil.copyfile(prior/'artifacts/known-request.json',ART/'known-request.json')
save(ART/'stage.json',{'base_release':ps['base_release'],'roots':{'candidate':str((d/'snapshot').relative_to(ROOT))},'candidate_dirs':{'candidate':str(d.relative_to(ROOT))},'working_before':{n:sha(ROOT/n) for n in files},'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'arm_order':['candidate'],'parent':str(prior.relative_to(ROOT)), 'unrelated_upstream_differences':[n for n in pf['files']['candidate'] if sha(ROOT/n)!=pf['files']['candidate'][n]]})
print(d/'snapshot')
