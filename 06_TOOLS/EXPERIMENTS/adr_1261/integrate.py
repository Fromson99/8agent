from pathlib import Path
import sys,json,hashlib,shutil,subprocess
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1261-oracle-progress-snapshot-dedup';D=A/'artifacts/design';O=A/'artifacts/run-001';read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as z:return hashlib.file_digest(z,'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(D/'baseline.json');f=read(D/'freeze.json');C=R/f['code_root'];own=f['products'];assert all(sha(C/n)==h for n,h in f['files'].items());assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
for tag,count in [('unit-final',16),('real-progress-final',4),('records-final',18),('api-final',2),('support-final',97)]:v=read(A/'artifacts'/('checks-'+tag+'.json'));assert v['passed']==count and v['failed']==0
old=read(A/'artifacts/checks-baseline-existing-final.json');new=read(A/'artifacts/checks-candidate-existing-final.json');failed=lambda v:{r['test'] for r in v['rows'] if r['status']=='failed'};assert failed(old)==failed(new) and old['passed']==new['passed']==56 and len(failed(new))==14
previous=read(O/'codec-baseline.json');current=read(O/'codec-candidate-qualified.json');assert current['body_envelope_characters']<=previous['body_envelope_characters']*.8 and current['all_sql']<=previous['all_sql']*1.5
assert read(O/'holdout.json')['all_versions_exact']
working={str(p.relative_to(R)):sha(p) for p in (R/'02_BACKEND/semantic_runtime').rglob('*.py')};put(D/'working-before-integration.json',working)
backup=A/'artifacts/working-before-integration';backup.mkdir()
for n,h in own.items():
 p=R/n
 if p.exists():
  assert sha(p)==b['manifest']['files'].get(n),'Concurrent storage edit';q=backup/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
 else:assert n not in b['manifest']['files']
 shutil.copyfile(C/n,p)
# Change only owned dependency entries in working manifests; preserve parallel source pins.
updates={};pins=[]
for p in (R/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if not set(own)&set(v.get('files',{})):continue
 before=sha(p);q=backup/p.relative_to(R);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);v['files'].update(own);put(p,v);updates[before]=sha(p);pins.append(str(p.relative_to(R)))
p=R/'00_SYSTEM/PIPELINE.json';shutil.copy2(p,backup/'00_SYSTEM/PIPELINE.json');text=p.read_text()
for oldhash,newhash in updates.items():text=text.replace(oldhash,newhash)
p.write_text(text);pins.append(str(p.relative_to(R)))
assert all(sha(R/n)==h for n,h in own.items());assert all(sha(R/n)==h for n,h in working.items() if n not in own)
put(O/'working-integration.json',{'products':list(own),'pin_files':pins,'unrelated_working_files_preserved':True,'unselected_working_differences_from_active':[n for n,h in b['working_files'].items() if h!=b['manifest']['files'][n]],'working_equals_selected_only_for_owned_modules':True,'full_working_inventory_equals_candidate':False,'reason':'Candidate deliberately uses activeMAIN129 plus storage2; unqualified parallel changes remain in working checkout, not rolled back or silently promoted','backup':str(backup.relative_to(R))})
put(D/'preview-auth.json',{'purpose':'integration_preview'});put(D/'preview-validation.json',{'structural_checks_passed':True})
with (A/'artifacts/preview.log').open('x') as log:subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',b['manifest']['data_path'],'--release-id','progress-dedup-preview-20261031-r1','--authorization',str(D/'preview-auth.json'),'--validation',str(D/'preview-validation.json'),'--integration-preview',str(D/'official-preview.json')],cwd=R,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(D/'official-preview.json');files=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:files.pop(row['path'])
 else:files[row['path']]=row['after']
assert files==f['files'] and len(files)==496
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':f['candidate_revision'],'staged_files':files,'excluded_candidate_paths':{}};put(D/'release-rebase.json',rebase)
for row in d['changes']:row['reason']='Exact dependency inventory for the two verified persistence modules' if row['path'] not in own else 'Lossless progress snapshot sharing; retain every logical version and resume authority'
d.update(candidate=f['candidate_revision'],rebase_receipt={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')});put(D/'integration.json',d);print('Integrated2 owned modules+preserved working pins; selected candidate496/preview',len(d['changes']),'changes')
