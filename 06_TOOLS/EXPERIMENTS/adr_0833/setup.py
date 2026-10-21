from pathlib import Path
import hashlib, itertools, json, shutil, subprocess, sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0833-compact-delivery-qualification';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
parent=R/'04_EXPERIMENTS/ADR/ADR-0832-compact-evidence-delivery'
assert read(parent/'실험/manifest.json')['reservation']['status']=='completed'
v=read(parent/'artifacts/design/verification-binding-final.json');old=R/v['code_root']
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==77
release=read(R/pointer['manifest_path'])
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':release,'selected_release_manifest':release})
put(D/'data-binding.json',{'path':release['data_path'],'manifest_sha256':release['data_manifest_sha256']})
cases=[{'case_id':f'delivery-{i:03d}','length':n,'unicode':u,'lines':lines,'rebound':r,'scope':s}
 for i,(n,u,lines,r,s) in enumerate(itertools.product((1,1199,1200,1201,2401),(False,True),(1,3),(False,True),('same','foreign_document','foreign_source','unread')),1)]
assert len(cases)==160
put(D/'cases.json',cases)
criteria={'hypothesis':'Unchanged completed832rev005 records exactly the compact subspans delivered under current source identity; rejects unread or foreign evidence across all160 declared technical combinations.',
 'success':['all160 candidate cases pass','baseline observation is explicit; no baseline false positive','both arms13 real-data service checks pass','completed832 exact same342files retain317passed and same6preexisting common failures','no runtime edits after freeze','all frozen code/data hashes and publication validator unchanged','matrix under60seconds/2GiB; each service under180seconds/12GiB'],
 'failure':['foreign source accepted','wrong text or position recorded','publication checks relaxed','frozen candidate changed','new regression failure'],
 'in_sample':False,'decision_eligible':True,'quality_certified':False,'real_model_calls':0,
 'novelty':'Prospectively enumerated finite technical census; no legal cases or statistical holdout claim. Parent developmental tests remain known regressions.',
 'retained_development':{'result':str((parent/'artifacts/run-001/result.json').relative_to(R)),'sha256':sha(parent/'artifacts/run-001/result.json'),'code_binding_sha256':sha(parent/'artifacts/design/verification-binding-final.json')},
 'recovery':'Exact option receipt construction owns integrity failures; gateway owns send success; no extra retries, source or budget changes.'}
put(D/'criteria.json',criteria)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0833/connected'
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id','ADR-0833-experiment-v1','--arm-id','connected','--run-id','run-001']
for n in v['serving_files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for n in v['serving_files']:shutil.copy2(old/n,C/'snapshot'/n)
sys.path.insert(0,str(R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'));import adr_candidate
adr_candidate.refresh(C)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
assert all(sha(code/n)==h for n,h in v['serving_files'].items())
put(D/'working-before.json',{x['target_path']:x['upstream_sha256'] for x in cm['files']})
put(D/'verification-binding.json',{'code_root':str(code.relative_to(R)),'serving_files':v['serving_files'],'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact delivered span and source identity technical census',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='Selected MAIN77' if arm['id']=='baseline' else 'Exact completed832rev005 unchanged342files',controls=['same data/profile','no model or semantic prompt changes'])
m['runs'][0].update(selection_rule='All160 enumerated technical states; both13service checks; retain hashbound completed832 tests',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='compact-exact-delivery-finite-census',version='20261016-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
reason='Only exact fixed original spans and delivery receipts; no retrieval or legal accuracy comparison.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(A/'실험/manifest.json',m)
print('Prepared160 cases; unchanged completed832rev005')
