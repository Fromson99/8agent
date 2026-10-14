"""Freeze the fresh-request-only comparison before implementation and calls."""
from pathlib import Path
import hashlib, json, subprocess

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0707-grounded-law-title-entry'; D=A/'artifacts/design'
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
dataset={'cases':[{'case_id':'front-statute-001','question':prior['cases'][1]['question']},*cm['cases'],
 {'case_id':'body-content-001','question':'감사인에게 재무제표를 제출하는 기한이 어떻게 되나요? 정기총회 전에 제출하는 경우를 설명해 주세요.'}],
 'product_gold':False,'scope':'Public legislation only, synthetic body question; no private CM question export.',
 'selection':'Known exact law + CM018 abbreviation/background + public body phrase without law title; in-sample engineering probe.',
 'order':[['baseline','front-statute-001'],['title-entry','front-statute-001'],['title-entry','cm-018'],['baseline','cm-018'],['baseline','body-content-001'],['title-entry','body-content-001']]}
criteria={'scope':'Extend completed ADR0706 fused front with ACL-filtered actual law-title/registered-alias/partial/derived-abbreviation span hints and first STRUCTURE or FULLTEXT choice in the same call. Preserve original task and quoted background separately. Structure and fulltext remain selectable thereafter.',
 'success':['Actual title and original question spans are provided without an additional model call; partial/derived abbreviation is not registered alias or legal evidence',
 'Exact coordinate and abbreviated CM questions can choose STRUCTURE; body detail can choose FULLTEXT first, without mandatory structure lookup',
 'Preserve requested issue; background must not create an additional application obligation; full paragraph structure requires all subtree text/pages delivered',
 'All physical calls, repairs, tokens, per-call latency and full API response time are recorded; report failures without speedup claims',
 'ACL, citation, state binding and complete reads retained; no unauthorized title hints; no MAIN change'],
 'failure':'At most one front contract repair; no hidden provider or legacy fallback. Preserve all failed results. No tuning or rerun after observing outcomes in this ADR.',
 'limits':{'requests':6,'repeats_per_arm_case':1,'model_attempts_per_request':40,'wall_seconds':1800,'output_tokens':6400},
 'controls':'Baseline exact completed ADR0706 fused-entry; both inherit MAIN48. Each request fresh process/runtime, same 65 public docs/generation and Qwen/Parasail policy. Alternating order; OS cache not flushed. No adaptive difficulty budget.',
 'quality':'Engineering trace and source extent inspection; no approved gold or legal accuracy certification. This combined front+tool candidate does not isolate causal attribution of individual changes.',
 'main':'unchanged; isolated candidate only; GENOS not executed'}
for name,v in [('dataset',dataset),('criteria',criteria),('baseline',{'pointer':pointer,'pointer_sha256':sha(pp),'release':release})]:put(D/(name+'.json'),v)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis='Actual title span hints ground one-pass request understanding and optional search-tool choice without additional model routing.',primary_metric='Paired end-to-end request_seconds and physical model_calls, conditioned on completion and issue preservation',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,repeats=1)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
for arm in m['design']['arms']:
 arm.update(changes='Exact completed ADR0706 fused-entry candidate; MAIN48 selected baseline recorded separately' if arm['id']=='baseline' else criteria['scope'],controls=criteria['controls'])
 m['design']['retrieval_stage_plan']['stages_by_arm'][arm['id']]=[{'stage_id':'catalogue','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'filter','parent_stage_ids':['catalogue']},{'stage_id':'presented','kind':'present','parent_stage_ids':['acquired']}]
m['runs'][0].update(selection_rule=dataset['selection'],artifact_path=str((A/'artifacts/run-001/summary.json').relative_to(R)))
m['dataset'].update(name='Fresh public statute entry paired probe',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'))
m['llm_policy']['llm_calls']=[x for x in m['llm_policy']['llm_calls'] if x['class']=='product']
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
for arm in ('title-entry',):
 cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id',arm,'--experiment-id',m['experiment_id'],'--arm-id',arm,'--run-id','run-001']
 for name in sorted(set(release['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}):cmd+=['--source',name]
 subprocess.run(cmd,cwd=R,check=True)

# Carry only parent differences from the verified MAIN48 files, never overwrite working product files.
import shutil
parent=R/'02_BACKEND/lawrag/research/candidates/adr_0706/fused-entry/revisions/rev-001/snapshot'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0707/title-entry'; S=C/'snapshot'
for p in parent.rglob('*'):
 if p.is_file() and '__pycache__' not in p.parts:
  target=S/p.relative_to(parent);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target','02_BACKEND/semantic_runtime/legal_agent/request_entry.py','--upstream-state','absent'],cwd=R,check=True)
