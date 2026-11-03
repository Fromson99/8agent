from common import *
import subprocess,os,shutil
b={**read(DES/'baseline.json'),**read(DES/'gold-before.json')};f=read(DES/'freeze.json');stage=read(DES/'stage.json')
test=read(ART/'prepared-api-r2/result.json')
assert test['passed']>0 and test['failed']==0 and test['code_unchanged']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['active_sha256']
assert all(sha(ROOT/n)==h for n,h in b['gold_files'].items())
p=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';r=read(p)
assert r['files']==stage['files'] and all(sha(ROOT/n)==h for n,h in f['files'].items())
put(OUT/'gold-before.json',{'binding':b['gold_binding'],'files':b['gold_files']})
with (OUT/'apply.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',str(p),'--confirm-main'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
new=dict(b['gold_binding']);new.update(engine_root=r['code_root'],engine_files=r['files'],engine_release_id=RELEASE,
 engine_manifest_sha256=sha(p),engine_candidate_revision=f['candidate_revision'],
 inference_status='USER_DIRECTED_MAIN136_QUERY_OPTIMIZATION_REAL_QWEN_NOT_CERTIFIED')
new['main_authorization']={'release_id':RELEASE,'authorization_sha256':r['authorization_sha256'],'validation_sha256':r['validation_sha256']}
put(OUT/'gold-binding-prepared.json',new)
assert sha(GOLD/'binding.json')==b['gold_files'][str((GOLD/'binding.json').relative_to(ROOT))]
temp=GOLD/'binding.json.main136-tmp';shutil.copyfile(OUT/'gold-binding-prepared.json',temp);os.replace(temp,GOLD/'binding.json')
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert active['generation']==136 and active['release_id']==RELEASE
assert all(sha(ROOT/r['code_root']/n)==sha(ROOT/n)==h for n,h in r['files'].items())
assert all(sha(ROOT/n)==h for n,h in b['gold_files'].items() if n!=str((GOLD/'binding.json').relative_to(ROOT)))
put(OUT/'activation.json',{'active':active,'files':len(r['files']),'delta_files':stage['changed'],
 'working_candidate_selected_exact':True,'gold_engine_same_release':True,
 'gold_mapping_settings_connector_unchanged':True,'data_generation_unchanged':True,
 'rollback_main135':str((p.parent/'rollback/ACTIVE_RELEASE.json').relative_to(ROOT)),
 'model_calls':0,'genos_deployed':False,'git_pushed':False})
print('Selected MAIN136,',len(r['files']),'serving files; Gold aligned; original data/settings preserved')
