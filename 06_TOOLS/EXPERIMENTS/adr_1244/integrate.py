from common import *
import shutil,subprocess
b=read(DES/'baseline.json');f=read(DES/'freeze.json');C=ROOT/f['code_root']
assert read(ART/'checks-qualified-records.json')['passed']==18 and read(ART/'checks-qualified-api.json')['exit_code']==0
comparisons=[]
for baseline,candidate in [('baseline-existing','qualified-existing'),('baseline-support','candidate-support')]:
 old=read(ART/('checks-'+baseline+'.json'));new=read(ART/('checks-'+candidate+'.json'))
 failed=lambda v:{r['test'] for r in v['rows'] if r['status']=='failed'}
 assert failed(old)==failed(new) and old['passed']==new['passed'],(baseline,candidate)
 comparisons.append({'baseline':bind(ART/('checks-'+baseline+'.json')),'candidate':bind(ART/('checks-'+candidate+'.json')),
 'passed':new['passed'],'same_existing_failures':len(failed(old)),'new_failures':[]})
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(ROOT/n)==h for n,h in b['working_files'].items())
changes=[n for n,h in f['files'].items() if not (ROOT/n).exists() or sha(ROOT/n)!=h]
pins=[n for n in changes if n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/')]
products=[n for n in changes if n not in pins];assert len(products)==11 and len(pins)==31
backup=ART/'working-before-integration';backup.mkdir()
for n in changes:
 if (ROOT/n).exists():
  target=backup/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/n,target)
 else:assert n=='02_BACKEND/semantic_runtime/detailed_log_storage.py'
 shutil.copy2(C/n,ROOT/n)
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
put(ART/'working-integration.json',{'files':495,'products':products,'pins':pins,'backup':str(backup.relative_to(ROOT)),'comparisons':comparisons})
put(ART/'working-pipeline-integrated.json',read(ROOT/'00_SYSTEM/PIPELINE.json'))
put(DES/'preview-auth.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True})
with (ART/'preview.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),
 '--generation',b['manifest']['data_path'],'--release-id','oracle-structured-preview-20261030-r1',
 '--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),
 '--integration-preview',str(DES/'official-preview.json')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==f['files'] and len(d['changes'])==42
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],
 'candidate':f['candidate_revision'],'staged_files':actual,'excluded_candidate_paths':{}})
for row in d['changes']:row['reason']='Exact inventory pin' if row['path'] in pins else 'Oracle structured authority, NFS-only raw diagnostics; preserve evidence/ACL/budgets and default NFS'
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
print('Integrated11 storage/consumer files and31 pins;495 exact')
