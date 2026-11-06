from common import *
import shutil
DES.mkdir(exist_ok=False)
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1372-assigned-original-use-repair-feedback/artifacts'
f=read(P/'design/candidate-repaired.json');C=ROOT/f['code_root']
assert all(sha(C/n)==h for n,h in f['selected_files'].items())
for n in ['baseline.json','working-before.json','live-cases.json','grading-only.json','source-scope.json','providers.json','provider-parasail.json','authorization.json']:
 put(DES/n,read(P/'design'/n))
working={n:sha(ROOT/n) for n in f['selected_files']}
target='02_BACKEND/semantic_runtime/legal_agent/need_continuity.py'
prior=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1369-explicit-exclusion-quote-selection/artifacts/design/candidate-repaired.json')
assert working[target] in (prior['selected_files'][target], f['selected_files'][target]), 'Concurrent target edit'
put(DES/'working-before.json',working)
put(ART/'combined-parent.json',{'direct_parent':f['code_root'],'concurrent_files':[n for n in working if working[n]!=f['selected_files'][n]],'all_current_changes_preserved':True})
put(DES/'candidate-parent.json',f)
criteria={'hypothesis':'Report conflicting resolved needs and unsupported original USE together during one repair. Preserve all original decisions and canonical validation.',
 'success':['Actual365 and434 complete with source-supported claims and final review','SSE requires DONE, consistent provider/model/id, terminal reason, exact content and usage; malformed/incomplete stream never accepted','Original schema, source, ACL, wire, budget and duplicate invariants unchanged'],
 'failure':['Unknown stops this run; no retry of earlier UNKNOWN or changed request hidden in same reservation','SSE heartbeat alone cannot identify remote root cause; report only observed deltas/errors','No JSON mode or strict false fallback, no truncated answer, no source mutation'],
 'plan':{'cases':['B03-12','B05-03','B03-03','B03-17'],'providers':['reka'],'max_calls':160,'output_cap':None,'model_deadline_seconds':180,'request_deadline_seconds':1800,'stream':True,'strict':True,'reasoning':'none','repeats':1},
 'limits':{'heavy_workers':1,'available_start_GiB':5,'available_stop_GiB':3,'rss_GiB':5,'swap_growth_MiB':128}}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Complete original-schema validated responses and diagnostic raw stream',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='1372 completed three of four; B03-12 had an unsupported resolved need after repair',controls='Reference only')
m['design']['arms'][1].update(changes='Combined dependent-need and original-use feedback, same REKA FP8 and strict reviews',controls='Same provider, reasoningnone, strict original schema, no retry; stream transport only')
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Two previous failures then two controls, independent requests; first UNKNOWN stops',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='R4 public two failed cases and two controls',version='20261104-r4',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['design']['retrieval_stage_plan']=read(P.parent/'실험/manifest.json')['design']['retrieval_stage_plan']
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'repaired',list(f['selected_files']),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
assert all(sha(can/'snapshot'/n)==h for n,h in working.items())
shutil.copyfile(C/target,can/'snapshot'/target)
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':list(f['selected_files']),'product_files':['02_BACKEND/semantic_runtime/legal_agent/need_continuity.py']})
shutil.copytree(P/'transport',ART/'transport')
print(can/'snapshot')

matrix=ROOT/'04_EXPERIMENTS/ADR/ADR-1370-integration-oneclick-provider-repeat/artifacts/design'
put(DES/'provider-reka.json',read(matrix/'provider-reka.json'))
put(DES/'providers.json',{'reka':read(matrix/'providers.json')['reka']})
