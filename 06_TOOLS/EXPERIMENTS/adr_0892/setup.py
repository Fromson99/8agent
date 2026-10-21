from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0892-verified-assessment-wire';P=R/'04_EXPERIMENTS/ADR/ADR-0891-definition-navigation-continuity';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(P/'실험/manifest.json')['reservation']['status']=='completed'
assert not (D/'criteria.json').exists()
base=read(P/'artifacts/design/baseline.json');before=read(P/'artifacts/design/working-before.json')
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']
assert all(sha(R/n)==h for n,h in before.items())
for n in ['baseline.json','working-before.json','data-binding.json','cases.json','offline-reference.json']:shutil.copy2(P/'artifacts/design'/n,D/n)
prior=read(P/'artifacts/followup-design.json');notes={'candidate_plan':prior['next_changes'],'checks':prior['tests']}
criteria={'hypothesis':'Canonical source identity verification runs before model-only assessment projection, retaining exact receipt and compact text on the same actual service path.',
 'design':notes['candidate_plan'],'required_contracts':notes['checks'],
 'success':['All8frozenCMcases attempted serially on same final candidate/model/data','Exact originals/ACL/hash/state/resume/budgets and actualserviceconsumer contracts retained','CM008subject/extension,CM003exclusion/classification,CM051operativeformula independently reviewed against actual selected originals','All newly discovered semantic misses and output omissions recorded, not hidden as data absence'],
 'failure':['Lost/fabricated original or citation identity, ACL/hash/state/deadline/duplicate regression','Required contracts/service binding failure or resource ceiling exceeded'],
 'limits':{'calls_per_case':40,'wall_seconds':1800,'final_reserve':3,'no_progress_recovery_per_request':1,'workers':1,'rss_gib':8,'as_gib':9},
 'recovery':{'owner':'Existing navigation and bounded_decision; one extra recovery selection with existing one repair, no new gateway retry','errors':'No-progress before new content delivery; invalid/missing document lookup; explicit source modality reversal','preserve':'Actual failed lookup, acquired versus presented status, immutable recovery snapshot, used budget/deadline and source receipts','final':'Existing bounded partial-original handoff with concrete missing items, never source absence proof'},
 'resource_policy':'GENOS_RESIDENT_DATA=off, original shared read-only SQLite, one worker, compressed exact histories, no dataset copies',
 'evaluation':'Same CM001/003/008/033/051 plus CM011/022/038 prospectively selected in0884 fromCM51. Historically exposed, no legal holdout or causal superiority claim. Later independent finite technical qualification required for MAIN.'}
put(D/'criteria.json',criteria)
parent=read(P/'artifacts/design/freeze.json');PC=R/parent['code_root'];cm=read(R/parent['candidate']['manifest_path'])
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','verified','--experiment-id','ADR-0892-experiment-v1','--arm-id','verified','--run-id','run-001']
for x in cm['files']:cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0892/verified/snapshot'
for n,h in before.items():
 if sha(PC/n)!=h:(C/n).write_bytes((PC/n).read_bytes())
m=read(A/'실험/manifest.json');m.update(in_sample=True,decision_eligible=False)
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Requested original access and useful final answer with bounded durable recovery',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'verified','role':'candidate','derived_from':['ADR-0891-experiment-v1/continuity'],'changes':criteria['design'],'controls':'SameMAIN86 data, frozenCM8, Qwen3.8ParasailFP8 reasoningnone nofallback,40calls1800s; no gold inproduct'}]
m['runs'][0].update(arm_ids=['verified'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'max_calls':320}]
m['dataset'].update(name='CM51 five known and three additional cases',version='cm-field-core-e2e-v3',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['design']['retrieval_stage_plan']['stages_by_arm']={'verified':[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
m['retrieval_accounting']['changed']=True;m['retrieval_accounting']['not_applicable_reason']=None
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),not_applicable_reason=None)
put(A/'실험/manifest.json',m)
print('MAIN86 exact; completed0891 inherited; criteria frozen before implementation')
