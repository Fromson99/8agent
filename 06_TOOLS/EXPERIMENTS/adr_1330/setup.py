from common import *

DES.mkdir(exist_ok=False)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release=read(ROOT/pointer['manifest_path'])
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1329-repeat-scope-join-wiring/artifacts/design/candidate-integrated.json')
files=list(parent['selected_files'])
before={n:sha(ROOT/n) for n in files}
assert pointer['generation']==140
put(DES/'baseline.json',{'pointer':pointer,'release':release})
put(DES/'working-before.json',before)
criteria={
 'hypothesis':'Handle malformed rejected review fields without exceptions; preserve mechanically derived scope claim joins, bind literal repeats to their current goal, and deliver original-grounded navigation guidance on the actual compact/supervisor wire.',
 'success':['Scope USE claims are exact joins of model-selected claims/evidence/issues; no legal text, basis, use/exclude/open, reasons, gaps or judgment adoption changes. Unsupported USE and conflicts remain rejected; canonical legacy readers preserved.',
 'Exact latest request and state task with unchanged request scope, READY route, source binding and authority exposes only presentation/reentry/clarification for that goal. Changed question, facts, scope, pending or stale bindings use ordinary interpretation.',
 'Actual navigation invoke includes the general no-guessed-deadline/delegation instruction for compact/supervisor and ordinary progress paths.',
 'Synthetic API, real memory, provider projection, source integrity and existing regression checks preserve known failures, UNKNOWN/budget/duplicate rules; candidate and working525 match; MAIN140 unchanged.'],
 'failure':['No law/test-specific rule, answer substitution or automatic USE/EXCLUDE choice.', 'No automatic provider retry or source-only success claim.', 'No model quality claim from contracts.'],
 'limits':{'model_calls':0,'heavy_workers':1,'rss_GiB':5,'swap_growth_MiB':128}}
put(DES/'criteria.json',criteria)
put(DES/'cases.json',[{'id':'scope','scope':'Per-original generation and exact conflict diagnostics, canonical/legacy unchanged'}, {'id':'repeat','scope':'Known review-failure context and same-goal ASSESS reentry vs source/provider failures'}])
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Source and decision preservation with executable scope and review recovery contracts',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0].update(changes='Completed1329 frozen exact525 candidate; working1326 kept as integration base',controls='Canonical original/status/scope/claims/budget/security checks')
m['design']['arms'][1].update(changes='Derived exact scope joins; literal repeat target restriction; actual navigation guidance wiring',controls='Same existing semantic validators, original acquisition, no automatic legal choices')
m['runs'][0].update(arm_ids=['integrated'],selection_rule='Prospectively frozen synthetic/source-record contracts and existing regression/API tests, no live models',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Synthetic scope and memory contracts plus unchanged failed1327 records',version='20261104-r1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['llm_policy']['llm_calls']=[]
for node in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):node['not_applicable_reason']='Synthetic contracts and read-only failed-record validation; no actual corpus retrieval or live model'
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'integrated',files,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'])
import shutil
parent_root=ROOT/parent['code_root']
for n,h in parent['selected_files'].items():
 assert sha(parent_root/n)==h
 shutil.copyfile(parent_root/n,can/'snapshot'/n)
products=['need_continuity','corrected_memory','memory_methods','completion_execution','answer_progress','decision_projection','investigation_supervisor']
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':files,'product_files':['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in products],'base_generation':140})
print(can/'snapshot')
