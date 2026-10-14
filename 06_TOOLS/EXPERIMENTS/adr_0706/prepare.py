"""Freeze the fresh-request-only comparison before implementation and calls."""
from pathlib import Path
import hashlib, json, subprocess

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0706-fused-request-entry-e2e'; D=A/'artifacts/design'
D.mkdir(parents=True,exist_ok=True)
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
pp=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'; pointer=read(pp)
assert pointer['generation']==48
release=read(R/pointer['manifest_path'])
assert sha(R/pointer['manifest_path'])==pointer['release_manifest_sha256']
for name,h in release['files'].items():assert sha(R/name)==sha(R/release['code_root']/name)==h,name
prior=read(R/'04_EXPERIMENTS/ADR/ADR-0703-exception-coupled-final-holdout/artifacts/design/dataset.json')
cm=read(R/'04_EXPERIMENTS/ADR/ADR-0705-cm-max-call-bottleneck-probe/artifacts/design/dataset.json')
dataset={'cases':[{'case_id':ident,'question':prior['cases'][i]['question']} for ident,i in [('front-statute-001',1),('front-statute-002',2)]]+cm['cases'],
 'product_gold':False,'scope':'Public statute questions only; no private data or approved golden answers.',
 'selection':'Known named statute conjunction and exception cases H02/H03 plus known difficult abbreviated CM018; in-sample probe, no holdout claim.',
 'order':[['baseline','front-statute-001'],['fused-entry','front-statute-001'],['fused-entry','front-statute-002'],['baseline','front-statute-002'],['baseline','cm-018'],['fused-entry','cm-018']]}
criteria={'scope':'Fuse routing, fresh CASE_START command and INTENT in one model response. Host validates command/scope/schema; no separate semantic command-check for fresh requests. Existing goals, history operations, reuse and failed resumes retain legacy path.',
 'success':['Fresh eligible CASE accepts one request-entry model attempt and persists the same seven checkpoints without duplicate legacy front calls','Each paired full API request records final success/failure, physical calls including repairs, individual/total provider time, tokens and end-to-end request time','No baseline-completed case becomes failure or loses explicit requested issue; no structural/citation/ACL/state regression','Report paired full latency and calls including downstream variability; do not call faster failure a speedup'],
 'failure':'Record rejected candidates and errors. At most one schema/host-validation repair in fused entry; no legacy fallback for rejected eligible proposal. No rerun or product amendment after observing outcomes in this ADR.',
 'limits':{'requests':6,'repeats_per_arm_case':1,'model_attempts_per_request':40,'wall_seconds':1800,'output_tokens':6400},
 'controls':'Each request fresh process and isolated runtime; same source generation, authorized 65 public docs, model/provider, search/read/assessment/compose code and original request. Alternating paired order, no cProfile. OS cache not flushed. App setup time separate.',
 'quality':'Front intent/facts manual comparison and host accepted judgment/citation checks; no independent legal accuracy certification or approved gold recall.',
 'main':'unchanged; candidate only; no GENOS field execution'}
for name,v in [('dataset',dataset),('criteria',criteria),('baseline',{'pointer':pointer,'pointer_sha256':sha(pp),'release':release})]:put(D/(name+'.json'),v)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis='Fresh request front 4 calls -> 1 without losing original issues; measure full answer path rather than front-only latency.',primary_metric='Paired end-to-end request_seconds and physical model_calls, conditioned on completion and issue preservation',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,repeats=1)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
for arm in m['design']['arms']:
 arm.update(changes='Exact MAIN48 product code' if arm['id']=='baseline' else criteria['scope'],controls=criteria['controls'])
 m['design']['retrieval_stage_plan']['stages_by_arm'][arm['id']]=[{'stage_id':'catalogue','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'filter','parent_stage_ids':['catalogue']},{'stage_id':'presented','kind':'present','parent_stage_ids':['acquired']}]
m['runs'][0].update(selection_rule=dataset['selection'],artifact_path=str((A/'artifacts/run-001/summary.json').relative_to(R)))
m['dataset'].update(name='Fresh public statute entry paired probe',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'))
m['llm_policy']['llm_calls']=[x for x in m['llm_policy']['llm_calls'] if x['class']=='product']
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Search algorithm unchanged; altered entry-generated queries may change observed retrieval. Exact ledger measured for all requests.')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
for arm in ('fused-entry',):
 cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id',arm,'--experiment-id',m['experiment_id'],'--arm-id',arm,'--run-id','run-001']
 for name in sorted(set(release['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}):cmd+=['--source',name]
 subprocess.run(cmd,cwd=R,check=True)
