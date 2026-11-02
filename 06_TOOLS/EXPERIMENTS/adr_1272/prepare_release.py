from common import *
import subprocess
f=read(DES/'freeze.json');b=read(DES/'baseline.json');stage=read(DES/'stage.json')
w=read(ART/'workspace-check.json');binding=read(ART/'workspace-code-binding.json')
assert w['passed']==110 and w['failed']==0 and all(binding['checks'].values())
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'지금까지 된거 메인에 싹다 반영해',
 'scope':'Select all current completed serving implementation including loop recovery, source review, and workspace; local MAIN and matching Gold engine binding only.',
 'quality_gate_override':True,'deployment_basis':'USER_DIRECTED_CUTOVER','quality_certified':False,
 'known_limits':['Previous response explained unresolved final-review422 and providerUNKNOWN504','Real injected Qwen recovery uses SQLite synthetic originals, not legal-quality holdout','Workspace real Oracle full compile/approval/RAG remains unverified; old Rejected records preserved'],
 'no_implicit_external_deploy':True,'criteria':bind(DES/'criteria.json')})
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':read(DES/'integration.json'),
 'current_loop':read(DES/'inherited-verification.json'),'workspace_check':bind(ART/'workspace-check.json'),
 'workspace_passed':110,'source_identity':bind(DES/'freeze.json'),'serving_files':stage['count'],
 'quality_certified':False,'new_model_calls':0,'oracle_data_or_ddl_changes':0})
with (OUT/'prepare.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(ROOT/f['code_root']),'--generation',b['release']['data_path'],'--release-id',RELEASE,'--authorization',str(OUT/'authorization.json'),'--validation',str(OUT/'validation.json')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
manifest=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';r=read(manifest)
assert r['files']==stage['files'] and r['deployment_basis']=='USER_DIRECTED_CUTOVER'
assert all(sha(ROOT/r['code_root']/n)==h==sha(ROOT/n) for n,h in r['files'].items())
assert r['data_path']==b['release']['data_path'] and r['data_manifest_sha256']==b['release']['data_manifest_sha256']
put(OUT/'prepared.json',{'release':bind(manifest),'files':len(r['files']),'changed':stage['changed'],
 'working_candidate_release_exact':True,'data_unchanged':True,'main_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']})
print('Prepared',RELEASE,len(r['files']),'files; activation pending selected-code API check')
