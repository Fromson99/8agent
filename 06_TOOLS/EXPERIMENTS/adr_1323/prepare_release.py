from common import *
import subprocess,shutil,runpy
OUT=ART/'main';OUT.mkdir(exist_ok=False)
RELEASE='genos-oracle-startup-20261104-r1'
f=read(DES/'candidate-integrated.json');C=ROOT/f['code_root'];b=read(DES/'baseline.json')
test=read(ART/'startup/result.json');assert test['failed']==1 and test['passed']==27 and test['code_unchanged']
base=read(ART/'baseline-existing/result.json');assert base['failed']==1 and base['passed']==21
assert [x['test'] for x in test['rows'] if x['outcome']=='failed']==[x['test'] for x in base['rows'] if x['outcome']=='failed']
assert 'PASS engines=30 files=497' in Path('/tmp/adr1323-engine.log').read_text()

working=b['working_files'];before=b['release']['files'];assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer']
assert all(sha(ROOT/n)==h for n,h in working.items()),'Concurrent working change'
assert all(sha(C/n)==h for n,h in f['selected_files'].items())
old=runpy.run_path(str(ROOT/b['release']['code_root']/'02_BACKEND/semantic_runtime/oracle_query_plans.py'))['PLANS']
new=runpy.run_path(str(C/'02_BACKEND/semantic_runtime/oracle_query_plans.py'))['PLANS']
def statements(plans):return {k:{a:b for a,b in v.items() if a!='sources'} for k,v in plans.items()}
assert statements(old)==statements(new)
changes={n:h for n,h in f['selected_files'].items() if before.get(n)!=h}
assert len(changes)==2
for n in changes:
 p=ART/'working-before'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
put(ART/'working-integration.json',{'before':{n:before[n] for n in changes},'after':changes,'unchanged_Oracle_plans':639})
for n in changes:
 p=ROOT/n;tmp=p.with_name('.'+p.name+'.adr1323');shutil.copyfile(C/n,tmp);os.replace(tmp,p)
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
def command(log,args):
 with (OUT/log).open('x') as out:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py',*args],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,check=True)
put(OUT/'preview-authorization.json',{'purpose':'integration_preview'});put(OUT/'preview-validation.json',{'structural_checks_passed':True})
command('preview.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE+'-preview','--authorization',str(OUT/'preview-authorization.json'),'--validation',str(OUT/'preview-validation.json'),'--integration-preview',str(OUT/'integration-preview.json')])
d=read(OUT/'integration-preview.json');stage=dict(before)
for row in d['changes']:
 assert row['after']==f['selected_files'][row['path']]
 stage[row['path']]=row['after'];row['reason']='Register the backend import path before Oracle diagnostics in the two standalone HTTP entrypoints; all other MAIN139 code and native SQL unchanged'
assert stage==f['selected_files']
put(OUT/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':b['pointer']['release_manifest_sha256'],'candidate':f['pin'],'staged_files':stage,'excluded_candidate_paths':{}})
d.update(candidate=f['pin'],rebase_receipt=bind(OUT/'release-rebase.json'));put(OUT/'integration.json',d);put(OUT/'stage.json',{'files':stage,'count':len(stage),'changed':len(d['changes'])})
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'개발계 Oracle MAIN 정상동작 및 TRANSFER 한줄설치 후 사용자가 제시한 start_sse ModuleNotFoundError 현장 오류 수정',
 'scope':'Local MAIN and replacement Samsung full-code one-bash handoff; field deployment separate','quality_gate_override':True,'deployment_basis':'USER_DIRECTED_CUTOVER','quality_certified':False,'no_implicit_external_deploy':True,
 'criteria':bind(DES/'criteria.json'),'rollback_pipeline':bind(ROOT/b['release']['code_root']/'00_SYSTEM/PIPELINE.json'),
 'known_limits':['No access to field GENOS endpoint','Other working multiturn edits are preserved and excluded from this MAIN139-based startup fix','No new legal quality or performance test']})
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':d,'candidate':f['pin'],'verification':bind(ART/'startup/result.json'),'serving_files':len(stage),'quality_certified':False,'model_calls':0,'unchanged_SQL_plans':639})
command('prepare.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE,'--authorization',str(OUT/'authorization.json'),'--validation',str(OUT/'validation.json')])
p=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';r=read(p);assert r['files']==stage
put(DES/'candidate-prepared.json',{'code_root':r['code_root'],'selected_files':stage})
gold=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
put(OUT/'gold-before.json',{'binding':read(gold/'binding.json'),'files':{str(p.relative_to(ROOT)):sha(p) for p in gold.iterdir() if p.is_file() and p.suffix in ('.py','.json','.yaml')}})
print('Prepared',RELEASE,'files',len(stage),'delta',len(changes))
