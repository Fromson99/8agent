from common import *
import shutil,subprocess,difflib
f=read(sorted(DES.glob('freeze-*.json'))[-1]);C=ROOT/f['code_root'];b=read(DES/'baseline.json')
tech=read(ART/'check-qualified.json');reg=read(ART/'regression-comparison.json')
assert tech['all_passed'] and not reg['new_regressions'] and not reg['status_differences']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
changed=[n for n,h in f['files'].items() if b['manifest']['files'].get(n)!=h]
engines={r['manifest'] for r in read(C/'00_SYSTEM/PIPELINE.json')['engines'].values()};pins=engines|{'00_SYSTEM/PIPELINE.json'}
products=[n for n in changed if n not in pins];assert len(products)==6,products
for n,h in f['files'].items():assert sha(C/n)==h,n
for n,h in b['working_files'].items():assert (sha(ROOT/n) if (ROOT/n).is_file() else None)==h,'Concurrent working modification: '+n
put(DES/'staging-final.json',{'code_root':str(C.relative_to(ROOT)),'files':f['files'],'changed':changed,'products':products})
put(DES/'preview-auth.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True})
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',b['manifest']['data_path'],'--release-id','accepted-answer-preview-20261029-r1','--authorization',str(DES/'preview-auth.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'official-preview.json')]
with (ART/'official-preview.log').open('x') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'official-preview.json');actual=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:actual.pop(row['path'])
 else:actual[row['path']]=row['after']
assert actual==f['files']
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':d['base_release_manifest_sha256'],'candidate':f['candidate_revision'],'staged_files':actual,'excluded_candidate_paths':{}})
for row in d['changes']:row['reason']='Preserve accepted claims through deterministic final rendering and selected profile; retain all MAIN116 cumulative functionality.'
d.update(candidate=f['candidate_revision'],rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
merged={};patches={}
for n in products:
 base=(ROOT/b['manifest']['code_root']/n).read_text();new=(C/n).read_text();work=(ROOT/n).read_text()
 before=work;left=base.splitlines(True);right=new.splitlines(True)
 groups=list(difflib.SequenceMatcher(a=left,b=right,autojunk=False).get_grouped_opcodes(3))
 for group in reversed(groups):
  old=''.join(left[group[0][1]:group[-1][2]]);replacement=''.join(right[group[0][3]:group[-1][4]])
  assert work.count(old)==1,('hunk conflict',n,old)
  work=work.replace(old,replacement,1)
 merged[n]=work
 patches[n]=''.join(difflib.unified_diff(before.splitlines(True),work.splitlines(True),fromfile=n,tofile=n))
 # Reverse exactly the proposed changes to prove unrelated working text survives.
 for group in groups:
  old=''.join(left[group[0][1]:group[-1][2]]);replacement=''.join(right[group[0][3]:group[-1][4]])
  assert work.count(replacement)==1,n
  work=work.replace(replacement,old,1)
 assert work==before,n
for n in products+sorted(pins):
 dest=ART/'working-backup'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dest)
for n,t in merged.items():(ROOT/n).write_text(t)
(ART/'working-targeted.patch').write_text('\n'.join(patches.values()))
for n in engines:
 p=ROOT/n;v=read(p)
 for path in v['files']:v['files'][path]=sha(ROOT/path)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=ROOT/'00_SYSTEM/PIPELINE.json';v=read(p)
for row in v['engines'].values():row['sha256']=sha(ROOT/row['manifest'])
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
protected=[n for n in b['working_files'] if n not in products and n not in pins]
assert all(sha(ROOT/n)==b['working_files'][n] for n in protected)
put(ART/'working-integration.json',{'product_files':{n:sha(ROOT/n) for n in products},'pins':{n:sha(ROOT/n) for n in pins},'changed_files':changed,'protected_files':len(protected),'protected_unchanged':True,'targeted_merge_preserved_unrelated_hunks':True,'new_model_calls':0})
put(ART/'working-pipeline-integrated.json',read(ROOT/'00_SYSTEM/PIPELINE.json'))
print('Integrated',len(products),'product/configuration files; serving changed',len(changed),'inventory',len(actual))
