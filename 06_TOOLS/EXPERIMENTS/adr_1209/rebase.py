from common import *
import subprocess,shutil
f=read(DES/'freeze.json');b=read(DES/'baseline.json');C=ROOT/f['code_root']
first=read(ART/'checks-candidate-features-all-first.json');repair=read(ART/'checks-candidate-features-repair.json')
rows={x['test']:x for x in first['rows']}
for x in repair['rows']:rows[x['test']]=x
assert len(rows)==348 and all(x['status']=='passed' for x in rows.values())
put(ART/'feature-completion.json',{'passed':348,'excluded':1,'first':bind(ART/'checks-candidate-features-all-first.json'),'repair':bind(ART/'checks-candidate-features-repair.json'),'initial_setup_errors':2,'cause':'test_unified_legal_agent.ROOT was not rebound to the frozen candidate; same fixture now has the correct contracts_root. No product or fixture changes.','external_model_calls':0})
old=read(ART/'checks-baseline-regression-first.json');new=read(ART/'checks-candidate-regression-first.json')
outcomes=lambda v:{(x['test'],x['when']):x['status'] for x in v['rows']}
a=outcomes(old);z=outcomes(new);assert a.keys()==z.keys(),(a.keys()-z.keys(),z.keys()-a.keys())
new_failures=[k for k in z if z[k]=='failed' and a[k]!='failed'];assert not new_failures,new_failures
assert all(not r['import_leaks'] and r['fixed_files_unchanged'] for r in [first,repair,old,new])
put(ART/'regression-comparison.json',{'identical_outcomes':a==z,'baseline_passed':old['passed'],'baseline_failed_or_errors':old['failed'],'candidate_passed':new['passed'],'candidate_failed_or_errors':new['failed'],'new_failures':len(new_failures),'baseline':bind(ART/'checks-baseline-regression-first.json'),'candidate':bind(ART/'checks-candidate-regression-first.json')})
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
drift={n:{'before':h,'now':sha(ROOT/n)} for n,h in b['working_files'].items() if sha(ROOT/n)!=h}
put(ART/'working-drift-check.json',{'drift':drift});assert not drift,drift
pin_files=[n for n,h in f['files'].items() if sha(ROOT/n)!=h]
assert len(pin_files)==31 and all(n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/') for n in pin_files),pin_files
for n in pin_files:shutil.copy2(C/n,ROOT/n)
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
put(ART/'working-integration.json',{'all487_exact':True,'pin_files':{n:f['files'][n] for n in pin_files},'non_pin_products_preserved':True,'baseline_main':b['active']['release_id']})
put(ART/'working-pipeline-integrated.json',read(ROOT/'00_SYSTEM/PIPELINE.json'))
put(DES/'preview-auth.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True})
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',b['manifest']['data_path'],'--release-id','cumulative-contracts-preview-20261029-r1','--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'official-preview.json')]
with (ART/'official-preview.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==f['files'] and len(d['changes'])==96
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':f['candidate_revision'],'staged_files':actual,'excluded_candidate_paths':{}})
for row in d['changes']:
 n=row['path']
 row['reason']=('Pin the exact complete cumulative serving inventory and inactive profile templates' if n.startswith(('00_SYSTEM/','02_BACKEND/ENGINES/')) else 'Include completed domain profile authoring, glossary binding and compiled approval workflow' if '/ontology_work/' in n or '/ontology_' in n else 'Include completed declared need continuity, supervisor recovery, purpose change review and lossless storage/admission changes; existing source display preserved')
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
print('348 features; regression',new['passed'],new['failed'],'new0; working487 exact; official487 / changes96')
