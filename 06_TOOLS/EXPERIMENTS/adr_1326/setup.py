from common import *

DES.mkdir(exist_ok=False)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release=read(ROOT/pointer['manifest_path'])
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1325-assessment-direct-links-live-multiturn/artifacts/design/candidate-integrated.json')
files=list(parent['selected_files'])
before={n:sha(ROOT/n) for n in files}
assert before==parent['selected_files'] and pointer['generation']==140
put(DES/'baseline.json',{'pointer':pointer,'release':release})
put(DES/'working-before.json',before)
criteria={
 'hypothesis':'Explicit per-original generation prevents grouping uncited originals as adopted evidence; complete link diagnostics and typed review-recovery context separate mechanical review failure from missing sources without changing legal judgments.',
 'success':['Generation reviews each presented original separately with target-bound IDs and exact row counts; original canonical validators and legacy grouped receipts remain valid.',
 'Actual failed1325 scope group stays rejected; diagnostics identify exact unsupported originals and linked claims without mutating claims/gaps/evidence or automatically excluding anything.',
 'Prior failed assessment exposes its exact failure category/issues and a valid ASSESS restart only for known review failures; repeat with unchanged request may retain goal and SELECT, changed requests remain model decisions.',
 'Synthetic actual API first/repair/persistent-error/OPEN paths and memory same-goal/changed-question paths preserve source, ACL, hashes, duplicate protection and bounded repair.',
 'Current working integration preserves all earlier1322/1324 and1323 startup changes; native SQL semantics unchanged; MAIN140 untouched.'],
 'failure':['No special case for test law, question or expected answer; no fabricated claims/source/EXCLUDE decisions.',
 'Do not reinterpret UNKNOWN/provider failures as safe review recovery or automatically resend.',
 'No live quality claim from contracts; real questions are a separately frozen successor experiment.'],
 'limits':{'model_calls':0,'heavy_workers':1,'rss_GiB':5,'swap_growth_MiB':128},
}
put(DES/'criteria.json',criteria)
put(DES/'cases.json',[{'id':'scope-links','scope':'Per-original generation and exact conflict diagnostics, canonical/legacy unchanged'}, {'id':'review-reentry','scope':'Known review-failure context and same-goal ASSESS reentry vs source/provider failures'}])
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Source and decision preservation with executable scope and review recovery contracts',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0].update(changes='Completed1325 exact525 code, same as1324',controls='Canonical original/status/scope/claims/budget/security checks')
m['design']['arms'][1].update(changes='Per-original generation; exact scope repair feedback; review-failure resume context; no guessed missing requirement guidance',controls='Same existing semantic validators, original acquisition, no automatic legal choices')
m['runs'][0].update(arm_ids=['integrated'],selection_rule='Prospectively frozen synthetic/source-record contracts and existing regression/API tests, no live models',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Synthetic scope and memory contracts plus unchanged rejected1325 actual records',version='20261104-r1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['llm_policy']['llm_calls']=[]
for node in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):node['not_applicable_reason']='Synthetic contracts and read-only failed-record validation; no actual corpus retrieval or live model'
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'integrated',files,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'])
products=['need_continuity','read_judgment_final','corrected_memory','memory_methods','completion_execution','answer_progress']
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':files,'product_files':['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in products],'base_generation':140})
print(can/'snapshot')
