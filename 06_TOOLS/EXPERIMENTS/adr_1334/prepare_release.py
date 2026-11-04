from common import *
import subprocess,runpy
OUT=ART/'main';OUT.mkdir(exist_ok=False)
RELEASE='genos-gold-b003-20261104-r1'
f=read(DES/'candidate-integrated.json');C=ROOT/f['code_root'];b=read(DES/'baseline.json')
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer']
assert all(sha(C/n)==h for n,h in f['selected_files'].items())
assert all(sha(ROOT/n)==h for n,h in b['working_files'].items())
old=runpy.run_path(str(ROOT/b['release']['code_root']/'02_BACKEND/semantic_runtime/oracle_query_plans.py'))['PLANS'];new=runpy.run_path(str(C/'02_BACKEND/semantic_runtime/oracle_query_plans.py'))['PLANS']
def sql(p):return {k:{a:b for a,b in v.items() if a!='sources'} for k,v in p.items()}
assert sql(old)==sql(new) and len(new)==639
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
def command(log,args):
 with (OUT/log).open('x') as out:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py',*args],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,check=True)
put(OUT/'preview-authorization.json',{'purpose':'integration_preview'});put(OUT/'preview-validation.json',{'structural_checks_passed':True})
command('preview.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE+'-preview','--authorization',str(OUT/'preview-authorization.json'),'--validation',str(OUT/'preview-validation.json'),'--integration-preview',str(OUT/'integration-preview.json')])
d=read(OUT/'integration-preview.json');stage=dict(b['release']['files'])
for row in d['changes']:
 assert row['after']==f['selected_files'][row['path']]
 stage[row['path']]=row['after'];row['reason']='Existing validated Gold B003 R5 mapping, explicit ORDS selection and same-request ontology; original Silver option and Agent records preserved'
assert stage==f['selected_files'] and len(d['changes'])==39
put(OUT/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':b['pointer']['release_manifest_sha256'],'candidate':f['pin'],'staged_files':stage,'excluded_candidate_paths':{}})
d.update(candidate=f['pin'],rebase_receipt=bind(OUT/'release-rebase.json'));put(OUT/'integration.json',d);put(OUT/'stage.json',{'files':stage,'count':len(stage),'changed':len(d['changes'])})
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'지금 메인에 반영해봐','scope':'Local MAIN promotion of the completed Gold B003 mapping change; field deployment separate','quality_gate_override':True,'deployment_basis':'USER_DIRECTED_CUTOVER','quality_certified':False,'no_implicit_external_deploy':True,'criteria':bind(DES/'criteria.json'),'rollback_pipeline':bind(ROOT/b['release']['code_root']/'00_SYSTEM/PIPELINE.json'),'known_limits':['Existing Gold technical verification is not new legal quality certification','Concurrent multiturn/assessment/workflow working changes are preserved and excluded','GENOS field inaccessible; no email or field deployment requested']})
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':d,'candidate':f['pin'],'verification':b['prior_validation'],'serving_files':len(stage),'quality_certified':False,'model_calls':0,'unchanged_SQL_plans':639})
command('prepare.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE,'--authorization',str(OUT/'authorization.json'),'--validation',str(OUT/'validation.json')])
p=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';r=read(p);assert r['files']==stage
put(DES/'candidate-prepared.json',{'code_root':r['code_root'],'selected_files':stage})
put(OUT/'gold-before.json',{'binding':b['gold_binding'],'files':b['gold_files']})
print('Prepared',RELEASE,'files528 delta39; no MAIN change yet')
