from common import *
import subprocess,shutil
OUT=ART/'main';OUT.mkdir(exist_ok=False);GOLD=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';RELEASE='query-latency-native-20261104-r1'
f=read(DES/'candidate-after.json');C=ROOT/f['code_root'];b=read(DES/'baseline.json');before=read(DES/'working-before-files.json')
assert read(ART/'analysis.json')['verified']
assert all(sha(C/n)==h for n,h in f['selected_files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'main-pointer-before.json')['sha256']
assert all(sha(ROOT/n)==h for n,h in before.items()),'Concurrent source drift; preserve it'
changes={n:h for n,h in f['selected_files'].items() if before[n]!=h};backup=ART/'working-before';backup.mkdir()
for n in changes:
 p=backup/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
put(ART/'integration-preflight.json',{'before':{n:before[n] for n in changes},'after':changes,'source_candidate':f['pin']})
for n,h in changes.items():
 p=ROOT/n;tmp=p.with_name('.'+p.name+'.adr1316');shutil.copyfile(C/n,tmp);os.replace(tmp,p)
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
put(ART/'working-integration.json',{'changed_files':len(changes),'changes':changes,'all539exact':True})
put(DES/'candidate-working.json',{'code_root':'.','selected_files':f['selected_files']})
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
def command(log,args):
 with (OUT/log).open('x') as out:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py',*args],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,check=True)
put(OUT/'preview-authorization.json',{'purpose':'integration_preview'});put(OUT/'preview-validation.json',{'structural_checks_passed':True})
command('preview.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE+'-preview','--authorization',str(OUT/'preview-authorization.json'),'--validation',str(OUT/'preview-validation.json'),'--integration-preview',str(OUT/'integration-preview.json')])
d=read(OUT/'integration-preview.json');stage=dict(b['release']['files'])
for row in d['changes']:
 assert row['after'] is not None and f['selected_files'][row['path']]==row['after']
 stage[row['path']]=row['after'];row['reason']='Verified cumulative request-local source/structure reuse, bounded original-ID to native-unit lookup batches, SQLite metadata preparation, native prepared Oracle SQL/ORDS and optional development mapping closure; final review defaults and current Gold source mapping preserved.'
put(OUT/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':b['pointer']['release_manifest_sha256'],'candidate':f['pin'],'staged_files':stage,'excluded_candidate_paths':{n:'Build/research dependency outside selected serving engine closure; exact candidate source preserved' for n in set(f['selected_files'])-set(stage)}})
d.update(candidate=f['pin'],rebase_receipt=bind(OUT/'release-rebase.json'));put(OUT/'integration.json',d);put(OUT/'stage.json',{'files':stage,'count':len(stage),'changed':len(d['changes'])})
oldpipe=ROOT/b['release']['code_root']/'00_SYSTEM/PIPELINE.json'
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'추가 수정하고 메인에 반영해','scope':'Additional SQL/structure latency fixes and cumulative current code local MAIN and Gold binding integration','quality_gate_override':True,'deployment_basis':'USER_DIRECTED_CUTOVER','quality_certified':False,'no_implicit_external_deploy':True,'criteria':bind(DES/'criteria.json'),'rollback_pipeline':bind(oldpipe),'known_limits':['New model answer quality and FINISH real effect not remeasured','Field Oracle19/Dataiku/A8 allowlist execution not certified','SQLite first resource preparation remains material']})
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':d,'candidate':f['pin'],'verification':bind(ART/'analysis.json'),'serving_files':len(stage),'quality_certified':False,'model_calls':0})
command('prepare.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE,'--authorization',str(OUT/'authorization.json'),'--validation',str(OUT/'validation.json')])
p=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json';r=read(p)
assert r['files']==stage and all(sha(ROOT/r['code_root']/n)==sha(ROOT/n)==h for n,h in stage.items())
put(DES/'candidate-prepared.json',{'code_root':r['code_root'],'selected_files':stage})
put(OUT/'prepared.json',{'release_id':RELEASE,'files':len(stage),'changed_vs_main136':len(d['changes']),'working_candidate_release_exact':True,'data_unchanged':r['data_manifest_sha256']==b['release']['data_manifest_sha256']})
# Freeze all connector/config originals before activation, independently of model defaults.
put(OUT/'gold-before.json',{'binding':read(GOLD/'binding.json'),'files':{str(p.relative_to(ROOT)):sha(p) for p in GOLD.iterdir() if p.is_file() and p.suffix in ('.py','.json','.yaml')}})
print('Prepared',RELEASE,len(stage),'files; workingchanges',len(changes),'deltaMAIN',len(d['changes']))
