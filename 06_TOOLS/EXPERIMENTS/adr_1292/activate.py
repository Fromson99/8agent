from common import *
import subprocess,os,shutil
b=read(DES/'baseline.json');f=read(DES/'freeze.json');stage=read(DES/'stage.json')
test=read(ART/'prepared-api/result.json');package=read(OUT/'ui-package-check.json')
assert test['passed']==14 and test['failed']==0 and test['code_unchanged'] and test['active_unchanged']
assert package['passed']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['active_sha256']
assert all(sha(ROOT/n)==h for n,h in b['gold_files'].items())
p=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';r=read(p)
assert r['files']==stage['files'] and all(sha(ROOT/n)==h for n,h in f['files'].items())
put(OUT/'gold-before.json',{'binding':b['gold_binding'],'files':b['gold_files']})
with (OUT/'apply.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',str(p),'--confirm-main'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
new=dict(b['gold_binding']);new.update(engine_root=r['code_root'],engine_files=r['files'],engine_release_id=RELEASE,
 engine_manifest_sha256=sha(p),engine_candidate_revision=f['candidate_revision'],
 inference_status='USER_DIRECTED_MAIN134_CONSOLE_INTEGRATION_REAL_QWEN_NOT_CERTIFIED')
new['main_authorization']={'release_id':RELEASE,'authorization_sha256':r['authorization_sha256'],'validation_sha256':r['validation_sha256']}
put(OUT/'gold-binding-prepared.json',new)
assert sha(GOLD/'binding.json')==b['gold_files'][str((GOLD/'binding.json').relative_to(ROOT))]
temp=GOLD/'binding.json.main134-tmp';shutil.copyfile(OUT/'gold-binding-prepared.json',temp);os.replace(temp,GOLD/'binding.json')
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert active['generation']==134 and active['release_id']==RELEASE
assert all(sha(ROOT/r['code_root']/n)==sha(ROOT/n)==h for n,h in r['files'].items())
assert all(sha(ROOT/n)==h for n,h in b['gold_files'].items() if n!=str((GOLD/'binding.json').relative_to(ROOT)))
put(OUT/'activation.json',{'active':active,'files':len(r['files']),'delta_files':stage['changed'],
 'working_candidate_selected_exact':True,'gold_engine_same_release':True,
 'gold_mapping_settings_connector_unchanged':True,'data_generation_unchanged':True,
 'rollback_main133':str((p.parent/'rollback/ACTIVE_RELEASE.json').relative_to(ROOT)),
 'model_calls':0,'genos_deployed':False,'git_pushed':False,'ui_package':bind(OUT/'ui-package.json')})
print('Selected MAIN134,',len(r['files']),'serving files; Gold aligned; separate UI package verified')
