from common import *
import subprocess,shutil,runpy
OUT=ART/'main';OUT.mkdir(exist_ok=False)
RELEASE='genos-embed-env-20261104-r1'
f=read(DES/'candidate-integrated.json');C=ROOT/f['code_root'];b=read(DES/'baseline.json')
test=read(ART/'final-contracts/result.json');assert test['failed']==0 and test['passed']==60 and test['code_unchanged']
assert 'PASS engines=30 files=497' in Path('/tmp/adr1320-engine-r2.log').read_text()
assert 'Checked 639' in Path('/tmp/adr1320-native-check-r2.log').read_text()
before=b['working_files'];assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer']
assert all(sha(ROOT/n)==h for n,h in before.items()),'Concurrent working change'
assert all(sha(C/n)==h for n,h in f['selected_files'].items())
old=runpy.run_path(str(ROOT/b['release']['code_root']/'02_BACKEND/semantic_runtime/oracle_query_plans.py'))['PLANS']
new=runpy.run_path(str(C/'02_BACKEND/semantic_runtime/oracle_query_plans.py'))['PLANS']
def statements(plans):return {k:{a:b for a,b in v.items() if a!='sources'} for k,v in plans.items()}
assert statements(old)==statements(new)
changes={n:h for n,h in f['selected_files'].items() if before.get(n)!=h}
assert len(changes)==35
for n in changes:
 p=ART/'working-before'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
put(ART/'working-integration.json',{'before':{n:before[n] for n in changes},'after':changes,'unchanged_Oracle_plans':639})
for n in changes:
 p=ROOT/n;tmp=p.with_name('.'+p.name+'.adr1320');shutil.copyfile(C/n,tmp);os.replace(tmp,p)
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
def command(log,args):
 with (OUT/log).open('x') as out:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py',*args],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,check=True)
put(OUT/'preview-authorization.json',{'purpose':'integration_preview'});put(OUT/'preview-validation.json',{'structural_checks_passed':True})
command('preview.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE+'-preview','--authorization',str(OUT/'preview-authorization.json'),'--validation',str(OUT/'preview-validation.json'),'--integration-preview',str(OUT/'integration-preview.json')])
d=read(OUT/'integration-preview.json');stage=dict(before)
for row in d['changes']:
 assert row['after']==f['selected_files'][row['path']]
 stage[row['path']]=row['after'];row['reason']='User-confirmed GENOS embedding ID/TOKEN names, optional Oracle profile pin, gateway model selection; native SQL and engine pins regenerated without query changes'
assert stage==f['selected_files']
put(OUT/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':b['pointer']['release_manifest_sha256'],'candidate':f['pin'],'staged_files':stage,'excluded_candidate_paths':{}})
d.update(candidate=f['pin'],rebase_receipt=bind(OUT/'release-rebase.json'));put(OUT/'integration.json',d);put(OUT/'stage.json',{'files':stage,'count':len(stage),'changed':len(d['changes'])})
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'개발계에서 우리 메인이 잘 동작해야함 모든 데이터는 오라클에 있는거; 프로필 그거 차피 같은거라던데 걍 안넣게; GENOS_EMBED_ID하고 GENOS_EMBED_TOKEN 필요함 승호님 코드 봐봐',
 'scope':'Local MAIN and replacement Samsung full-code one-bash handoff; field deployment separate','quality_gate_override':True,'deployment_basis':'USER_DIRECTED_CUTOVER','quality_certified':False,'no_implicit_external_deploy':True,
 'criteria':bind(DES/'criteria.json'),'rollback_pipeline':bind(ROOT/b['release']['code_root']/'00_SYSTEM/PIPELINE.json'),
 'known_limits':['No access to field GENOS endpoint','Same actual ingestion/query embedding identity confirmed by user, not auto-proven by hash/dimensions','No new legal quality or performance test']})
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':d,'candidate':f['pin'],'verification':bind(ART/'final-contracts/result.json'),'serving_files':len(stage),'quality_certified':False,'model_calls':0,'unchanged_SQL_plans':639})
command('prepare.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE,'--authorization',str(OUT/'authorization.json'),'--validation',str(OUT/'validation.json')])
p=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';r=read(p);assert r['files']==stage
put(DES/'candidate-prepared.json',{'code_root':r['code_root'],'selected_files':stage})
gold=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
put(OUT/'gold-before.json',{'binding':read(gold/'binding.json'),'files':{str(p.relative_to(ROOT)):sha(p) for p in gold.iterdir() if p.is_file() and p.suffix in ('.py','.json','.yaml')}})
print('Prepared',RELEASE,'files',len(stage),'delta',len(changes))
