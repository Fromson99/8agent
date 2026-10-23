from common import *
from copy import deepcopy
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1028-goal-verdict-handoff'
pm=read(prior/'실험/manifest.json');pf=read(prior/'artifacts/design-freeze.json');ps=read(prior/'artifacts/stage.json');parent=ROOT/ps['roots']['candidate']
assert pm['reservation']['status']=='completed' and pm['results']['status']=='complete'
assert all(sha(parent/n)==h for n,h in pf['files']['candidate'].items())
assert sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py')==pf['client_sha256']
m=read(ADR/'실험/manifest.json');m['design']=deepcopy(pm['design'])
m['design'].update(
 hypothesis='Bind the validated material ASSESS requirement to the original issue and offered gap action. Preserve navigation sufficiency opinion separately. An explicit gap-bound continuation may proceed without forcing a redundant opinion rewrite; unrelated tools remain forbidden for terminal goals.',
 primary_metric='No added goal call or repair for a terminal navigation opinion paired with an explicitly offered action for a validated ASSESS requirement.',
 success_criteria='All source/state/goal/cycle/API contracts pass. Context and receipt retain both semantic opinions and current ASSESS requirements. Valid gap action can continue in one existing navigation call; forged issue, binding, or unrelated target cannot use the exception. One known-question live run records no separate goal call, no repeated connection directory, and no goal/action repair. Calls<=9, input<=304086 and delegated-source reach are observed targets, reported separately from semantic quality.',
 failure_criteria='Loss of either opinion, fabricated missing need or target, accepting unknown/stale target binding, bypassing authorization or canonical completion checks, repeated correction on resume, extra goal-review call or applicable contradiction repair, or live operational targets missed.',
 sampling='One unchanged known public question, candidate only; historical complete ADR1028 unpaired comparison. No judge, adaptive rerun or approved gold.',
 working_integration='Selective integration of validated existing module changes into working code, disabled by default until separate release selection. No MAIN102 or GENOS activation.')
m['design']['arms'][0].update(derived_from=['ADR-1028-experiment-v1/candidate'],changes='Historical ADR1028: terminal assembly succeeded but ASSESS requirement not reflected in goal;9calls including1repair.',controls='Same data/model/question and14call/1800s budgets.')
m['design']['arms'][1].update(changes='Effective goal requirements and exact ASSESS gap-action binding, preserving both model opinions without another model call.',controls='Same inherited goal, source/scope/cycle protections and model/data/question/budgets.')
m['design']['code_isolation']['candidates']=[]
m['design']['failure_recovery']={'owner':'answer_progress assembles only allowed terminal actions; output_contract retains one repair for other errors; no new retry owner.',
 'limits':'14 physical calls /1800s; transport retry0; schema repair1; no added review call; RSS6GiB/min available4GiB, sequential.',
 'state':'Original issue set and request/binding preserved. Current evidence IDs validated. Accepted opinion receipt hashed and idempotent; same key with changed proposal or tampered receipt fails closed. Invalid opinions are not saved. On repeated no-answer-progress or budgets, deliver verified originals to existing assessment without certifying sufficiency. Failure/partial/current evidence and counters preserved on resume.'}
m['lineage']['hypothesis_delta']='Connect verified ASSESS missing requirements to the existing goal ledger and exact offered actions; preserve both opinions without reasking the model.'
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
