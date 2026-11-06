from common import *
import subprocess
OUT=ART/'main';OUT.mkdir(exist_ok=False)
RELEASE='guided-answer-20261105-r1'
f=read(DES/'candidate-selected.json');C=ROOT/f['code_root'];b=read(DES/'baseline.json')
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer']
for p in ('final-service-contracts','working-contracts-r2'):
 r=read(ART/p/'result.json');assert r['failed']==0 and r['code_unchanged']
gold=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
put(OUT/'gold-before.json',{'binding':read(gold/'binding.json'),'files':{str(p.relative_to(ROOT)):sha(p) for p in gold.iterdir() if p.is_file() and p.suffix in ('.json','.py','.yaml')}})
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
def command(log,args):
 with (OUT/log).open('x') as out:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py',*args],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,check=True)
put(OUT/'preview-authorization.json',{'purpose':'integration_preview'});put(OUT/'preview-validation.json',{'structural_checks_passed':True})
command('preview.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE+'-preview','--authorization',str(OUT/'preview-authorization.json'),'--validation',str(OUT/'preview-validation.json'),'--integration-preview',str(OUT/'integration-preview.json')])
d=read(OUT/'integration-preview.json');stage=dict(b['release']['files'])
for row in d['changes']:
 assert row['after']==f['selected_files'][row['path']]
 stage[row['path']]=row['after'];row['reason']='User-directed guided final answer and clarification, no final semantic review or repair; same source and ACL boundaries. Known real Qwen omission limitations retained.'
assert stage==f['selected_files'] and len(stage)==531
put(OUT/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':b['pointer']['release_manifest_sha256'],'candidate':f['pin'],'staged_files':stage,'excluded_candidate_paths':{}})
d.update(candidate=f['pin'],rebase_receipt=bind(OUT/'release-rebase.json'));put(OUT/'integration.json',d);put(OUT/'stage.json',{'files':stage,'count':len(stage),'changed':len(d['changes'])})
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'메인에 반영하고 삼성메일로 쏴줘','scope':'Local MAIN151 and same Gold engine binding; prepare verified full code ZIP, execution TXT and guide and send to Samsung partner email. No access to GENOS field deployment.', 'quality_gate_override':True,'deployment_basis':'USER_DIRECTED_CUTOVER','quality_certified':False,'no_implicit_external_deploy':True,'criteria':bind(DES/'criteria.json'),'rollback_pipeline':bind(ROOT/b['release']['code_root']/'00_SYSTEM/PIPELINE.json'),'known_limits':['Actual CM003 four final-stage trials retained, latest explanation/question works but exception omission remains. Not legal quality certification. Actual full retrieval/multiturn not rerun; lifecycle is synthetic. Command/investigation model review and special workflows retained.']})
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':d,'candidate':f['pin'],'verification':bind(ART/'final-service-contracts/result.json'),'working_verification':bind(ART/'working-contracts-r2/result.json'),'serving_files':len(stage),'quality_certified':False,'actual_final_stage_result':bind(ART/'actual-final-r6/result.json'),'unchanged_SQL_plans':640,'new_SQL_plans':0})
command('prepare.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE,'--authorization',str(OUT/'authorization.json'),'--validation',str(OUT/'validation.json')])
p=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';r=read(p);assert r['files']==stage
put(DES/'candidate-prepared.json',{'code_root':r['code_root'],'selected_files':stage,'pin':f['pin']})
print('Prepared',len(stage),'files; changed',len(d['changes']),'MAIN still150')
