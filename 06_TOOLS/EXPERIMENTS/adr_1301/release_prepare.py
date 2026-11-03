from common import *
import subprocess,shutil,os

f=read(DES/'freeze.json');b=read(DES/'baseline.json');C=ROOT/f['code_root'];before=read(DES/'working-before.json')
for name in ('contracts-r1','regression-r2','native-final'):
 r=read(ART/name/'result.json');assert r.get('failed',0)==0 and r.get('status','PASS')=='PASS' and r['code_unchanged'] and r['active_unchanged'],name
assert all(sha(C/n)==h for n,h in f['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['active_sha256']
assert all(sha(ROOT/n)==h for n,h in before.items()),'concurrent upstream drift'
assert read(ART/'scaling/result.json')['status']=='PASS'
rows=[{'path':n,'before':before.get(n),'after':h} for n,h in f['files'].items() if before.get(n)!=h]
for row in rows:assert (sha(ROOT/row['path']) if (ROOT/row['path']).exists() else None)==row['before'],row['path']
backup=ART/'working-before';backup.mkdir(exist_ok=False)
for row in rows:
 if row['before']:
  p=backup/row['path'];p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/row['path'],p);assert sha(p)==row['before']
put(ART/'integration-preflight.json',{'rows':rows,'candidate':bind(DES/'freeze.json'),'authorization':read(DES/'criteria.json')['authorization']})
for row in rows:
 dst=ROOT/row['path'];dst.parent.mkdir(parents=True,exist_ok=True);temp=dst.with_name('.'+dst.name+'.adr1301');assert not temp.exists();shutil.copy2(C/row['path'],temp);os.replace(temp,dst)
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
put(ART/'working-integration.json',{'status':'PASS','rows':rows,'changed_files':len(rows),'frozen_working_equal':len(f['files'])})
OUT.mkdir(exist_ok=True)
put(DES/'preview-authorization.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True,'quality_certified':False})
def run(name,args):
 with (OUT/name).open('x') as log:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py',*args],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
run('preview.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE+'-preview','--authorization',str(DES/'preview-authorization.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'integration-preview.json')])
d=read(DES/'integration-preview.json');stage=dict(b['release']['files'])
for row in d['changes']:
 assert row['after'] is not None and f['files'][row['path']]==row['after']
 stage[row['path']]=row['after'];row['reason']='Verified ordinary lossless input, shared review relations and host-derived acquired-source bookkeeping; existing semantic validators intact; no legal quality certification'
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':b['active']['release_manifest_sha256'],'candidate':f['candidate_revision'],'staged_files':stage,'excluded_candidate_paths':{n:'Unchanged console/test/research dependency outside serving closure' for n in set(f['files'])-set(stage)}})
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
put(DES/'stage.json',{'files':stage,'count':len(stage),'changed':len(d['changes']),'changes':d['changes']})
put(OUT/'authorization.json',{'authorized_by':'user','authorization_text':'정리해보고 메인에 반영해',
 'scope':'Ordinary ASSESS contract cleanup; local MAIN and Gold binding only',
 'quality_gate_override':True,'deployment_basis':'USER_DIRECTED_CUTOVER','quality_certified':False,'no_implicit_external_deploy':True,
 'known_limits':['ADR1297 actual scenario UNKNOWN and no full pass preserved','Independent semantic/scope review remains; incremental review not implemented','New effect on real Qwen quality and large-data latency unverified'], 'criteria':bind(DES/'criteria.json')})
put(OUT/'validation.json',{'structural_checks_passed':True,'integration':d,'source_identity':bind(DES/'freeze.json'),'serving_files':len(stage),'quality_certified':False,'model_calls':0,
 'scaling':bind(ART/'scaling/result.json'),'verification':{n:bind(ART/n/'result.json') for n in ('contracts-r1','regression-r2','native-final')}})
run('prepare.log',['prepare','--code-root',str(C),'--generation',b['release']['data_path'],'--release-id',RELEASE,'--authorization',str(OUT/'authorization.json'),'--validation',str(OUT/'validation.json')])
r=read(ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json')
assert r['files']==stage and all(sha(ROOT/r['code_root']/n)==sha(ROOT/n)==h for n,h in stage.items())
assert r['data_path']==b['release']['data_path'] and r['data_manifest_sha256']==b['release']['data_manifest_sha256']
put(OUT/'prepared.json',{'release_id':RELEASE,'files':len(stage),'changed':len(d['changes']),'working_candidate_release_exact':True,'data_unchanged':True})
print('Prepared',RELEASE,'serving',len(stage),'changed',len(d['changes']),'working changes',len(rows))
