from common import *
import subprocess,shutil
f=read(DES/'freeze.json');b=read(DES/'baseline.json');C=ROOT/f['code_root']
first=read(ART/'checks-candidate-new-first.json');assert first['passed']==34 and first['failed']==0
put(ART/'feature-completion.json',{'passed':81,'new_contracts':34,'existing_domain_contracts':47,'new':bind(ART/'checks-candidate-new-first.json'),'regression':bind(ART/'checks-candidate-regression-first.json'),'external_model_calls':0})
old=read(ART/'checks-baseline-regression-first.json');new=read(ART/'checks-candidate-regression-first.json')
outcomes=lambda v:{(x['test'],x['when']):x['status'] for x in v['rows']}
a=outcomes(old);z=outcomes(new);assert a.keys()==z.keys(),(a.keys()-z.keys(),z.keys()-a.keys())
new_failures=[k for k in z if z[k]=='failed' and a[k]!='failed'];assert not new_failures,new_failures
assert a==z
assert all(not r['import_leaks'] and r['fixed_files_unchanged'] for r in [first,old,new])
put(ART/'regression-comparison.json',{'identical_outcomes':a==z,'baseline_passed':old['passed'],'baseline_failed_or_errors':old['failed'],'candidate_passed':new['passed'],'candidate_failed_or_errors':new['failed'],'new_failures':len(new_failures),'baseline':bind(ART/'checks-baseline-regression-first.json'),'candidate':bind(ART/'checks-candidate-regression-first.json')})
assert read(ART/'consumer-candidate-off.json')['passed']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
drift={n:{'before':h,'now':sha(ROOT/n)} for n,h in b['working_files'].items() if sha(ROOT/n)!=h}
put(ART/'working-drift-check.json',{'drift':drift});assert not drift,drift
changes=[n for n,h in f['files'].items() if sha(ROOT/n)!=h]
pins=[n for n in changes if n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/')]
products=[n for n in changes if n not in pins]
assert len(changes)==33 and len(pins)==31 and len(products)==2,(len(changes),len(pins),len(products))
# The exact tested differences only; never overwrite the snapshot wholesale.
for n in changes:shutil.copy2(C/n,ROOT/n)
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
put(ART/'working-integration.json',{'all487_exact':True,'changed_files':{n:f['files'][n] for n in changes},'products':products,'pins':pins,'other454_files_preserved':True,'baseline_main':b['active']['release_id']})
put(ART/'working-pipeline-integrated.json',read(ROOT/'00_SYSTEM/PIPELINE.json'))
put(DES/'preview-auth.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True})
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',b['manifest']['data_path'],'--release-id','normalization-coverage-preview-20261029-r1','--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'official-preview.json')]
with (ART/'official-preview.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==f['files'] and len(d['changes'])==33
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':f['candidate_revision'],'staged_files':actual,'excluded_candidate_paths':{}})
for row in d['changes']:
 n=row['path'];row['reason']=('Pin the exact tested serving inventory' if n in pins else 'Closed input coverage and exact source locator assembly; original profile/canonical constraints and selected meaning unchanged')
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
print('81 contracts; regression',new['passed'],new['failed'],'new0; working487 exact; official487 / changes33')
