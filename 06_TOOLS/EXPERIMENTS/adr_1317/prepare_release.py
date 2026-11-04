from common import *
import subprocess, shutil, importlib.util
OUT=ART/'main';OUT.mkdir(exist_ok=False)
RELEASE='oracle-development-vector-20261104-r1'
f=read(DES/'candidate-integrated.json');C=ROOT/f['code_root'];b=read(DES/'baseline.json')
before=b['working_files']
for name in ('oracle-actual-r2','boot-r2','native-oracle-r2'):
 r=read(ART/name/'result.json');assert r['passed']>0 and r['failed']==0 and r['code_unchanged']
r=read(ART/'regression-r2/result.json');assert r['passed']==68 and r['failed']==1
assert all(sha(C/n)==h for n,h in f['selected_files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer']
for n,h in before.items():assert sha(ROOT/n)==h,('Concurrent change',n)
changes={n:h for n,h in f['selected_files'].items() if before.get(n)!=h}
for n in changes:
 if n not in before:assert not (ROOT/n).exists()
 else:
  p=ART/'working-before'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
put(ART/'integration-preflight.json',{'before':{n:before.get(n) for n in changes},'after':changes,'candidate':f['pin']})
for n in changes:
 p=ROOT/n;temp=p.with_name('.'+p.name+'.adr1317');shutil.copyfile(C/n,temp);os.replace(temp,p)
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
put(ART/'working-integration.json',{'changed_files':len(changes),'changes':changes,'all540exact':True})
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
def command(log,args):
 with (OUT/log).open('x') as out:
  subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py',*args],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,check=True)
put(ART/'analysis.json',{'verified':True,'candidate':f['pin'],'actual_Oracle_contract':bind(ART/'oracle-actual-r2/result.json'),
 'regression':{'passed':68,'failed':1,'failure':'Test entry loaded workspace while workflow loaded candidate; same-code fixture passed 9/9'},
 'same_code_boot':bind(ART/'boot-r2/result.json'),'native_SQL_actual_Oracle':bind(ART/'native-oracle-r2/result.json'),
 'product_failure_fixed':'Model-free RAG_SEARCH attempted filesystem tempfile under Oracle logical runtime path',
 'PeCab_pyarrow_unchanged':True,'new_models':0,'field_deployed':False})
put(OUT/'preview-authorization.json',{'purpose':'integration_preview'});put(OUT/'preview-validation.json',{'structural_checks_passed':True})
command('preview.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE+'-preview','--authorization',str(OUT/'preview-authorization.json'),'--validation',str(OUT/'preview-validation.json'),'--integration-preview',str(OUT/'integration-preview.json')])
d=read(OUT/'integration-preview.json');stage=dict(b['release']['files'])
for row in d['changes']:
 assert row['after'] is not None and f['selected_files'][row['path']]==row['after']
 stage[row['path']]=row['after'];row['reason']='Development G19 Oracle vector publication/profile binding, no-file metadata search, native prepared SQL and engine hash closure; PeCab dependencies preserved.'
put(OUT/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':b['pointer']['release_manifest_sha256'],'candidate':f['pin'],'staged_files':stage,'excluded_candidate_paths':{n:'Build/research dependency outside serving closure; candidate retained' for n in set(f['selected_files'])-set(stage)}})
d.update(candidate=f['pin'],rebase_receipt=bind(OUT/'release-rebase.json'));put(OUT/'integration.json',d);put(OUT/'stage.json',{'files':stage,'count':len(stage),'changed':len(d['changes'])})
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'개발계에서 우리 메인이 잘 동작해야함 모든 데이터는 오라클에 있는거 써야해; 임포트 문제는 해결되었어 ... pyarrow이건 PeCab다운하면 된다고 확인되었어',
 'scope':'Local MAIN integration and development Oracle validation/handoff; PeCab unchanged','quality_gate_override':True,'deployment_basis':'USER_DIRECTED_CUTOVER','quality_certified':False,'no_implicit_external_deploy':True,
 'criteria':bind(DES/'criteria.json'),'rollback_pipeline':bind(ROOT/b['release']['code_root']/'00_SYSTEM/PIPELINE.json'),
 'known_limits':['GENOS/Dataiku field endpoints inaccessible; no field deployment','Embedding endpoint fixture verifies protocol, not real model identity/quality','All business data Oracle requires DP=oracle and explicit development mapping; local default preserved']})
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':d,'candidate':f['pin'],'verification':bind(ART/'analysis.json'),'serving_files':len(stage),'quality_certified':False,'model_calls':0})
command('prepare.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE,'--authorization',str(OUT/'authorization.json'),'--validation',str(OUT/'validation.json')])
p=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';r=read(p)
assert r['files']==stage and all(sha(ROOT/r['code_root']/n)==sha(ROOT/n)==h for n,h in stage.items())
put(DES/'candidate-prepared.json',{'code_root':r['code_root'],'selected_files':stage})
gold=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
put(OUT/'gold-before.json',{'binding':read(gold/'binding.json'),'files':{str(p.relative_to(ROOT)):sha(p) for p in gold.iterdir() if p.is_file() and p.suffix in ('.py','.json','.yaml')}})
print('Prepared',RELEASE,'serving',len(stage),'delta',len(d['changes']),'working',len(changes))
