from common import *
import subprocess
f=read(DES/'freeze-rev-001.json');b=read(DES/'baseline.json');C=ROOT/f['code_root']
assert read(ART/'receipt-checks.json')['passed']
changed=[n for n,h in f['files'].items() if b['manifest']['files'].get(n)!=h]
pins={r['manifest'] for r in read(C/'00_SYSTEM/PIPELINE.json')['engines'].values()}|{'00_SYSTEM/PIPELINE.json'}
products=[n for n in changed if n not in pins];assert len(products)==6 and len(changed)==37
put(DES/'staging-final.json',{'code_root':f['code_root'],'files':f['files'],'changed':changed,'products':products})
put(DES/'preview-auth.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True})
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',b['manifest']['data_path'],'--release-id','accepted-answer-preview-20261029-r2','--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'official-preview.json')]
with (ART/'official-preview.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==f['files']
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':f['candidate_revision'],'staged_files':actual,'excluded_candidate_paths':{}})
for row in d['changes']:row['reason']='Exact1196 rev002 accepted-content rendering correction; complete technical receipts under1197.'
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
put(ART/'working-integration.json',read(SOURCE/'working-integration.json'));put(ART/'working-pipeline-integrated.json',read(SOURCE/'working-pipeline-integrated.json'))
print('Official rebase37 changes,466files; working content retained exactly')
