from common import *
import shutil,subprocess,sys
O=ROOT/'09_ARTIFACTS/AUDITS/20261028-vector-initial-main112';O.mkdir(parents=True,exist_ok=True)
b=read(DES/'baseline.json');s=read(DES/'staging.json');f=read(DES/'freeze.json');C=ROOT/f['code_root'];changed=s['changed'];operator=[n for n in f['files'] if n.startswith('08_DEPLOYMENT/DATAIKU/vector_initial_20261028_r1/') or n=='02_BACKEND/lawrag/pipeline/oracle_query_dataiku.py']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
for n in changed+operator:assert (sha(ROOT/n) if (ROOT/n).is_file() else None)==b['working_files'].get(n),'concurrent edit '+n
shutil.copyfile(ROOT/'00_SYSTEM/PIPELINE.json',O/'rollback-working-pipeline.json')
q={'source':bind(ADR/'실험/manifest.json'),'readme':bind(ADR/'README.md'),'arm':'integrated','result':bind(ART/'run-001/result.json'),'rebase':bind(DES/'release-rebase.json')}
put(O/'authorization.json',{'authorized_by':'user','authorization_text':'메인 변경하고 우리 딸깍으로 우리 구조화된 데이터를 벡터db에 적재할수 있게 만들고 삼성메일로 쏴줘','scope':'MAIN111 plus verified initial vector and resumable Dataiku publication. Source data/model/budgets unchanged; no field deployment claimed.','quality_gate_override':False,'qualification':q,'rollback_pipeline':bind(O/'rollback-working-pipeline.json')})
put(O/'validation.json',{'structural_checks_passed':True,'integration':read(DES/'integration.json'),'technical_conditions':44,'repeat_serving_conditions':4,'delivery_conditions':8,'existing_tests':110,'existing_failures_same':1,'new_regression':0,'new_model_calls':0,'quality_certified':False,'field_deployment':False})
sys.path.insert(0,str(ROOT/'02_BACKEND'));from semantic_runtime.release_qualification import verify
verify(ROOT,read(O/'authorization.json'),read(O/'validation.json'))
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(ROOT/s['code_root']),'--generation',b['manifest']['data_path'],'--release-id','vector-initial-20261028-r1','--authorization',str(O/'authorization.json'),'--validation',str(O/'validation.json')]
with (O/'prepare.log').open('w') as log:subprocess.run(cmd,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
manifest=ROOT/'08_DEPLOYMENT/RELEASES/vector-initial-20261028-r1/release.json';assert read(manifest)['files']==s['files']
status=subprocess.check_output(['git','status','--porcelain','-z'],cwd=ROOT).decode().split('\0');protected={v[3:]:sha(ROOT/v[3:]) for v in status if v and v[:2]!='??' and (ROOT/v[3:]).is_file() and v[3:] not in changed+operator}
for n in changed+operator:
 assert (sha(ROOT/n) if (ROOT/n).is_file() else None)==b['working_files'].get(n),'concurrent edit '+n
 if (ROOT/n).is_file():
  backup=O/'working-backup'/n;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,backup)
 dest=ROOT/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,dest)
assert all(sha(ROOT/n)==h for n,h in protected.items())
put(O/'working-integration.json',{'serving_changed':{n:sha(ROOT/n) for n in changed},'operator_files':{n:sha(ROOT/n) for n in operator},'protected_other_modified_files':protected,'protected_unchanged':True,'data_modified':False,'strategy':'exact baseline precondition, touched files only, backups; unrelated edits preserved'})
with (O/'apply.log').open('w') as log:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','apply','--manifest',str(manifest),'--confirm-main'],cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Selected MAIN',read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation'])
