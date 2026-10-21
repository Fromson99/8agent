from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0894-mixed-source-modality';P=R/'04_EXPERIMENTS/ADR/ADR-0893-reference-delivery-continuity';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(P/'실험/manifest.json')['reservation']['status']=='completed'
assert not (D/'freeze.json').exists()
base=read(P/'artifacts/design/baseline.json');before=read(P/'artifacts/design/working-before.json')
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']
assert all(sha(R/n)==h for n,h in before.items())
for n in ['baseline.json','working-before.json','data-binding.json','cases.json','offline-reference.json']:shutil.copy2(P/'artifacts/design'/n,D/n)
prior=read(P/'artifacts/followup-design.json');notes={'candidate_plan':prior['next_changes'],'checks':prior['tests']}
criteria={'hypothesis':'Explicit obligation connective 하되 must participate in mixed-modality detection; the same full source paragraph may contain both obligation and permission without a false global contradiction.',
 'design':notes['candidate_plan'],'required_contracts':notes['checks'],
 'success':['Same8frozenCMquestions attempted serially on exactfinalcandidate/model/data','Correct mixed45dayobligation and60daypermission source survives assessment; true single-modality reversals remain rejected','All582retained same-code contracts and new mixedmodalitycases pass; exact originals ACL/hash/state/resume/budgets remain strict','CM008search/termination,CM003classification,CM051formula/scope all independently reviewed; semantic misses remainexplicit'],
 'failure':['Source ACL hash state budget or consumerregression','Mixedsource falsepositive remains or true single-modality reversal incorrectlyaccepted','Resource ceiling exceeded'],
 'run_order':['cm-033', 'cm-001', 'cm-003', 'cm-008', 'cm-051', 'cm-011', 'cm-022', 'cm-038'],
 'limits':{'calls_per_case':40,'wall_seconds':1800,'final_reserve':3,'workers':1,'rss_gib':8,'as_gib':9},
 'recovery':{'owner':'Existing assessment one repair only','preserve':'No automatic legalconclusion; mixed recognized modal endings remainUNSPECIFIED; sourcequote and ID validation unchanged','final':'Existing bounded original handoff and result statuses; no failure masking'},
 'resource_policy':'GENOS_RESIDENT_DATA=off, sharedread-only data,oneworker,compressed exacthistory',
 'evaluation':'SameCM001/003/008/033/051 plusCM011/022/038 selectedprospectivelyin0884. In-sample diagnostic replay, not legalholdout. Independent finite technicalqualification after completion.'}
put(D/'criteria.json',criteria)
parent=read(P/'artifacts/design/freeze.json');PC=R/parent['code_root'];cm=read(R/parent['candidate']['manifest_path'])
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','mixed','--experiment-id','ADR-0894-experiment-v1','--arm-id','mixed','--run-id','run-001']
for x in cm['files']:cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0894/mixed/snapshot'
for n,h in before.items():
 if sha(PC/n)!=h:(C/n).write_bytes((PC/n).read_bytes())
m=read(A/'실험/manifest.json');m.update(in_sample=True,decision_eligible=False)
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Requested original access and useful final answer with bounded durable recovery',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'mixed','role':'candidate','derived_from':['ADR-0893-experiment-v1/references'],'changes':criteria['design'],'controls':'SameMAIN86 data, frozenCM8, Qwen3.8ParasailFP8 reasoningnone nofallback,40calls1800s; no gold inproduct'}]
m['runs'][0].update(arm_ids=['mixed'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'max_calls':320}]
m['dataset'].update(name='CM51 five known and three additional cases',version='cm-field-core-e2e-v3',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['design']['retrieval_stage_plan']['stages_by_arm']={'mixed':[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
m['retrieval_accounting']['changed']=True;m['retrieval_accounting']['not_applicable_reason']=None
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),not_applicable_reason=None)
put(A/'실험/manifest.json',m)
print('MAIN86 exact; completed0893 inherited; criteria frozen before implementation')
