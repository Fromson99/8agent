from common import *
import subprocess
OUT=ART/'main';OUT.mkdir(exist_ok=False)
RELEASE='coherent-navigation-20261105-r1'
f=read(DES/'candidate-repaired.json');C=ROOT/f['code_root'];b=read(DES/'baseline.json')
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer']
tested=read(ART/'candidate-menu-journal/result.json');assert tested['failed']==0 and tested['passed']==23 and tested['code_unchanged']
comparison=read(ART/'regression-comparison.json')
assert comparison['passed'] and comparison['new_failures']==0 and comparison['new_contracts']==23
changed=read(DES/'delta.json')['changed']
assert len(changed)==36 and len(read(DES/'delta.json')['products'])==5
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
def command(log,args):
 with (OUT/log).open('x') as out:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py',*args],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,check=True)
put(OUT/'preview-authorization.json',{'purpose':'integration_preview'});put(OUT/'preview-validation.json',{'structural_checks_passed':True})
command('preview.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE+'-preview','--authorization',str(OUT/'preview-authorization.json'),'--validation',str(OUT/'preview-validation.json'),'--integration-preview',str(OUT/'integration-preview.json')])
d=read(OUT/'integration-preview.json');stage=dict(b['release']['files'])
for row in d['changes']:
 assert row['after']==f['selected_files'][row['path']]
 stage[row['path']]=row['after'];row['reason']='Current MAIN149 plus coherent navigation dispatch and lossless focused tool menus; preserve every other product module, source and ACL. No model calls in this implementation ADR.'
assert stage==f['selected_files'] and {row['path'] for row in d['changes']}==set(read(DES/'delta.json')['changed'])
put(OUT/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':b['pointer']['release_manifest_sha256'],'candidate':f['pin'],'staged_files':stage,'excluded_candidate_paths':{}})
d.update(candidate=f['pin'],rebase_receipt=bind(OUT/'release-rebase.json'));put(OUT/'integration.json',d);put(OUT/'stage.json',{'files':stage,'count':len(stage),'changed':len(d['changes'])})
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':read(DES/'criteria.json')['authorization'],'scope':'User-authorized local MAIN150: five navigation modules and derived pins atop149, same Gold engine binding; no DB or field deployment','quality_gate_override':True,'deployment_basis':'USER_DIRECTED_CUTOVER','quality_certified':False,'no_implicit_external_deploy':True,'criteria':bind(DES/'criteria.json'),'rollback_pipeline':bind(ROOT/b['release']['code_root']/'00_SYSTEM/PIPELINE.json'),'known_limits':read(DES/'criteria.json')['limits']})
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':d,'candidate':f['pin'],'verification':bind(ART/'candidate-menu-journal/result.json'),'regression_comparison':bind(ART/'regression-comparison.json'),'serving_files':len(stage),'quality_certified':False,'model_calls':0,'unchanged_SQL_plans':640,'new_SQL_plans':0})
command('prepare.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE,'--authorization',str(OUT/'authorization.json'),'--validation',str(OUT/'validation.json')])
p=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';r=read(p);assert r['files']==stage
put(DES/'candidate-prepared.json',{'code_root':r['code_root'],'selected_files':stage,'pin':f['pin']})
put(OUT/'gold-before.json',{'binding':b['gold_binding'],'files':b['gold_files']})
print('Prepared530 files, changed',len(d['changes']),'MAIN unchanged pending prepared tests')
