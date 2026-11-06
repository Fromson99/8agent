from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac

DES.mkdir(exist_ok=False)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release=read(ROOT/pointer['manifest_path'])
assert pointer['generation']==145 and sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256']
files=list(release['files'])
before={n:sha(ROOT/n) for n in files}
put(DES/'baseline.json',{'pointer':pointer,'release':release})
put(ART/'integration-current-base.json',before)
products=['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in
          ('review_actions','shortcut_cases','corrected_memory')]
products+=['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py','02_BACKEND/semantic_runtime/oracle_query_plans.py']
source=ROOT/'04_EXPERIMENTS/ADR/ADR-1383-main145-ontology-usage/artifacts/usage-live/legacy365-on1-ontology-on'
origin=read(source/'turn-1/response.json.gz')['body']
assert origin['assembly']['term_agent']['stop_reason']=='ASSESSMENT_CONTRACT_UNRESOLVED' and not origin['answer']['claims']
receipt=read(source/'runtime-archive.json')
assert sha(source/'runtime.tar.gz')==receipt['archive']['sha256']
put(DES/'origin.json',{'case':str(source.relative_to(ROOT)), 'original_request':read(source/'turn-1/request.json'),
    'goal_id':origin['question_id'],'revision':origin['revision'],'archive':receipt['archive'],'inventory':receipt['inventory'],
    'profile':read(source/'binding.json')['profile'],'session_owner':'adr1383'})
criteria={'hypothesis':'The exact displayed and legacy chat retry commands bind to the previous response of the same session, case, ACL, version, and scope before model command selection. Stored incomplete final review re-enters assessment or source selection per verified acquisition error; already completed or unavailable returns public state with zero model calls.',
'success':['Native API tests for scope, stale or successful predecessor, changed text, duplicate/one-shot and both displayed and legacy external-prefixed requests. No source-request-route or memory-resolve on the exact command.','Read archived real failed 365 goal in a verified isolated copy, then issue the photo free-text followup through the same API using actual Qwen. Grade whether the recovery executes and the answer is supported separately.','Preserve current working changes and frozen release, compare native query plans, hashes and engine pins. Stop on UNKNOWN; do not resend.']}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Correct authenticated follow-up dispatch and existing source reuse; independently report actual answer coverage',success_criteria=criteria['success'],failure_criteria=['Missing goal binding, bypassed ACL, raw routing failure, or new command model on canonical retry.'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Unchanged MAIN145 historical observed route',controls='Actual previous photo probe; no new baseline model sends')
m['design']['arms'][1].update(changes='Exact chat review dispatch on current working tree',controls='Same stored originals, ACL, current release source generation and Qwen model; no product auto-selection')
m['lineage']['hypothesis_delta']='Fix observed command selection timeout and diagnostic exposure with durable case-bound action.'
m['dataset'].update(name='Archived failed Commercial Act question plus controlled service regressions',version='1383-1388',frozen_source=str((DES/'origin.json').relative_to(ROOT)),sha256=sha(DES/'origin.json'))
m['runs'][0].update(arm_ids=['repaired'],selection_rule='One archived real failed goal and controlled API coverage, no repeat after unknown',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','repaired')}
m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
put(DES/'candidate-parent.json',{'selected_files':before})
can=ac.snapshot(ADR,'repaired',files,experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
assert all(sha(can/'snapshot'/n)==before[n] for n in files)
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':files,'product_files':products})
print(can/'snapshot')
