from common import *
import os,shutil,subprocess
b=read(DES/'baseline.json');f=read(DES/'freeze.json');gold=read(DES/'gold-before-integration.json')
root_test=read(ART/'checks-root-entry-api-002.json')
assert root_test['exit_code']==0 and root_test['passed']==2 and root_test['code_root']=='.'
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/n)==h for n,h in gold['files'].items())
OUT.mkdir(parents=True,exist_ok=True)
with (OUT/'adr-final.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py','validate','--path',str(ADR),'--final'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
q={'source':bind(ADR/'실험/manifest.json'),'readme':bind(ADR/'README.md'),'arm':'oracle-records',
 'result':bind(RUN/'result.json'),'rebase':bind(DES/'release-rebase.json')}
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'우리 그 온톨로지에 필요한거 빼고 상세 로그같은경우는 일단은 nfs에 두게 해줘; 온톨로지에 필요한 구조화된 내용은 그대로 오라클로 옮기고',
 'scope':'Keep structured ontology/resume records in Oracle and move raw diagnostics/detailed reports to NFS; preserve default NFS and original sources/model/Gold; select local MAIN. No field deployment/mail/Git push.',
 'quality_gate_override':False,'qualification':q,'rollback_pipeline':bind(ART/'working-pipeline-integrated.json')})
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':read(DES/'integration.json'),
 'technical_tests_passed':173,'same_existing_failures':14,'new_failures':0,
 'actual_root_oracle_service':bind(ART/'checks-root-entry-api-002.json'),
 'all_serving_files':495,'new_agent_tables':3,'new_agent_user_columns':21,
 'external_model_calls':0,'performance_certified':False,'quality_certified':False})
sys.path.insert(0,str(ROOT/'02_BACKEND'));from semantic_runtime.release_qualification import verify
verify(ROOT,read(OUT/'authorization.json'),read(OUT/'validation.json'))
with (OUT/'prepare.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare',
 '--code-root',str(ROOT/f['code_root']),'--generation',b['manifest']['data_path'],'--release-id',RELEASE,
 '--authorization',str(OUT/'authorization.json'),'--validation',str(OUT/'validation.json')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
manifest=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';release=read(manifest)
assert release['files']==f['files']
updated=dict(gold['binding']);updated.update(engine_root=release['code_root'],engine_files=release['files'],engine_release_id=RELEASE,
 engine_manifest_sha256=sha(manifest),data_path=release['data_path'],engine_candidate_revision=f['candidate_revision'],
 inference_status='ORACLE_AGENT_RECORDS_TECHNICAL_PASS_REAL_INFERENCE_NOT_RETESTED')
assert updated['connector_files']==gold['binding']['connector_files']
put(OUT/'gold-binding-prepared.json',updated)
rollback=OUT/'gold-before';rollback.mkdir();shutil.copy2(GOLD/'binding.json',rollback/'binding.json')
put(OUT/'rollback.json',{'prior_main':b['active'],'prior_gold':gold,'working_backup':read(ART/'working-integration.json')['backup'],
 'instructions':'Use official MAIN rollback and restore preserved Gold binding together. Preserve Oracle new records; no automatic reverse migration to NFS.'})
with (OUT/'apply.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply',
 '--manifest',str(manifest),'--confirm-main'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
temporary=GOLD/'binding.json.main128-tmp';assert not temporary.exists()
shutil.copy2(OUT/'gold-binding-prepared.json',temporary);os.replace(temporary,GOLD/'binding.json')
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert active['release_id']==RELEASE and active['generation']==128
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/n)==h for n,h in gold['files'].items() if n!=str((GOLD/'binding.json').relative_to(ROOT)))
put(OUT/'activation.json',{'active':active,'working_exact':True,'serving_files':495,
 'gold_binding':bind(GOLD/'binding.json'),'gold_connector_and_mapping_settings_preserved':True,
 'original_data_changed':False,'field_deployed':False,'actual_nfs_history_migrated':False})
print('Selected MAIN128',RELEASE,'with the same preserved Gold connector')
