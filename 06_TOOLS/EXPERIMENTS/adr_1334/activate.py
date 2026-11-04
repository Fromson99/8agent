from common import *
import subprocess,shutil
OUT=ART/'main';GOLD=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
RELEASE='genos-gold-b003-20261104-r1'
f=read(DES/'candidate-integrated.json');b=read(DES/'baseline.json');old=read(OUT/'gold-before.json')
for name,count in [('prepared-contracts',36),('prepared-oracle',1)]:
 test=read(ART/name/'result.json');assert test['passed']==count and test['failed']==0 and test['exit_code']==0
assert 'PASS engines=30 files=500' in (ART/'prepared-engine.log').read_text()
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer']
assert all(sha(ROOT/n)==h for n,h in b['working_files'].items()),'Concurrent working change; leave MAIN unchanged'
assert all(sha(ROOT/n)==h for n,h in old['files'].items()),'Gold connector changed'
p=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';r=read(p)
assert all(sha(ROOT/r['code_root']/n)==h for n,h in r['files'].items())
with (OUT/'apply.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',str(p),'--confirm-main'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
binding={**old['binding'],'engine_root':r['code_root'],'engine_files':r['files'],'engine_release_id':RELEASE,
 'engine_manifest_sha256':sha(p),'engine_candidate_revision':f['pin'],
 'inference_status':'USER_DIRECTED_MAIN141_GOLD_MAPPING_FIELD_NOT_CERTIFIED',
 'main_authorization':{'release_id':RELEASE,'authorization_sha256':r['authorization_sha256'],'validation_sha256':r['validation_sha256']}}
put(OUT/'gold-binding-prepared.json',binding)
temp=GOLD/'binding.json.main141-tmp';shutil.copyfile(OUT/'gold-binding-prepared.json',temp);os.replace(temp,GOLD/'binding.json')
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert active['generation']==141 and active['release_id']==RELEASE
assert all(sha(ROOT/n)==h for n,h in b['working_files'].items())
assert all(sha(ROOT/n)==h for n,h in old['files'].items() if n!=str((GOLD/'binding.json').relative_to(ROOT)))
put(OUT/'activation.json',{'active':active,'files':len(r['files']),'own_product_files_selected_exact':True,'working_files_unchanged':True,'gold_same_engine':True,'Gold_mapping_publication_unchanged':True,
 'rollback_main140':str((p.parent/'rollback/ACTIVE_RELEASE.json').relative_to(ROOT)),
 'gold_rollback':str((OUT/'gold-before.json').relative_to(ROOT)),
 'prepared_checks':37,'model_calls':0,'field_deployed':False})
print('MAIN141 selected; Gold connector same engine; working code unchanged')
