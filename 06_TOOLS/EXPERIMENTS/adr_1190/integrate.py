from common import *
import shutil,subprocess

f=read(DES/'freeze-rev-001.json');C=ROOT/f['code_root'];b=read(DES/'baseline.json')
tech=read(ART/'check-rev-001.json')
assert tech['passed']==41 and tech['failed']==0 and not tech['import_leaks']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
changed=[n for n,h in f['files'].items() if b['manifest']['files'].get(n)!=h]
engines={r['manifest'] for r in read(C/'00_SYSTEM/PIPELINE.json')['engines'].values()}
pins=engines|{'00_SYSTEM/PIPELINE.json'}
products=[n for n in changed if n not in pins]
assert products==['00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'],products
for n,h in f['files'].items():assert sha(C/n)==h,n
assert sha(ROOT/b['research_client']['path'])==b['research_client']['sha256']
for n,h in b['working_files'].items():
 assert (sha(ROOT/n) if (ROOT/n).is_file() else None)==h, 'Concurrent working modification: '+n
put(DES/'staging-final.json',{'code_root':str(C.relative_to(ROOT)),'files':f['files'],'changed':changed})
put(DES/'preview-auth.json',{'purpose':'integration_preview'})
put(DES/'preview-validation.json',{'structural_checks_passed':True})
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare',
 '--code-root',str(C),'--generation',b['manifest']['data_path'],
 '--release-id','parasail-primary-preview-20261029-r1','--authorization',str(DES/'preview-auth.json'),
 '--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'official-preview.json')]
with (ART/'official-preview.log').open('x') as log:
 subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==f['files']
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1',
 'base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':f['candidate_revision'],
 'staged_files':actual,'excluded_candidate_paths':{}})
for row in d['changes']:row['reason']='User requested Parasail FP8 primary; Near AI on one confirmed429 remains unchanged.'
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'))
put(DES/'integration.json',d)
for n in products+sorted(pins):
 dest=ART/'working-backup'/n;dest.parent.mkdir(parents=True,exist_ok=True)
 shutil.copyfile(ROOT/n,dest)
for n in products:shutil.copyfile(C/n,ROOT/n)
for n in engines:
 p=ROOT/n;v=read(p)
 for path in v['files']:v['files'][path]=sha(ROOT/path)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=ROOT/'00_SYSTEM/PIPELINE.json';v=read(p)
for row in v['engines'].values():row['sha256']=sha(ROOT/row['manifest'])
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
protected=[n for n in b['working_files'] if n not in products and n not in pins]
assert all(sha(ROOT/n)==b['working_files'][n] for n in protected)
put(ART/'working-integration.json',{'product_files':{n:sha(ROOT/n) for n in products},
 'pins':{n:sha(ROOT/n) for n in pins},'changed_files':changed,
 'protected_files':len(protected),'protected_unchanged':True,'new_model_calls':0})
put(ART/'working-pipeline-integrated.json',read(ROOT/'00_SYSTEM/PIPELINE.json'))
print('Integrated provider config; changed serving files',len(changed),'inventory',len(actual))
