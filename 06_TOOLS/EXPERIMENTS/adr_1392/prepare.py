from common import *
import subprocess,runpy
OUT=ART/'main';OUT.mkdir(exist_ok=False)
RELEASE='bound-chat-review-20261105-r1'
f=read(DES/'candidate-integrated.json');C=ROOT/f['code_root'];b=read(DES/'baseline.json')
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer']
assert all(sha(C/n)==h for n,h in f['selected_files'].items())

old=runpy.run_path(str(ROOT/b['release']['code_root']/'02_BACKEND/semantic_runtime/oracle_query_plans.py'))['PLANS'];new=runpy.run_path(str(C/'02_BACKEND/semantic_runtime/oracle_query_plans.py'))['PLANS']
def sql(p):return {k:{a:b for a,b in v.items() if a!='sources'} for k,v in p.items()}
assert len(old)==639 and len(new)==640 and set(old)<set(new)
assert all(sql(old)[key]==sql(new)[key] for key in old)
assert read(DES/'native-plan-equivalence.json')['new_review_plans']==1
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
def command(log,args):
 with (OUT/log).open('x') as out:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py',*args],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,check=True)
put(OUT/'preview-authorization.json',{'purpose':'integration_preview'});put(OUT/'preview-validation.json',{'structural_checks_passed':True})
command('preview.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE+'-preview','--authorization',str(OUT/'preview-authorization.json'),'--validation',str(OUT/'preview-validation.json'),'--integration-preview',str(OUT/'integration-preview.json')])
d=read(OUT/'integration-preview.json');stage=dict(b['release']['files'])
for row in d['changes']:
 assert row['after']==f['selected_files'][row['path']]
 stage[row['path']]=row['after'];row['reason']='Reviewed chat action, isolated UI function, native lookup plan and corresponding engine hashes only'
intent=read(DES/'intent.json')
allowed=set(intent['products']+[intent['native'],'00_SYSTEM/PIPELINE.json']) | {row['manifest'] for row in read(C/'00_SYSTEM/PIPELINE.json')['engines'].values()}
assert stage==f['selected_files'] and {row['path'] for row in d['changes']}==allowed and len(allowed)==36
put(OUT/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':b['pointer']['release_manifest_sha256'],'candidate':f['pin'],'staged_files':stage,'excluded_candidate_paths':{}})
d.update(candidate=f['pin'],rebase_receipt=bind(OUT/'release-rebase.json'));put(OUT/'integration.json',d);put(OUT/'stage.json',{'files':stage,'count':len(stage),'changed':len(d['changes'])})
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'이거 메인에 반영해봐','scope':'Select local MAIN146 for the validated bound chat retry feature and match its local Gold engine binding','quality_gate_override':True,'deployment_basis':'USER_DIRECTED_CUTOVER','quality_certified':False,'no_implicit_external_deploy':True,'criteria':bind(DES/'criteria.json'),'rollback_pipeline':bind(ROOT/b['release']['code_root']/'00_SYSTEM/PIPELINE.json'),'known_limits':['A different code binding can require a fresh original question','No GENOS field deployment or new external model quality evaluation']})
evidence=read(ART/'candidate-review/result.json')
assert evidence['exit_code']==0 and evidence['code_unchanged'] and evidence['passed']==39
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':d,'candidate':f['pin'],'verification':bind(ART/'candidate-review/result.json'),'serving_files':len(stage),'quality_certified':False,'model_calls':0,'unchanged_SQL_plans':639,'new_SQL_plans':1})
command('prepare.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE,'--authorization',str(OUT/'authorization.json'),'--validation',str(OUT/'validation.json')])
p=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';r=read(p);assert r['files']==stage
put(DES/'candidate-prepared.json',{'code_root':r['code_root'],'selected_files':stage})
put(OUT/'gold-before.json',{'binding':b['gold_binding'],'files':b['gold_files']})
print('Prepared',RELEASE,'files528 delta36; no MAIN change yet')
