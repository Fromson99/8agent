from common import *
from copy import deepcopy
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1029-assessment-goal-binding'
pm=read(prior/'실험/manifest.json');pf=read(prior/'artifacts/design-freeze.json');ps=read(prior/'artifacts/stage.json');parent=ROOT/ps['roots']['candidate']
assert pm['reservation']['status']=='completed' and pm['results']['status']=='complete'
assert all(sha(parent/n)==h for n,h in pf['files']['candidate'].items())
assert sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py')==pf['client_sha256']
m=read(ADR/'실험/manifest.json');m['design']=deepcopy(pm['design'])
m['design'].update(
 hypothesis='A model-reported no-change streak may stop investigation only after the first offered source READ for the validated material ASSESS need has had one attempt. Grant at most one batch for each bound gap, retain counters/opinions and all canonical source/permission/budget checks.',
 primary_metric='First unattempted material-gap READ is not preempted solely by goal no-progress; subsequent unchanged reads still stop with preserved evidence.',
 success_criteria='Contracts cover first read, completed/failed prior read, repeated request/resume, changed gap/binding, unrelated target and exhausted budget. No separate goal model call. One known-question run reaches delegated original, with0 duplicate directories and0 goal-action repair calls; calls<=12 and input<=939172 as ADR1026 historical targets.',
 failure_criteria='Grant outside offered authorized READ or material reviewed need, more than one grant per bound gap, reset of counts/budget/deadline, bypass of canonical validation, first eligible READ blocked by goal streak, or operational targets missed.',
 sampling='One unchanged known public question, candidate only; complete ADR1029 parent and ADR1026 historical operational context, unpaired. No judge or adaptive reruns.',
 working_integration='Selective integration of validated existing module changes into working code; current default feature flag and selected MAIN102/GENOS unchanged.')
m['design']['arms'][0].update(derived_from=['ADR-1029-experiment-v1/candidate'],changes='Historical ADR1029: goals synchronized,0repairs; goal streak stopped the first delegated READ;9calls.',controls='Same data/model/question and14call/1800s budgets.')
m['design']['arms'][1].update(changes='One durable first-read allowance per unattempted validated material gap, without new meaning judgment or added model call.',controls='Same goal, source/scope/cycle protections and model/data/question/budgets.')
m['design']['code_isolation']['candidates']=[]
m['design']['failure_recovery']={'owner':'answer_progress assembles only allowed terminal actions; output_contract retains one repair for other errors; no new retry owner.',
 'limits':'14 physical calls /1800s; transport retry0; schema repair1; no added review call; RSS6GiB/min available4GiB, sequential.',
 'state':'Original issue set and request/binding preserved. Current evidence IDs validated. Accepted opinion receipt hashed and idempotent; same key with changed proposal or tampered receipt fails closed. Invalid opinions are not saved. On repeated no-answer-progress or budgets, deliver verified originals to existing assessment without certifying sufficiency. Failure/partial/current evidence and counters preserved on resume.'}
m['lineage']['hypothesis_delta']='Do not count navigation-only no-change as enough to preempt the first source READ for a validated material gap; allow one attempt within unchanged budgets.'
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
