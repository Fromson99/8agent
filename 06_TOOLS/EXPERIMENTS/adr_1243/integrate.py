from common import *
import shutil,subprocess
b=read(DES/'baseline.json');f=read(DES/'freeze.json');C=ROOT/f['code_root']
assert read(ART/'checks-final-records.json')['passed']==14 and read(ART/'checks-final-api.json')['exit_code']==0
assert read(ART/'checks-baseline-records.json')['passed']==12 and read(ART/'checks-baseline-records.json')['failed']==2
assert read(ART/'checks-baseline-api.json')['failed']==2
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(ROOT/n)==h for n,h in b['working_files'].items())
changes=[n for n,h in f['files'].items() if sha(ROOT/n)!=h]
pins=[n for n in changes if n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/')]
products=[n for n in changes if n not in pins];assert len(products)==3 and len(pins)==31
backup=ART/'working-before-integration';backup.mkdir()
for n in changes:
 target=backup/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/n,target);shutil.copy2(C/n,ROOT/n)
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
put(ART/'working-integration.json',{'files':494,'products':products,'pins':pins,'backup':str(backup.relative_to(ROOT))})
put(ART/'working-pipeline-integrated.json',read(ROOT/'00_SYSTEM/PIPELINE.json'))
put(DES/'preview-auth.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True})
with (ART/'preview.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),
 '--generation',b['manifest']['data_path'],'--release-id','oracle-default-preview-20261030-r1',
 '--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),
 '--integration-preview',str(DES/'official-preview.json')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==f['files'] and len(d['changes'])==34
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],
 'candidate':f['candidate_revision'],'staged_files':actual,'excluded_candidate_paths':{}})
for row in d['changes']:row['reason']='Exact inventory pin' if row['path'] in pins else 'Unify Oracle default runtime for service AD/report/recovery and chat without changing NFS defaults'
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
print('Integrated3 pure runtime resolver files and31 pins;494 exact')
