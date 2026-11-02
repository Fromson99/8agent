from common import *
import os,shutil,subprocess
SOURCE_ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1248-oracle-safe-records-main'
SOURCE_RESULT=SOURCE_ADR/'artifacts/run-001/result.json'
b=read(DES/'baseline.json');f=read(DES/'freeze.json');gold=read(DES/'gold-before-integration.json')
root_test=read(ART/'checks-root-api.json')
assert root_test['exit_code']==0 and root_test['passed']==2 and root_test['code_root']=='.'
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/n)==h for n,h in gold['files'].items())
OUT.mkdir(parents=True,exist_ok=True)
with (OUT/'adr-final.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py','validate','--path',str(SOURCE_ADR),'--final'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
q={'source':bind(SOURCE_ADR/'실험/manifest.json'),'readme':bind(SOURCE_ADR/'README.md'),'arm':'selected',
 'result':bind(SOURCE_RESULT),'rebase':bind(DES/'release-rebase.json')}
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'수정해봐 — Oracle 기록 저장 증폭과 SQLite 충돌 수정; 앞서 요청한 메인 DP=oracle 연결 유지',
 'scope':'Fix Oracle persistence amplification and live RAM SQLite refresh; preserve structured authority, NFS diagnostics, default NFS, original schemas/model/Gold; select local MAIN. No field deployment/mail/Git push.',
 'quality_gate_override':False,'qualification':q,'rollback_pipeline':bind(ART/'working-pipeline-integrated.json')})
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':read(DES/'integration.json'),
 'technical_tests_passed':188,'same_existing_failures':14,'new_failures':0,
 'actual_root_oracle_service':bind(ART/'checks-root-api.json'),
 'all_serving_files':495,'new_agent_tables':0,'new_agent_user_columns':0,
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
 'instructions':'Before any v3 body is written, official rollback and preserved Gold binding may restore prior selection. After v3 writes, keep the v3-capable reader in a compatible recovery release or use an explicitly restored prior snapshot/namespace; never run v2-only MAIN128 over new v3 data. Preserve all new records; no reverse migration or delete.'})
with (OUT/'apply.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply',
 '--manifest',str(manifest),'--confirm-main'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
temporary=GOLD/'binding.json.main129-tmp';assert not temporary.exists()
shutil.copy2(OUT/'gold-binding-prepared.json',temporary);os.replace(temporary,GOLD/'binding.json')
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert active['release_id']==RELEASE and active['generation']==129
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/n)==h for n,h in gold['files'].items() if n!=str((GOLD/'binding.json').relative_to(ROOT)))
put(OUT/'activation.json',{'active':active,'working_exact':True,'serving_files':495,
 'gold_binding':bind(GOLD/'binding.json'),'gold_connector_and_mapping_settings_preserved':True,
 'original_data_changed':False,'field_deployed':False,'actual_nfs_history_migrated':False})
print('Selected MAIN129',RELEASE,'with the same preserved Gold connector')
