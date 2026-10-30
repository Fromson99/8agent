from common import *
import shutil,difflib
f=read(DES/'freeze-rev-001.json');C=ROOT/f['code_root'];b=read(DES/'baseline.json')
new=read(ART/'check-rev-001-fixture-corrected.json');old=read(ART/'check-baseline-existing.json')
assert new['returncode']==old['returncode']==0 and read(ART/'replay-checkpoint-receipt.json')['passed']
status=lambda x:{r['test']:r['status'] for r in x['rows']}
assert all(status(new).get(k)==v for k,v in status(old).items())
put(ART/'existing-contract-comparison.json',{'baseline_passed':old['passed'],'candidate_same_passed':len(old['rows']),'new_regressions':[],'scope':'44 identical supervisor/paging/native-normal contracts; 15 additional candidate contracts separately counted'})
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
pins={r['manifest'] for r in read(C/'00_SYSTEM/PIPELINE.json')['engines'].values()}|{'00_SYSTEM/PIPELINE.json'}
changed=[n for n,h in f['files'].items() if b['manifest']['files'].get(n)!=h]
products=[n for n in changed if n not in pins]
assert products==['02_BACKEND/semantic_runtime/legal_agent/investigation_supervisor.py'],products
for n,h in f['files'].items():assert sha(C/n)==h
for n,h in b['working_files'].items():assert (sha(ROOT/n) if (ROOT/n).is_file() else None)==h,'Concurrent product edit: '+n
for n in products+sorted(pins):
 dest=ART/'working-backup'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dest)
patches=[]
for n in products:
 before=(ROOT/n).read_text();work=before
 left=(ROOT/b['manifest']['code_root']/n).read_text().splitlines(True);right=(C/n).read_text().splitlines(True)
 groups=list(difflib.SequenceMatcher(a=left,b=right,autojunk=False).get_grouped_opcodes(3))
 for g in reversed(groups):
  a=''.join(left[g[0][1]:g[-1][2]]);z=''.join(right[g[0][3]:g[-1][4]])
  assert work.count(a)==1,('hunk conflict',n);work=work.replace(a,z,1)
 reverse=work
 for g in groups:
  a=''.join(left[g[0][1]:g[-1][2]]);z=''.join(right[g[0][3]:g[-1][4]])
  assert reverse.count(z)==1;reverse=reverse.replace(z,a,1)
 assert reverse==before
 patches.append(''.join(difflib.unified_diff(before.splitlines(True),work.splitlines(True),fromfile=n,tofile=n)))
 (ROOT/n).write_text(work)
(ART/'working-targeted.patch').write_text('\n'.join(patches))
for n in pins-{'00_SYSTEM/PIPELINE.json'}:
 p=ROOT/n;v=read(p)
 for path in v['files']:v['files'][path]=sha(ROOT/path)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=ROOT/'00_SYSTEM/PIPELINE.json';v=read(p)
for row in v['engines'].values():row['sha256']=sha(ROOT/row['manifest'])
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
protected=[n for n in b['working_files'] if n not in products and n not in pins]
assert all(sha(ROOT/n)==b['working_files'][n] for n in protected)
assert all(sha(ROOT/n)==sha(C/n) for n in products)
put(ART/'working-integration.json',{'product_files':{n:sha(ROOT/n) for n in products},'pins':{n:sha(ROOT/n) for n in pins},'protected_files':len(protected),'protected_unchanged':True,'targeted_hunks_only':True,'main_unchanged':True,'new_model_calls':0})
print('Integrated product1, pins',len(pins),'protected',len(protected),'MAIN117 unchanged')
