from common import *
import shutil,subprocess
b=read(DES/'baseline.json');f=read(DES/'freeze.json');C=ROOT/f['code_root']
assert read(ART/'checks-final-records.json')['exit_code']==0
assert read(ART/'checks-final-api.json')['exit_code']==0
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(ROOT/n)==h for n,h in b['working_files'].items()),'Concurrent serving edits require an explicit new rebase'
assert all(sha(ROOT/n)==h for n,h in read(DES/'gold-before-integration.json')['files'].items())
comparisons=[]
for baseline,candidate in [('baseline-existing-001','final-existing'),('baseline-support','final-support')]:
 old=read(ART/('checks-'+baseline+'.json'));new=read(ART/('checks-'+candidate+'.json'))
 failed=lambda v:{r['test'] for r in v['rows'] if r['status']=='failed'}
 assert failed(old)==failed(new) and old['passed']==new['passed'],(baseline,candidate)
 comparisons.append({'baseline':bind(ART/('checks-'+baseline+'.json')),'candidate':bind(ART/('checks-'+candidate+'.json')),
     'passed':new['passed'],'same_existing_failures':sorted(failed(old)),'new_failures':[]})
changes=[n for n,h in f['files'].items() if not (ROOT/n).is_file() or sha(ROOT/n)!=h]
pins=[n for n in changes if n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/')]
products=[n for n in changes if n not in pins]
backup=ART/'working-before-integration-r2';backup.mkdir()
for n in changes:
 p=ROOT/n
 if p.exists():
  target=backup/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
 else:assert n not in b['manifest']['files']
 p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(C/n,p)
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
put(ART/'working-integration.json',{'all_serving_files_exact':True,'files':len(f['files']),
    'products':products,'pins':pins,'prior_main':b['active'],'comparisons':comparisons,
    'backup':str(backup.relative_to(ROOT)),'new_files':[n for n in changes if n not in b['manifest']['files']]})
put(ART/'working-pipeline-integrated.json',read(ROOT/'00_SYSTEM/PIPELINE.json'))
assert read(DES/'preview-auth.json')=={'purpose':'integration_preview'}
assert read(DES/'preview-validation.json')=={'structural_checks_passed':True}
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),
 '--generation',b['manifest']['data_path'],'--release-id','oracle-records-preview-20261030-r2',
 '--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),
 '--integration-preview',str(DES/'official-preview.json')]
with (ART/'official-preview.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==f['files'] and len(d['changes'])==len(changes)
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1',
 'base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':f['candidate_revision'],
 'staged_files':actual,'excluded_candidate_paths':{}})
for row in d['changes']:
 row['reason']='Exact serving inventory pin' if row['path'] in pins else 'Oracle Agent persistence with explicit runtime ports, default NFS preserved; legal/source/ACL contracts retained'
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'))
put(DES/'integration.json',d)
print('Integrated',len(products),'product/manifest files +',len(pins),'engine pins;',len(f['files']),'serving files exact')
