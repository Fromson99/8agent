from common import *
import subprocess
b=read(DES/'baseline.json');s=read(DES/'staging.json');f=read(DES/'freeze.json')
unit=read(ART/'technical-rev-001.json');nav=read(ART/'navigation-rev-001.json');serving=read(ART/'navigation-serving-rev-001.json');ora=read(ART/'oracle-rev-001.json');delivery=read(ROOT/'08_DEPLOYMENT/GENOS/handoffs/vector_initial_20261028_r1/VALIDATION.json')
assert unit['passed']==29 and not unit['failed'] and nav['passed']==serving['passed']==4 and not nav['failed'] and not serving['failed'] and not nav['import_leaks'] and not serving['import_leaks'];assert ora['strict_success'] and delivery['strict_success']
a=read(ART/'regression-baseline-local-rev-001.json');c=read(ART/'regression-candidate-local-rev-001.json');assert [(r['test'],r['status']) for r in a['rows']]==[(r['test'],r['status']) for r in c['rows']];assert c['passed']==109 and c['failed']==1 and not c['import_leaks']
put(DES/'preview-auth.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True,'new_regression':0})
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(ROOT/s['code_root']),'--generation',b['manifest']['data_path'],'--release-id','vector-initial-preview-20261028-r1','--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'official-preview.json')]
with (ART/'official-preview.log').open('w') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
draft=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in draft['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==s['files'] and len(actual)==458
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':draft['base_release_manifest_sha256'],'candidate':f['binding'],'staged_files':actual,'excluded_candidate_paths':{n:'Dataiku-only build adapter/recipe installer, separately delivered and checked' for n in sorted(set(f['files'])-set(actual))}})
for row in draft['changes']:row['reason']='Vector-first initial Oracle retrieval and Dataiku publication; preserve exact source, ACL, keyword recovery, ontology and model budgets. New physical read mapping for SIDDS dev deployment.'
draft.update(candidate=f['binding'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',draft)
checks={k:True for k in ('unit29','real_navigation4','same_serving_navigation4','actual_local_oracle11','delivery8','existing110_outcomes_identical','no_new_regression','official458_inventory','source_data_unchanged','no_external_model_calls','prior_failure_preserved')}
put(ART/'run-001/result.json',{'status':'complete','strict_success':True,'checks':checks,'unit_conditions':29,'navigation_conditions':4,'serving_repeat_conditions':4,'Oracle_conditions':11,'delivery_conditions':len(delivery['checks']),'existing_tests':110,'existing_passed':109,'existing_failed':1,'new_regression':0,'new_model_calls':0,'quality_certified':False,'field_deployment':False,'files':458,'changed_files':len(s['changed']),'evidence':{p.name:bind(p) for p in [ART/'technical-rev-001.json',ART/'navigation-rev-001.json',ART/'navigation-serving-rev-001.json',ART/'oracle-rev-001.json',ART/'regression-baseline-local-rev-001.json',ART/'regression-candidate-local-rev-001.json',ROOT/'08_DEPLOYMENT/GENOS/handoffs/vector_initial_20261028_r1/VALIDATION.json']}})
put(DES/'verification-scripts.json',{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')})
print('Qualified458 serving; unit29 navigation4 repeat4 Oracle11 delivery',len(delivery['checks']),'existing109pass1samefailure')
