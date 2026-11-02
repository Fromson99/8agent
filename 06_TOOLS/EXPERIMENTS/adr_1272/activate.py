from common import *
import subprocess,os,shutil
b=read(DES/'baseline.json');f=read(DES/'freeze.json');stage=read(DES/'stage.json')
test=read(ART/'prepared-api/result.json')
assert test['passed']==13 and test['failed']==0 and test['code_unchanged'] and test['active_pointer_unchanged']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(ROOT/n)==h for n,h in b['gold_files'].items())
compat=ROOT/'04_EXPERIMENTS/ADR/ADR-1273-gold-user-directed-main-binding/artifacts'
compat_test=read(compat/'tests.json');assert compat_test['passed']==16 and compat_test['failed']==0
cf=read(compat/'freeze.json');connector=ROOT/cf['target'];candidate_connector=ROOT/cf['code_root']/cf['target']
assert sha(connector)==cf['before'] and sha(candidate_connector)==cf['after']
manifest=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';r=read(manifest)
assert r['files']==stage['files'];assert all(sha(ROOT/n)==h for n,h in f['files'].items())
put(OUT/'gold-before.json',{'binding':b['gold_binding'],'files':b['gold_files']})
shutil.copyfile(connector,OUT/'gold-connector-before.py')
with (OUT/'apply.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',str(manifest),'--confirm-main'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
new=dict(b['gold_binding']);new.update(engine_root=r['code_root'],engine_files=r['files'],engine_release_id=RELEASE,
 engine_manifest_sha256=sha(manifest),engine_candidate_revision=f['candidate_revision'],
 inference_status='USER_DIRECTED_MAIN131_LOOP_QWEN_SQLITE_VERIFIED_ORACLE_WORKSPACE_NOT_CERTIFIED')
new['connector_files']=dict(new['connector_files']);assert 'connect.py' in new['connector_files']
new['connector_files']['connect.py']=cf['after']
new['main_authorization']={'release_id':RELEASE,'authorization_sha256':r['authorization_sha256'],'validation_sha256':r['validation_sha256']}
put(OUT/'gold-binding-prepared.json',new)
assert sha(GOLD/'binding.json')==b['gold_files'][str((GOLD/'binding.json').relative_to(ROOT))]
code_temp=GOLD/'connect.py.main131-tmp';shutil.copyfile(candidate_connector,code_temp);os.replace(code_temp,connector)
temp=GOLD/'binding.json.main131-tmp';shutil.copyfile(OUT/'gold-binding-prepared.json',temp);os.replace(temp,GOLD/'binding.json')
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert active['generation']==131 and active['release_id']==RELEASE
assert all(sha(ROOT/r['code_root']/n)==sha(ROOT/n)==h for n,h in r['files'].items())
assert all(sha(ROOT/n)==h for n,h in b['gold_files'].items() if n not in (cf['target'],str((GOLD/'binding.json').relative_to(ROOT))))
assert sha(connector)==cf['after']
put(OUT/'activation.json',{'active':active,'files':len(r['files']),'delta_files':stage['changed'],
 'all_current_serving_files_selected':True,'working_candidate_selected_exact':True,
 'gold_engine_same_release':True,'gold_physical_mapping_settings_unchanged':True,
 'gold_connector_authority_change':bind(compat/'freeze.json'),
 'data_generation_unchanged':r['data_path']==b['release']['data_path'],
 'main130_rollback':str((manifest.parent/'rollback/ACTIVE_RELEASE.json').relative_to(ROOT)),
 'new_model_calls':0,'oracle_data_or_ddl_changes':0,'genos_deployed':False,'git_pushed':False})
print('Selected MAIN131',RELEASE,'504 files; Gold engine aligned')
