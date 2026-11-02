from common import *
import shutil,subprocess
b=read(DES/'baseline.json');f=read(DES/'freeze.json');C=ROOT/f['code_root']
for tag,count in [('unit-001',14),('records-001',18),('api-001',2)]:
 v=read(ART/('checks-'+tag+'.json'));assert v['exit_code']==0 and v['passed']==count
assert read(ART/'stress.json')[1]['pass']
comparisons=[]
for family in ('existing','support'):
 old=read(ART/('checks-baseline-'+family+'-002.json'));new=read(ART/('checks-candidate-'+family+'-002.json'))
 failed=lambda v:{r['test'] for r in v['rows'] if r['status']=='failed'}
 assert failed(old)==failed(new) and old['passed']==new['passed']
 comparisons.append({'family':family,'passed':new['passed'],'existing_failures':len(failed(old)),'new_failures':[]})
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(ROOT/n)==h for n,h in b['working_files'].items())
changes=[n for n,h in f['files'].items() if sha(ROOT/n)!=h];pins=[n for n in changes if n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/')];products=[n for n in changes if n not in pins]
assert len(products)==3 and len(pins)==31
put(DES/'gold-before-integration.json',{'binding':read(GOLD/'binding.json'),'files':{str(p.relative_to(ROOT)):sha(p) for p in GOLD.iterdir() if p.is_file()}})
backup=ART/'working-before-integration';backup.mkdir()
for n in changes:
 target=backup/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/n,target);shutil.copy2(C/n,ROOT/n)
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
put(ART/'working-integration.json',{'files':495,'products':products,'pins':pins,'backup':str(backup.relative_to(ROOT)),'comparisons':comparisons})
put(ART/'working-pipeline-integrated.json',read(ROOT/'00_SYSTEM/PIPELINE.json'))
put(DES/'preview-auth.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True})
with (ART/'preview.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',b['manifest']['data_path'],'--release-id','oracle-safe-preview-20261030-r1','--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'official-preview.json')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==f['files'] and len(d['changes'])==34
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':f['candidate_revision'],'staged_files':actual,'excluded_candidate_paths':{}})
for row in d['changes']:row['reason']='Exact engine inventory pin' if row['path'] in pins else 'Oracle body compression and safe in-memory record refresh; preserve canonical authority/NFS boundaries'
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
print('Integrated3 storage modules+31pins;495 exact')
