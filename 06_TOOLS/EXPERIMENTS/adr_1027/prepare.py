from common import *
from copy import deepcopy
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1026-connection-cycle-retry3'
pm=read(prior/'실험/manifest.json');pf=read(prior/'artifacts/design-freeze.json');ps=read(prior/'artifacts/stage.json');parent=ROOT/ps['roots']['candidate']
assert pm['reservation']['status']=='completed' and pm['results']['status']=='complete'
assert all(sha(parent/n)==h for n,h in pf['files']['candidate'].items())
assert sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py')==pf['client_sha256']
m=read(ADR/'실험/manifest.json');m['design']=deepcopy(pm['design'])
m['design'].update(
 hypothesis='Within the existing read-choice call, update every original issue with answer, current evidence and a material missing need. Bind each proposed tool to a NEEDS_SOURCE issue; complete issues cannot trigger more tools. Save and reuse bounded goal opinions across decisions/resume without a separate model call.',
 primary_metric='No separate progress LLM calls; complete issue coverage and goal/action consistency; zero unchanged directory repeats; live original reach plus native FINISH before investigation budget.',
 success_criteria='Goal ledger, single-call API and failure/resume/ACL contracts pass. One known-query run reaches the stored delegated originals and cited answer, emits native FINISH, zero duplicate directory operations or separate progress calls, fewer than12 physical calls and939172 input tokens. No source/state/ACL regression. No legal quality certification.',
 failure_criteria='Omitted or invented issue, unsupported evidence, tool for answered issue, premature finish with NEEDS_SOURCE, duplicate state commit, loss of saved sources, extra progress-only model call, broken cycle guard, native budget stop or live call/token threshold missed.',
 sampling='Known exposed question once, candidate only. Historical complete ADR1026 is unpaired comparison. Sequential, no adaptive rerun or offline judge. Contract tests are synthetic and do not certify model semantics.',
 working_integration='Extend the existing answer_progress/decision_projection path in an isolated successor of ADR1026; preserve its scope-first, locator grounding and cycle fixes. No MAIN/GENOS cutover or whole-snapshot overwrite of working code.')
m['design']['arms'][0].update(derived_from=['ADR-1026-experiment-v1/candidate'],changes='Completed ADR1026 historical result only; no new control model calls.',controls='Same question/data/model and14call/1800s budgets.')
m['design']['arms'][1].update(changes='Per-issue goal progress in the same decision call, deterministic action binding, persisted opinions and bounded no-answer-progress handoff; enable existing answer_progress_control.',controls='Preserve ADR1026 source/scope/cycle protections; unchanged model/data/question/budgets; answer_first remains false.')
m['design']['code_isolation']['candidates']=[]
m['design']['failure_recovery']={'owner':'Existing output_contract owns one repair for schema/goal/action mismatch; answer_progress owns receipt and bounded handoff; existing gateway owns transport policy.',
 'limits':'14 physical calls /1800s; transport retry0; schema repair1; no added review call; RSS6GiB/min available4GiB, sequential.',
 'state':'Original issue set and request/binding preserved. Current evidence IDs validated. Accepted opinion receipt hashed and idempotent; same key with changed proposal or tampered receipt fails closed. Invalid opinions are not saved. On repeated no-answer-progress or budgets, deliver verified originals to existing assessment without certifying sufficiency. Failure/partial/current evidence and counters preserved on resume.'}
m['lineage']['hypothesis_delta']='Replace free-standing next-tool reasons with mandatory per-original-issue answer/need updates and enforce their consistency in the same call.'
m['llm_policy']=deepcopy(pm['llm_policy']);m['retrieval_accounting']=deepcopy(pm['retrieval_accounting'])
for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][k]='PENDING_MEASUREMENT'
m['runs'][0].update(arm_ids=['candidate'],selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
save(ADR/'실험/manifest.json',m);save(ART/'design-before-snapshot.json',m['design'])
files=set(pf['files']['candidate']);present={n for n in files if (ROOT/n).is_file()}
d=ac.snapshot(ADR,'candidate',sorted(present),experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001']);c=d/'snapshot'
# Explicit whole candidate reproduction for an unchanged retest, never copied into working product.
for n in files:
 (c/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(parent/n,c/n)
 if n not in present:ac.register_file(d,n,upstream_state='absent')
assert all(sha(c/n)==h for n,h in pf['files']['candidate'].items())
shutil.copyfile(prior/'artifacts/known-request.json',ART/'known-request.json')
save(ART/'stage.json',{'base_release':ps['base_release'],'roots':{'candidate':str(c.relative_to(ROOT))},'candidate_dirs':{'candidate':str(d.relative_to(ROOT))},'working_before':{n:sha(ROOT/n) for n in present},'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'arm_order':['candidate'],'parent':str(prior.relative_to(ROOT)),'same_parent_files':len(files)})
print('Prepared parent candidate',len(files),'files; new contracts required')
