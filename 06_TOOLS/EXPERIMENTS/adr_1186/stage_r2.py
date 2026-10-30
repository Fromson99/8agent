from common import *
import shutil,subprocess
f=read(DES/'freeze.json');b=read(DES/'baseline.json');C=ROOT/f['code_root'];S=ART/'staged-code-r2';excluded=set(read(DES/'integration-plan.json')['serve_exclude'])
files={n:h for n,h in f['files'].items() if n not in excluded}
for n,h in files.items():
 assert sha(C/n)==h
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,p)
(S/'01_DATA').symlink_to(ROOT/'01_DATA',target_is_directory=True)
put(DES/'staging-final.json',{'code_root':str(S.relative_to(ROOT)),'files':files,'changed':[n for n,h in files.items() if b['manifest']['files'].get(n)!=h],'excluded':sorted(excluded),'data_shipped':False})
put(DES/'preview-auth-r2.json',{'purpose':'integration_preview'});put(DES/'preview-validation-r2.json',{'structural_checks_passed':True,'scope':'inventory validation only; final technical qualification is separate'})
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(S),'--generation',b['manifest']['data_path'],'--release-id','source-contract-preview-20261028-r2','--authorization',str(DES/'preview-auth-r2.json'),'--validation',str(DES/'preview-validation-r2.json'),'--integration-preview',str(DES/'official-preview-r2.json')]
with (ART/'official-preview-r2.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview-r2.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==files,(set(actual)-set(files),set(files)-set(actual))
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':f['candidate_revision'],'staged_files':actual,'excluded_candidate_paths':{n:'Research client integrated and tested in working code; excluded from serving package' for n in excluded}})
for row in d['changes']:row['reason']='Cumulative required-source execution, output recovery, scope/containment/assessment contracts, physical provider routing and absolute model deadline; current MAIN112 source/model/budgets and ontology/vector retained.'
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
print('Official serving inventory:',len(files),'changed:',len(d['changes']))
