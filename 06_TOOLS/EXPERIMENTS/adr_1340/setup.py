from common import *
import importlib.util

DES.mkdir(exist_ok=False)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release=read(ROOT/pointer['manifest_path'])
files=list(release['files'])
before={n:sha(ROOT/n) for n in files}
put(DES/'baseline.json',{'pointer':pointer,'release':release})
put(DES/'working-before.json',before)
criteria={
 'hypothesis':'Repeated directed page transitions without any newly visited page yield to the existing investigation handoff and final assessment, before consuming the investigation reserve.',
 'success':['First visits and ordinary backtracking/read selection preserve all candidates and existing schema/ACL checks.',
 'The repeated edge is blocked only after no new page since its prior traversal; all pending needs, source/judgment state and model proposals remain unchanged.',
 'Pager and cycle history commit together, with binding/hash validation and no counter reset on resumed same-menu calls; old three-field pager starts compatible history.',
 'Budget/time/UNKNOWN/invalid-target protection and supervisor page replay remain effective.',
 'Actual synthetic API reaches existing assessment with originals preserved and duplicate request causes no new model sends; exact candidate/working engine pins verified.'],
 'failure':['No fabricated FINISH proposal, legal sufficiency or evidence adoption; no charter/article-specific rule.',
 'No discarded hidden candidates, automatic transport retry, or real-model quality claim.'],
 'failure_contract':{'owner':'read_candidate_pages.move detects; Investigation.run catches existing ProgressHandoff and bounded_result routes to final assessment',
 'allowed_change':'Display-only checkpoint and repetition receipt; no sources, judgments, needs, authority or final status edits',
 'budget':'Existing physical40/final reserve and deadline unchanged; detection adds zero calls; same-state resume cannot loop again',
 'termination':'Existing bounded result: verified originals to assessment, or pending when none; assessment still owns legal completeness'},
 'limits':{'model_calls':0,'heavy_workers':1,'rss_GiB':5,'swap_growth_MiB':128,'available_start_GiB':5,'available_stop_GiB':3},
 'scope':'Working fix only, selected MAIN142 and field deployment unchanged. MAIN142 saved page responses serve as recorded behavior, not new live performance.'}
put(DES/'criteria.json',criteria)
put(DES/'cases.json',[{'id':'paging','scope':'First visit/backtracking/cycle, crash resume, stale state, budget, invalid target, saved1338 page sequence'}, {'id':'consumer','scope':'Synthetic API investigation handoff/assessment/idempotence and existing supervisor paging'}])
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Bounded display loop with unchanged source and final-assessment contracts',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0].update(changes='Completed1338 MAIN142 observation reference; current working pre-fix bytes retained',controls='No new live model calls')
m['design']['arms'][1].update(changes='Durable no-novel-page repeated-edge handoff in the shared pager',controls='All current working changes and semantic validation retained')
m['runs'][0].update(arm_ids=['bounded'],selection_rule='Prospective deterministic pager and API contracts plus existing relevant regressions; no live model',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Synthetic candidate-page and API contracts; unchanged1338 saved behavior',version='20261104-r1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['llm_policy']['llm_calls']=[]
for node in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):node['not_applicable_reason']='Display/control-only contracts over unchanged candidate membership; synthetic API and recorded behavior, no live retrieval comparison'
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'bounded',files,experiment_id=m['experiment_id'],arm_id='bounded',run_ids=['run-001'])
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':files,'product_files':['02_BACKEND/semantic_runtime/legal_agent/read_candidate_pages.py']})
print(can/'snapshot')
