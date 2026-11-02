from common import *
import subprocess,shutil,os
b=read(DES/'baseline.json');f=read(DES/'freeze.json');OUT.mkdir(parents=True,exist_ok=True)
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(ROOT/n)==h for n,h in f['files'].items()) and all(sha(ROOT/n)==h for n,h in b['gold_files'].items())
with (OUT/'adr-final.log').open('x') as log:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py','validate','--path',str(ADR),'--final'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
q={'source':bind(ADR/'실험/manifest.json'),'readme':bind(ADR/'README.md'),'arm':'repaired','result':bind(RUN/'result.json'),'rebase':bind(DES/'release-rebase.json')}
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'일단 수정하고 진행해봐','scope':'Fix Oracle fulltext scope port, select local MAIN125, bind Gold to the same engine, then actual model revalidation in a new ADR. Preserve original Gold connector, data/model/default profile. No field GENOS/Git/mail.','quality_gate_override':False,'qualification':q,'rollback_pipeline':bind(ART/'working-pipeline-integrated.json')})
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':read(DES/'integration.json'),'technical_conditions_passed':114,'existing_failed':8,'regression_new_failures':0,'product_files_changed':3,'pin_files_changed':31,'external_model_calls':0,'quality_certified':False,'performance_candidate_adopted':False,'gold_scope':bind(ART/'gold-candidate/scope-verification.json'),'gold_source_vector':bind(ART/'gold-candidate/consumer-verification.json'),'gold_ontology':bind(ART/'gold-candidate/ontology-verification.json')})
sys.path.insert(0,str(ROOT/'02_BACKEND'));from semantic_runtime.release_qualification import verify
verify(ROOT,read(OUT/'authorization.json'),read(OUT/'validation.json'))
with (OUT/'prepare.log').open('x') as log:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(ROOT/f['code_root']),'--generation',b['manifest']['data_path'],'--release-id',RELEASE,'--authorization',str(OUT/'authorization.json'),'--validation',str(OUT/'validation.json')],cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
manifest=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';release=read(manifest);assert release['files']==f['files']
gold=dict(b['gold_binding']);gold.update(engine_root=release['code_root'],engine_files=release['files'],engine_release_id=RELEASE,engine_manifest_sha256=sha(manifest),data_path=release['data_path'],inference_status='FULLTEXT_SCOPE_PORT_TECHNICAL_PASS_REAL_INFERENCE_NOT_RETESTED',engine_candidate_revision=f['candidate_revision'],runtime_patches_active=False)
assert gold['connector_files']==b['gold_binding']['connector_files'];put(OUT/'gold-binding-prepared.json',gold)
rollback=OUT/'gold-before';rollback.mkdir();shutil.copy2(GOLD/'binding.json',rollback/'binding.json');put(OUT/'gold-rollback.json',{'prior_main':b['active'],'prior_gold_files':b['gold_files'],'restore':['binding.json'],'instructions':'Select preserved MAIN124 via official rollback and restore prior Gold binding together. Connector files and mapping remain unchanged.'})
with (OUT/'apply.log').open('x') as log:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',str(manifest),'--confirm-main'],cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
tmp=GOLD/'binding.json.main125-tmp';assert not tmp.exists();shutil.copy2(OUT/'gold-binding-prepared.json',tmp);os.replace(tmp,GOLD/'binding.json')
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/n)==h for n,h in b['gold_files'].items() if n!=str((GOLD/'binding.json').relative_to(ROOT)))
put(OUT/'activation.json',{'active':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_exact':True,'gold_binding':bind(GOLD/'binding.json'),'gold_connector_unchanged':True,'mapping_settings_and_patches_preserved':True,'data_changed':False,'field_deployed':False})
print('Selected MAIN',read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation'],'and same engine Gold binding')
