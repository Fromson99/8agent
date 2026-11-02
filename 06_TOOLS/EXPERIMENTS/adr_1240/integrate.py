from common import *
import shutil,subprocess,re
b=read(DES/'baseline.json');f=read(DES/'freeze.json');C=ROOT/f['code_root'];result=read(ART/'checks-initial.json');prior=read(ART/'checks-existing-failures.json')
failed={r['test']:r for r in result['rows'] if r['status']=='failed'};old={r['test']:r for r in prior['rows'] if r['status']=='failed'};assert set(failed)==set(old) and len(failed)==8
normal=lambda s:re.sub(r'_workflow_[0-9a-f]+','_workflow_SELECTED',s.splitlines()[-1])
assert all(normal(failed[k]['error'])==normal(old[k]['error']) for k in failed)
assert result['passed']==114 and read(ART/'consumer-candidate-off.json')['passed']
for name in ('consumer-verification','ontology-verification','scope-verification'):
 v=read(ART/'gold-candidate'/(name+'.json'));assert v.get('passed') or v.get('status')=='PASS' or v.get('paths')==9
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(ROOT/n)==h for n,h in b['working_files'].items()) and all(sha(ROOT/n)==h for n,h in b['gold_files'].items())
changes=[n for n,h in f['files'].items() if sha(ROOT/n)!=h];pins=[n for n in changes if n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/')];products=[n for n in changes if n not in pins];assert len(pins)==31 and len(products)==3
put(ART/'contract-summary.json',{'passed':114,'existing_failed':8,'new_failures':0,'rows':result['rows'],'same_failure_tests':list(old),'comparison':'Exact final error messages; only dynamic workflow import namespace hash normalized because code root paths differ','new_models':0})
put(ART/'port-decision.json',{'status':'NOT_ADOPTED_PERFORMANCE_CANDIDATE','reason':'Kind narrowing preserved values but paired physical reads remained about1second; no demonstrated benefit. Original maintained Gold connector stays byte-identical. Engine scope-key API fix is independently adopted.','pairs':read(ART/'gold-candidate/scope-verification.json')['pairs'],'selected_connector_files':b['gold_binding']['connector_files']})
for n in changes:shutil.copy2(C/n,ROOT/n)
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
put(ART/'working-integration.json',{'all489_exact':True,'changed_files':{n:f['files'][n] for n in changes},'products':products,'pins':pins,'baseline_main':b['active']['release_id'],'gold_connector_changed':False})
put(ART/'working-pipeline-integrated.json',read(ROOT/'00_SYSTEM/PIPELINE.json'));put(DES/'preview-auth.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True})
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',b['manifest']['data_path'],'--release-id','oracle-scope-preview-20261030-r1','--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'official-preview.json')]
with (ART/'official-preview.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==f['files'] and len(d['changes'])==34
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':f['candidate_revision'],'staged_files':actual,'excluded_candidate_paths':{}})
for row in d['changes']:row['reason']='Exact serving inventory pin' if row['path'] in pins else 'Typed SQLite/Oracle selected unit scope port with exact source, ACL and publication hash checks; no model/ranking change'
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
print('Integrated product3+pin31=34; MAIN124 and original Gold connector still selected')
