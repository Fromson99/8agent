from common import *
import subprocess,shutil
f=read(DES/'freeze.json');b=read(DES/'baseline.json');C=ROOT/f['code_root']
for mode in ('candidate','working'):
 r=read(ART/f'checks-{mode}-source-final.json');assert r['passed']==29 and not r['failed'] and not r['import_leaks']
old=read(ART/'checks-baseline-regression-final.json');new=read(ART/'checks-candidate-regression-final.json')
outcomes=lambda v:{(r['test'],r['when']):r['status'] for r in v['rows']}
assert outcomes(old)==outcomes(new) and not old['import_leaks'] and not new['import_leaks']
if not (ART/'regression-comparison.json').exists():put(ART/'regression-comparison.json',{'identical_outcomes':True,'passed':new['passed'],'failed_or_setup_errors':new['failed'],'new_failures':0,'baseline':bind(ART/'checks-baseline-regression-final.json'),'candidate':bind(ART/'checks-candidate-regression-final.json')})
changed=[n for n,h in f['files'].items() if b['manifest']['files'].get(n)!=h];assert changed==[PRODUCT]
assert sha(ROOT/PRODUCT)==f['files'][PRODUCT]
put(ART/'concurrent-working-changes.json',{'files':{n:{'start':h,'current':sha(ROOT/n)} for n,h in b['working_files'].items() if sha(ROOT/n)!=h},'action':'Preserved without writing; excluded from isolated MAIN117 plus source renderer release.'})
put(DES/'preview-auth.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True})
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',b['manifest']['data_path'],'--release-id','source-accordion-preview-20261029-r1','--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'official-preview.json')]
with (ART/'official-preview.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==f['files'] and len(d['changes'])==1
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':f['candidate_revision'],'staged_files':actual,'excluded_candidate_paths':{}})
for row in d['changes']:row['reason']='Source button opens cards; individual card expands the exact acquired original text.'
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
put(ART/'working-pipeline-integrated.json',read(ROOT/'00_SYSTEM/PIPELINE.json'))
print('Official rebase: 466 files; source renderer only; other working files preserved')
