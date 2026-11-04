from common import *

DES.mkdir(exist_ok=False)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release=read(ROOT/pointer['manifest_path'])
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1335-voting-repeat-live/artifacts/design/candidate-integrated.json')
files=list(parent['selected_files'])
before={n:sha(ROOT/n) for n in files}
assert before==parent['selected_files'] and pointer['generation']==142
put(DES/'baseline.json',{'pointer':pointer,'release':release})
put(DES/'working-before.json',before)
criteria={
 'hypothesis':'The production shortcut resolver must receive the current request before model resolution; supervisor must receive exact selected-source progress; incomplete acquisition must resume selection instead of repeating final review.',
 'success':['Actual API path binds body/principal before ShortcutCases resolver; exact repeat keeps original target and READ/SELECT, changed requests retain ordinary command choices.', 'Supervisor wire preserves structure_selection_progress byte-for-byte and reports remaining requested sources; fast assessment handoff cannot label incomplete delivered selections ready.', 'Known SCOPE_ACQUISITION_INCOMPLETE exposes SELECT resume and explicitly incomplete acquisition; ordinary link/shape review failures remain ASSESS; UNKNOWN never eligible.', 'Existing106 plus new actualAPI and recorded-input contracts pass; source/legal/ACL/hash/budget/repair policies intact; exact working528 integration, MAIN142 unchanged.'],
 'failure':['No source acquisition falsification, automatic legal USE/EXCLUDE or hardcoded law answers.','No hidden provider retries or converting partial/failure to pass.'],
 'limits':{'model_calls':0,'heavy_workers':1,'rss_GiB':5,'swap_growth_MiB':128}}
put(DES/'criteria.json',criteria)
put(DES/'cases.json',[{'id':'entry','scope':'Per-original generation and exact conflict diagnostics, canonical/legacy unchanged'}, {'id':'selection','scope':'Known review-failure context and same-goal ASSESS reentry vs source/provider failures'}])
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Source and decision preservation with executable scope and review recovery contracts',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0].update(changes='Completed1335 exact528 code; MAIN142 reference source',controls='Canonical original/status/scope/claims/budget/security checks')
m['design']['arms'][1].update(changes='Early actual entry binding; supervisor selected-source progress; incomplete acquisition SELECT resume',controls='Same existing semantic validators, original acquisition, no automatic legal choices')
m['runs'][0].update(arm_ids=['integrated'],selection_rule='Prospectively frozen synthetic/source-record contracts and existing regression/API tests, no live models',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='ActualAPI entry/selection contracts plus unchanged1335 records',version='20261104-r1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['llm_policy']['llm_calls']=[]
for node in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):node['not_applicable_reason']='Synthetic contracts and read-only failed-record validation; no actual corpus retrieval or live model'
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'integrated',files,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'])
products=['case_repository','corrected_memory','memory_methods','investigation_supervisor']
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':files,'product_files':['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in products],'base_generation':142})
print(can/'snapshot')
