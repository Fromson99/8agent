from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==146
release=read(ROOT/ptr['manifest_path']);base=ROOT/release['code_root'];assert sha(ROOT/ptr['manifest_path'])==ptr['release_manifest_sha256']
files=release['files'];before={n:sha(ROOT/n) for n in files}
put(DES/'baseline.json',{'pointer':ptr,'release':release})
put(ART/'working-before.json',before)
products=['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('case_repository','shortcut_cases')]
assert all(files[n]==before[n] for n in products)
criteria={'hypothesis':'A literal repeated question with the same current completed state, sources, scope, ACL and code binding can re-display its verified answer without model routing. Follow-up/new-topic requests still require ordinary semantic decisions.',
'success':['Exact literal successful repeat preserves the goal/revision/source/answer and pays zero physical calls; duplicate request ID remains model-free.','Incomplete/source-only, stale, changed scope/facts/task, scenario, new topic or unauthorised prior answer cannot use the shortcut. Validate current originals and final assessment through the existing committed response path.','Replay the seven actual first-turn provider responses from1394 into a fresh case under the candidate, run repeat with zero sends, then independently request implicit extraordinary-meeting followup, new voting topic and canonical retry. Grade actual new Qwen turns separately from replay.'],
'failure':['Stop live sends after UNKNOWN, preserve originals and original1394 unknown request; no original route or case binding rewrite. No automatic MAIN promotion.'],
'limits':{'physical_total':120,'physical_per_request':40,'rss_gib':5,'available_ram_floor_gib':3,'swap_growth_mib':1024},'authorization':'우리 멀티턴도 다시 한번 봐봐 문제없나 / 계속해봐'}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Literal completed repeat without physical model calls and retained state; observed related/new-topic turns',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']='Apply exact-state saved-answer presentation before semantic routing, then diagnose remaining branches.'
for a in m['design']['arms']:a.update(changes='Observed1394 MAIN146 reference' if a['id']=='baseline' else 'Only same-state completed literal repeat shortcut plus shared committed response verification',controls='Original generation, ACL, completion validators and ordinary semantic follow-up unchanged.')
m['runs'][0].update(arm_ids=['repaired'],selection_rule='One new case seeded from recorded real first turn; repeat deterministic, subsequent new turns real Qwen; stop on UNKNOWN',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
origin=ROOT/'04_EXPERIMENTS/ADR/ADR-1394-main146-multiturn-audit/artifacts/public-live/conversation-selected'
put(DES/'replay.json',{'origin':str(origin.relative_to(ROOT)),'first_calls':{str(i):sha(origin/f'raw/call-{i:03}/response.json.gz') for i in range(1,8)},'only_first_turn_replayed':True,'prior_unknown_never_replayed':9})
m['dataset'].update(name='Fresh native multi-turn case with real first-turn response replay and live followups',version='1396-r1',frozen_source=str((DES/'replay.json').relative_to(ROOT)),sha256=sha(DES/'replay.json'))
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','repaired')};m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'repaired',list(files),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001']);C=can/'snapshot'
for n,h in files.items():
 if sha(C/n)!=h:shutil.copyfile(base/n,C/n)
assert all(sha(C/n)==h for n,h in files.items())
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':list(files),'product_files':products+['02_BACKEND/semantic_runtime/oracle_query_plans.py']})
put(DES/'candidate-parent.json',{'selected_files':before})
print(C)
