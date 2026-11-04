from pathlib import Path
import sys,json,hashlib,shutil
ROOT=Path('/home/jin/8-AGENT');T=Path(__file__).parent
for n in ('common.py','resource_guard.py','check.py'):
 s=(T.with_name('adr_1319')/n).read_text().replace('ADR-1319-multiturn-command-assessment-repair','ADR-1321-multiturn-followup-review-build-integration').replace("default='repaired'","default='integrated'")
 (T/n).write_text(s)
sys.path.insert(0,str(T));from common import *
DES.mkdir(exist_ok=False)
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1319-multiturn-command-assessment-repair/artifacts';parent=read(P/'design/candidate-repaired.json');PC=ROOT/parent['code_root']
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/pointer['manifest_path']);C=ROOT/release['code_root'];assert all(sha(C/n)==h for n,h in release['files'].items())
put(DES/'baseline.json',{'pointer':pointer,'release':release});put(DES/'working-before.json',{n:sha(ROOT/n) for n in release['files']})
criteria={'hypothesis':'Memory continuation is independent of answer_first retrieval policy. Exact judgment-id branch diagnostics identify empty adopted-claim links; repair guidance offers model-owned alternatives for canonical and shared-link wire values. Regenerate native Oracle source hash closure without changing SQL plans. Preserve parallel MAIN139 embedding settings during selective working integration.',
 'success':['Default answer_first=false sends continuation instruction to both resolver and command-check; new-topic choice stays allowed.','Actual1319 assessment14 empty-claim errors identify the exact judgment row/claim link, canonical acceptance unchanged; no inferred legal status.','All previous118 contracts plus new regressions pass; Oracle639 plans unchanged apart from source hash bindings; enginepreflight passes.','Working source edits and pins match the tested integration candidate; latest embedding changes and active MAIN139 remain unchanged by this task.'],
 'failure':['No fresh external model dispatch after parent UNKNOWN. Prior3turn outcomes and source-only failures remain unchanged.','No source/ACL/integrity relaxation; no automatic UNKNOWN retry; no product question answer certification from mocks.','Do not overwrite concurrent unrelated files or move MAIN pointer.'],
 'limits':{'new_model_calls':0,'workers':1,'rss_GiB':5,'minimum_free_GiB':3},
 'baseline':'Parent1319 repaired six files plus concurrently selected MAIN139 embedding version; freeze full closure and lineage before effects.',
 'user_authorization':'진행해봐; original multi-turn correction and internal experiment request',
 'parent_evidence':{'prompt':str((P/'followup-prompt-diagnosis.json').relative_to(ROOT)),'prompt_sha256':sha(P/'followup-prompt-diagnosis.json'),'review':str((P/'public-live/repeat-repaired/canonical/014-output.json.gz').relative_to(ROOT)),'review_sha256':sha(P/'public-live/repeat-repaired/canonical/014-output.json.gz')}}
put(DES/'criteria.json',criteria);put(DES/'cases.json',[{'id':'followup-prompt','profile':'current default answer_first=false','expected':'continuation directive sent; model owns same/new goal decision'},{'id':'review-diagnostics','input':criteria['parent_evidence']['review'],'expected':'exact failed claim link location, no claim/status mutation'},{'id':'native-build','expected':'same639SQLplans, correctsourcehashes, latestMAIN139preserved'}])
m=read(ADR/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact delivered instructions, unchanged rejection/acceptance with precise diagnostics, SQL equality and working import/pin closure',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')});m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0].update(changes='Completed1319 frozen candidate observations; MAIN139 is current selected integration base',controls='Parent failures and source-only outputs not regraded')
m['design']['arms'][1].update(changes=criteria['hypothesis'],controls='No models, no source edits, preserve parallel current release')
m['runs'][0].update(arm_ids=['integrated'],selection_rule='All parent118contracts, exact014reviewdiagnostics, default-profilewire and nativeplan equality, then working consumer',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[];m['dataset'].update(name='Three observed structural defects, exact1319records',version='20261104-r1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['retrieval_accounting'].update(not_applicable_reason='No retrieval algorithm or corpus query execution in this branch. Recorded outputs are diagnostic inputs only; actual public outcomes remain in1319.',stage_ledger={'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':None,'artifact_path':None,'sha256':None,'not_applicable_reason':'No real retrieval executed; synthetic API checks use fixture documents, not an observed legal corpus.'})
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'integrated',list(release['files']),experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);SC=can/'snapshot'
for n in release['files']:shutil.copyfile(C/n,SC/n)
old=read(P/'design/baseline.json')['release']['files'];product=[n for n,h in parent['selected_files'].items() if n.startswith('02_BACKEND/semantic_runtime/legal_agent/') and h!=old[n]]
assert len(product)==6
for n in product:
 assert release['files'][n]==old[n],n
 shutil.copyfile(PC/n,SC/n)
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':list(release['files']),'product_files':product,'base_generation':pointer['generation'],'parent':parent['pin']})
print('Isolated latest MAIN',pointer['generation'],'plus parent6files; no working overwrite')
