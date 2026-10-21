from pathlib import Path
import json,hashlib,shutil,subprocess,sys,itertools
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0846-source-return-boundary';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
P=R/'04_EXPERIMENTS/ADR/ADR-0845-source-terminal-qualification';assert read(P/'실험/manifest.json')['reservation']['status']=='completed';v=read(P/'artifacts/design/verification-binding-final.json');old=R/v['code_root']
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['generation']==80;m=read(R/p['manifest_path']);put(D/'baseline.json',{'pointer':p,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':m,'selected_release_manifest':m});put(D/'data-binding.json',{'path':m['data_path'],'manifest_sha256':m['data_manifest_sha256']});put(D/'working-before.json',{n:sha(R/n) if (R/n).exists() else None for n in v['serving_files']})
cases=[{'id':f'boundary-{i:02d}','internal':inside,'external':outside,'bounded':bounded,'interrupted':interrupted} for i,(inside,outside,bounded,interrupted) in enumerate(itertools.product((False,True),(False,True),(False,True),(False,True)),1)];put(D/'cases.json',cases)
criteria={'hypothesis':'The exact completed845 code normally returns zero, one-sided or two-sided originals, including bounded stop and interruption, without legal-answer completion.',
 'success':['All16 prospectively frozen original-availability/budget/interruption API states pass','Exact344 completed845 files retained unchanged','60 valid retained845 contracts pass; its invalid empty-query fixture is retained as failed history and excluded explicitly','Working API and selected-data service checks pass; exact qualified code is selected by local MAIN'],
 'failure':['Actual original lost or altered','Source return promotes legal answer/experience','Duplicate resets budget or makes extra physical calls','ACL/hash/state integrity bypassed'],
 'in_sample':False,'decision_eligible':True,'quality_certified':False,'real_model_calls':0,
 'novelty':'New16 finite API boundary states with empty tool results explicitly fixed. Not legal holdout questions. Prior60passing contracts are regression only; known844 model run is development evidence.',
 'parent_result':{'path':str((P/'artifacts/run-001/result.json').relative_to(R)),'sha256':sha(P/'artifacts/run-001/result.json')},
 'recovery':'Single native correction owner, persisted parent budget/deadline and exact original receipts; terminal replay reuses committed work.',
 'planned_product_changes':[]};put(D/'criteria.json',criteria)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0846/qualified';cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','qualified','--experiment-id','ADR-0846-experiment-v1','--arm-id','qualified','--run-id','run-001']
for n in v['serving_files']:
 if (R/n).exists():cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for n in v['serving_files']:
 dest=C/'snapshot'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/n,dest)
 if not (R/n).exists():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',n,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Finite source-terminal and nonblocking API contracts',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='Selected MAIN80' if arm['id']=='baseline' else criteria['hypothesis'],controls=['same selected data/profile/model policy','no product model calls or legal truth labels'])
m['runs'][0].update(arm_ids=['qualified'],selection_rule=criteria['novelty'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)));m['dataset'].update(name='source-terminal-finite-api-states',version='20261016-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
reason='Finite software state census with synthetic model proposals; no retrieval or legal accuracy metric.';m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason;put(A/'실험/manifest.json',m)
for name in ('integrate.py','consumer_check.py','working_consumer.py','prepare_verified_promotion.py'):
 t=(T.parent/'adr_0842'/name).read_text().replace('adr_0842','adr_0846').replace('ADR-0842-comparison-execution-qualification','ADR-0846-source-return-boundary').replace('direct-comparison-20261016-r1','source-return-comparison-20261016-r1').replace("'arm':'connected'","'arm':'qualified'").replace('113 passed','76 passed')
 (T/name).write_text(t)
t=(T.parent/'adr_0844/run_tests.py').read_text().replace('adr_0844/sources','adr_0846/qualified');(T/'run_tests.py').write_text(t)
print(C)
