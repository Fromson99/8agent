from pathlib import Path
import json,hashlib,shutil,subprocess,sys
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0821-comparison-task-confirmation';D=A/'artifacts/design';D.mkdir(exist_ok=True);T=Path(__file__).parent;P=R/'04_EXPERIMENTS/ADR/ADR-0819-comparison-task-qualification';PC=R/'02_BACKEND/lawrag/research/candidates/adr_0819/connected';C=R/'02_BACKEND/lawrag/research/candidates/adr_0821/connected'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
oldf=read(P/'artifacts/design/freeze.json');old=R/oldf['code_root'];pc=read(PC/'candidate.json')
for name in ('baseline.json','data-binding.json','working-before.json'):shutil.copy2(P/'artifacts/design'/name,D/name)
inherited=[P/'artifacts/run-001/result.json',P/'artifacts/design/freeze.json',P/'artifacts/design/cases.json',P/'artifacts/design/criteria.json',P/'실험/manifest.json',P/'README.md']
inherited+=list((P/'artifacts').glob('matrix-*.json'))+list((P/'artifacts').glob('regression-*.log'))+list((P/'artifacts').glob('*.time'))+[P/'artifacts/api.log',P/'artifacts/api-journals.tar.gz',P/'artifacts/candidate-consumer-v2.json',P/'artifacts/baseline-consumer-v2.json']
put(D/'inherited.json',{str(p.relative_to(R)):sha(p) for p in inherited})
criteria={'hypothesis':'Confirm unchanged software and exact originally prospective finite-census evidence without regrading; repair missing run artifact link in this new record only.',
 'success':['all inherited raw records hash-exact and internally consistent','same342 serving files as819','original154 census all pass,27API pass,208 common pass and exactsame6 baseline failures','fresh candidate service13 checks and180s/12GiB limits','active MAIN unchanged'],
 'scope':'Administrative and source-binding confirmation of the originally prospective software-contract evidence. No new legal holdout or effect measurement and no relabeling of prior failures.',
 'parent_defect':'0819 run-001 artifact_path remained TODO; final metadata validation failed. Completed parent remains unchanged.',
 'decision_basis':'Originally frozen and observed819 finite technical census plus fresh identical-code service checks; no quality override, no semantic accuracy certification.'}
put(D/'criteria.json',criteria)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id','ADR-0821-experiment-v1','--arm-id','connected','--run-id','run-001']
for x in pc['files']:
 if (R/x['target_path']).exists():cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for x in pc['files']:
 n=x['target_path'];p=C/'snapshot'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/n,p)
 if not (R/n).exists():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',n,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
sys.path.insert(0,str(R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'));import adr_candidate
adr_candidate.refresh(C);subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
for name in ('consumer_check.py','integrate.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0819'/name).read_text().replace('ADR-0819-comparison-task-qualification','ADR-0821-comparison-task-confirmation').replace('adr0819-consumer-','adr0821-consumer-');(T/name).write_text(s)
put(D/'verification-binding.json',{'code_root':str(code.relative_to(R)),'serving_files':oldf['serving_files'],'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact frozen-code/evidence confirmation and actual service checks',success_criteria=criteria['success'],failure_criteria=['changed prior record','code mismatch','consumer failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='Inherited exact MAIN76 observations' if arm['id']=='baseline' else 'Identical completed819 candidate; no source/prompt/data edits',controls=['raw records and original classification unchanged','same code and data','actual model0'])
m['runs'][0].update(selection_rule='All declared inherited records plus one fresh actual candidate service process',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='immutable-comparison-contract-records',version='20261016-v1',frozen_source=str((D/'inherited.json').relative_to(R)),sha256=sha(D/'inherited.json'),legal_version_checked=False,reference_version_checked=False)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,production_paths_modified_before_decision=False,runtime_import_allowed=False,production_registry_registered=False,main_wiring_unchanged=True,candidates=[{'candidate_id':'connected','arm_id':'connected','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str((T/'consumer_check.py').relative_to(R)),'runner_sha256':sha(T/'consumer_check.py')}])
reason='Immutable result and code-binding audit, not a retrieval experiment; no regrading or new retrieval quality measurement. Fresh service route is a connection check.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(A/'실험/manifest.json',m)
files={str(p.relative_to(R)):sha(p) for p in list(T.glob('*.py'))+list(D.glob('*.json'))+[C/'candidate.json']}
put(D/'freeze.json',{**read(D/'verification-binding.json'),'frozen_at':datetime.now(timezone.utc).isoformat(),'files':files})
print('Confirmation inputs frozen; no completed819 record changed')
