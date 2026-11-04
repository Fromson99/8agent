from common import *
import subprocess,shutil
OUT=ART/'main';GOLD=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';RELEASE='genos-oracle-startup-20261104-r1'
f=read(DES/'candidate-integrated.json');old=read(OUT/'gold-before.json');test=read(ART/'prepared-api/result.json')
assert test['passed']==6 and test['failed']==0 and test['code_unchanged']
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'baseline.json')['pointer']
assert all(sha(ROOT/n)==h for n,h in old['files'].items())
assert all(sha(ROOT/n)==h for n,h in read(ART/'working-integration.json')['after'].items())
assert all(sha(ROOT/n)==h for n,h in read(DES/'baseline.json')['working_files'].items() if n not in read(ART/'working-integration.json')['after'])
p=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';r=read(p)
with (OUT/'apply.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',str(p),'--confirm-main'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
b={**old['binding'],'engine_root':r['code_root'],'engine_files':r['files'],'engine_release_id':RELEASE,'engine_manifest_sha256':sha(p),'engine_candidate_revision':f['pin'],
 'inference_status':'USER_DIRECTED_MAIN140_ORACLE_DEVELOPMENT_VECTOR_FIELD_NOT_CERTIFIED',
 'main_authorization':{'release_id':RELEASE,'authorization_sha256':r['authorization_sha256'],'validation_sha256':r['validation_sha256']}}
put(OUT/'gold-binding-prepared.json',b);temp=GOLD/'binding.json.main140-tmp';shutil.copyfile(OUT/'gold-binding-prepared.json',temp);os.replace(temp,GOLD/'binding.json')
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert active['generation']==140 and active['release_id']==RELEASE
assert all(sha(ROOT/r['code_root']/n)==h for n,h in r['files'].items())
assert all(sha(ROOT/n)==h for n,h in old['files'].items() if n!=str((GOLD/'binding.json').relative_to(ROOT)))
put(OUT/'activation.json',{'active':active,'files':len(r['files']),'own_working_changes_candidate_selected_exact':True,'other_workspace_changes_preserved':True,'gold_same_engine':True,'Gold_mapping_publication_unchanged':True,
 'rollback_main139':str((p.parent/'rollback/ACTIVE_RELEASE.json').relative_to(ROOT)),'gold_rollback':str((OUT/'gold-before.json').relative_to(ROOT)),'model_calls':0,'field_deployed':False})
print('MAIN140 selected; Gold binding aligned; field deployment not executed')
