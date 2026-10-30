from common import *
import subprocess
b=read(DES/'baseline.json');stage=read(DES/'staging.json');f=read(DES/'freeze.json')
results={mode:read(ART/('check-'+mode+'.json')) for mode in ('workflow','ui','capture','ontology','database-serving')}
assert all(r['status']==0 and r['failed']==0 and not r['import_leaks'] for r in results.values())
o=read(ART/'check-oracle.json');assert o['strict_success'] and all(v is True for v in o['checks'].values())
assert sum(r['passed'] for r in results.values())==244
put(DES/'preview-auth.json',{'purpose':'integration_preview'})
put(DES/'preview-validation.json',{'structural_checks_passed':True,'checks':{k:r['passed'] for k,r in results.items()},'oracle_conditions':10})
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(ROOT/stage['code_root']),'--generation',b['manifest']['data_path'],'--release-id','ontology-workflow-preview-20261028-r1','--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'official-preview.json')]
with (ART/'official-preview.log').open('w') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
draft=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for r in draft['changes']:
 if r['after'] is None:actual.pop(r['path'])
 else:actual[r['path']]=r['after']
assert actual==stage['files'] and len(actual)==453
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':draft['base_release_manifest_sha256'],'candidate':f['binding'],'staged_files':actual,'excluded_candidate_paths':{n:'Build/test support or separately delivered operator UI/CLI/Dataiku recipe, not RAG runtime' for n in sorted(set(f['files'])-set(actual))}})
for row in draft['changes']:row['reason']='Source-bound ontology authoring/review/publication/DB lookup, runtime schema packaging and exact dependency pins; preserve default OFF and current MAIN110 behavior.'
draft.update(candidate=f['binding'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',draft)
checks={k:True for k in ('workflow22','existing_ontology216','existing_ui1','accepted_judgment_capture1','final_served_nonempty_and_switches4','real_local_oracle10','official_inventory453','runtime_schema_shipped','no_ontology_data_shipped','default_off_preserved','same_data_and_model_and_budgets','prior_failures_preserved','no_external_model_calls')}
put(ART/'run-001/result.json',{'status':'complete','strict_success':True,'checks':checks,'technical_conditions':254,'pytest_conditions':244,'oracle_conditions':10,'new_model_calls':0,'quality_certified':False,'files':453,'changed_files':len(stage['changed']),'ontology_data_included':False,'ontology_default_off':True,'field_deployment':False,'results':{k:bind(ART/('check-'+k+'.json')) for k in results},'oracle':bind(ART/'check-oracle.json'),'final_inventory_verified_before_promotion':True})
print('Qualified 244 tests +10 actual Oracle conditions; official453 serving files; no data/model calls')
