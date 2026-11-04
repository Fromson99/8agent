from common import *
import shutil
DES.mkdir(exist_ok=False)
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1356-qwen-stream-schema-diagnosis/artifacts'
f=read(P/'design/candidate-stream.json');C=ROOT/f['code_root']
assert all(sha(C/n)==h for n,h in f['selected_files'].items())
for n in ['baseline.json','working-before.json','live-cases.json','grading-only.json','source-scope.json','providers.json','provider-parasail.json','authorization.json']:
 put(DES/n,read(P/'design'/n))
put(DES/'candidate-parent.json',f)
criteria={'hypothesis':'Bound the action rationale to400 characters as required by its one-sentence purpose. SSE1356 proved runaway missing_need generation; reject oversized decisions without truncation and retain all final validation.',
 'success':['Actual365 and434 complete with source-supported claims and final review','SSE requires DONE, consistent provider/model/id, terminal reason, exact content and usage; malformed/incomplete stream never accepted','Original schema, source, ACL, wire, budget and duplicate invariants unchanged'],
 'failure':['Unknown stops this run; no retry of earlier UNKNOWN or changed request hidden in same reservation','SSE heartbeat alone cannot identify remote root cause; report only observed deltas/errors','No JSON mode or strict false fallback, no truncated answer, no source mutation'],
 'plan':{'cases':['B03-03','B03-17'],'providers':['parasail'],'max_calls':80,'output_cap':None,'model_deadline_seconds':180,'request_deadline_seconds':1800,'repaired':True,'strict':True,'reasoning':'none','repeats':1},
 'limits':{'heavy_workers':1,'available_start_GiB':5,'available_stop_GiB':3,'rss_GiB':5,'swap_growth_MiB':128}}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Complete original-schema validated responses and diagnostic raw stream',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Completed1356 same528 with captured unbounded rationale repetition',controls='Reference only')
m['design']['arms'][1].update(changes='One product file: explicit rationale length schema and concise instruction; same strict SSE observation',controls='Same provider, reasoningnone, strict original schema, no retry; stream transport only')
m['runs'][0].update(arm_ids=['repaired'],selection_rule='365 then434, independent fresh requests; first UNKNOWN stops',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='R4 public365/434',version='20261104-r4',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'repaired',list(f['selected_files']),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
for n,h in f['selected_files'].items():
 if sha(can/'snapshot'/n)!=h:shutil.copyfile(C/n,can/'snapshot'/n)
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':list(f['selected_files']),'product_files':['02_BACKEND/semantic_runtime/legal_agent/decision_projection.py']})
shutil.copytree(P/'transport',ART/'transport')
print(can/'snapshot')
