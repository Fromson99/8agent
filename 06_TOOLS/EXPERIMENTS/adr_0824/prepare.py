from pathlib import Path
import json,hashlib,shutil,subprocess,sys
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0824-comparison-partial-live-check';D=A/'artifacts/design';D.mkdir(exist_ok=True);T=Path(__file__).parent
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
parent=R/'02_BACKEND/lawrag/research/candidates/adr_0822/connected';pc=read(parent/'candidate.json');old=parent/'revisions/rev-003/snapshot';C=R/'02_BACKEND/lawrag/research/candidates/adr_0824/observed'
for name in ('baseline.json','data-binding.json'):shutil.copy2(R/'04_EXPERIMENTS/ADR/ADR-0823-comparison-partial-qualification/artifacts/design'/name,D/name)
cases=[c for c in read(R/'04_EXPERIMENTS/ADR/ADR-0817-risk-main76-live-e2e/artifacts/design/cases.json') if c['id']=='risk-104'];put(D/'cases.json',cases)
criteria={'hypothesis':'Actual model executes the new field review and returns grounded content or explicit missing fields through selected candidate service; known diagnostic only.',
 'success':['terminal durable response','field result rows present even if original source missing','own-side citations verify','latest attempt and valid result retained independently','saved status/duplicate no new calls'],
 'limits':{'physical_calls':40,'wall_seconds':1800,'outer_timeout':1920},'in_sample':True,'decision_eligible':False,
 'semantic_rubric':'Report what actual liquidity ratio sources establish and separate absent internal source and any unsupported or irrelevant evidence. Do not certify compliance or accuracy from transport/schema success.',
 'model':'qwen/qwen3.8-27b','provider':'Parasail','fallback':False,'selection':'original registered risk104, one scheduled run, no adaptive retries; old0817 observed result is context only, not a paired effect benchmark','quality_certified':False}
put(D/'criteria.json',criteria)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','observed','--experiment-id','ADR-0824-experiment-v1','--arm-id','observed','--run-id','run-001']
for x in pc['files']:
 if (R/x['target_path']).exists():cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for x in pc['files']:
 n=x['target_path'];p=C/'snapshot'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/n,p)
 if not (R/n).exists():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',n,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
sys.path.insert(0,str(R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'));import adr_candidate
adr_candidate.refresh(C);subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
m=read(A/'실험/manifest.json');m.update(in_sample=True,decision_eligible=False);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual model and consumer execution with source-grounded partial disclosure',success_criteria=criteria['success'],failure_criteria=['missing fields/citations','consumer state lost','schema or native failure preserved'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='Historical MAIN76 context only; no rerun' if arm['id']=='baseline' else 'Exact822rev003 with real model physical sends through ExperimentClient',controls=['immutable code and data','selected global budget','same authorization'])
m['runs'][0].update(artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)),arm_ids=['observed'],selection_rule=criteria['selection'],status='planned')
m['dataset'].update(name='risk_cm-known-risk104',version='20261016-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,production_paths_modified_before_decision=False,runtime_import_allowed=False,production_registry_registered=False,main_wiring_unchanged=True,candidates=[{'candidate_id':'observed','arm_id':'observed','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str((T/'live.py').relative_to(R)),'runner_sha256':sha(T/'live.py')}])
m['llm_policy']['llm_calls']=[{'role':'actual_workflow_and_native_rag','class':'product','model':criteria['model'],'repeats':1,'temperature':'selected runtime value'}]
plans=[{'stage_id':'native_read','kind':'source','parent_stage_ids':[]},{'stage_id':'child_adopted','kind':'select','parent_stage_ids':['native_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['child_adopted']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'baseline':plans,'observed':plans};m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None);put(A/'실험/manifest.json',m)
files={str((code/x['target_path']).relative_to(R)):sha(code/x['target_path']) for x in cm['files']}
files.update({str(p.relative_to(R)):sha(p) for p in list(T.glob('*.py'))+list(D.glob('*.json'))+[R/'02_BACKEND/lawrag/research/experiment_client.py']})
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'files':files,'code_root':str(code.relative_to(R)),'serving_files':{x['target_path']:sha(code/x['target_path']) for x in cm['files']}})
print('Frozen one real-model diagnostic request')
