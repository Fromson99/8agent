from pathlib import Path
import hashlib,itertools,json,shutil,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0838-comparison-judgment-qualification';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
P=R/'04_EXPERIMENTS/ADR/ADR-0837-comparison-advisory-items';assert read(P/'실험/manifest.json')['reservation']['status']=='completed'
v=read(P/'artifacts/design/verification-binding-final.json');old=R/v['code_root'];pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==78
release=read(R/pointer['manifest_path']);put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':release,'selected_release_manifest':release});put(D/'data-binding.json',{'path':release['data_path'],'manifest_sha256':release['data_manifest_sha256']})
cases=[{'case_id':f'judgment-{i:03d}','status':s,'comparison':c,'citation_mode':q,'expected_accepted':q in ('both','internal_only','external_only','none')} for i,(s,c,q) in enumerate(itertools.product(('CONFIRMED','PARTIAL','MISSING','CONFLICT'),('MATCH','DIFFERENT','UNKNOWN'),('both','internal_only','external_only','none','foreign_side','unknown','altered')),1)];assert len(cases)==84;put(D/'cases.json',cases)
criteria={'hypothesis':'Completed837 unchanged342files preserve model field opinions independently of selected-source presence while rejecting invalid source references across84 enumerated technical states.',
'success':['All84 candidate contracts pass; invalid citations accepted0 in both arms','Both arms13 actual-data service checks pass','Same completed837 code retains53 development passes and1 known model acceptance, without recounting them as holdout','No product edits after freeze; unchanged nativeRAG/source/hash/ACL/state code','Matrix under60seconds/2GiB; service under180seconds/12GiB'],
'failure':['foreign, invented or altered citation accepted','model opinion silently changed','wrong serving or data hashes','new service regression'],
'in_sample':False,'decision_eligible':True,'quality_certified':False,'real_model_calls':0,
'novelty':'Prospectively enumerated finite software contract census. Status/citation mechanics, not legal question holdout, retrieval or legal accuracy certification. Known development observations remain explicitly in-sample.',
'retained_development':{'result':str((P/'artifacts/run-001/result.json').relative_to(R)),'sha256':sha(P/'artifacts/run-001/result.json'),'code_binding_sha256':sha(P/'artifacts/design/verification-binding-final.json')},
'recovery':'Model adapter owns one structural repair; semantic opinion causes no repair. Source identity, ACL, hashes, state revisions and failed history remain mandatory.'};put(D/'criteria.json',criteria)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0838/connected';cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id','ADR-0838-experiment-v1','--arm-id','connected','--run-id','run-001']
for n in v['serving_files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for n in v['serving_files']:shutil.copy2(old/n,C/'snapshot'/n)
sys.path.insert(0,str(R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'));import adr_candidate;adr_candidate.refresh(C)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot';assert all(sha(code/n)==h for n,h in v['serving_files'].items())
put(D/'working-before.json',{x['target_path']:x['upstream_sha256'] for x in cm['files']});put(D/'verification-binding.json',{'code_root':str(code.relative_to(R)),'serving_files':v['serving_files'],'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Field opinion preservation and invalid source rejection technical census',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='Selected MAIN78' if arm['id']=='baseline' else 'Exact completed837rev001 unchanged342files',controls=['same data/profile','same literal source integrity','no new model generation'])
m['runs'][0].update(selection_rule='All84 declared technical states, both13 service checks, retain hashbound completed837 tests',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)));m['dataset'].update(name='comparison-opinion-finite-census',version='20261016-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
reason='Fixed synthetic contract states and exact citations; retrieval and legal correctness are not evaluated.';m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason;put(A/'실험/manifest.json',m)
for name in ('freeze.py','consumer_check.py','run_tests.py','test_judgment.py','test_workflow.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0837'/name).read_text().replace('adr_0837','adr_0838').replace('ADR-0837-comparison-advisory-items','ADR-0838-comparison-judgment-qualification').replace('ADR-0837-experiment-v1','ADR-0838-experiment-v1')
 if name=='freeze.py':s=s.replace("m['dataset']['sha256']=sha(D/'criteria.json')","m['dataset']['sha256']=sha(D/'cases.json')")
 (R/'06_TOOLS/EXPERIMENTS/adr_0838'/name).write_text(s)
print('Prepared84 technical states, unchanged completed837342files')
