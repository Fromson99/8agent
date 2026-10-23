"""Apply only the reproduced deterministic correction, preserving other work."""
from common import *
import shutil,difflib
s=read(ART/'stage.json');f=read(ART/'design-freeze.json');C=ROOT/s['roots']['candidate']
assert '106 passed, 1 deselected' in (ART/'contracts-final.txt').read_text()
assert read(ART/'real-data-contract.json')['status']=='PASS'
assert (ART/'guard-result.json').exists()
assert all(sha(C/n)==h for n,h in f['files']['candidate'].items())
changed={n:h for n,h in f['files']['candidate'].items() if s['working_before'].get(n)!=h}
for n in changed:
 p=ROOT/n;old=s['working_before'].get(n)
 assert (sha(p)==old if old else not p.exists()), 'Concurrent change: '+n
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
backup=ART/'integration-before';assert not backup.exists();patches=[]
for n in changed:
 p=ROOT/n
 old=p.read_text() if p.exists() else ''
 if p.exists():
  b=backup/n;b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,b)
 p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(C/n,p)
 if n.endswith('.py'):patches.extend(difflib.unified_diff(old.splitlines(True),p.read_text().splitlines(True),fromfile='before/'+n,tofile='after/'+n))
assert all(sha(ROOT/n)==h for n,h in f['files']['candidate'].items())
(ART/'changes.patch').write_text(''.join(patches))
save(ART/'integration.json',{'status':'WORKING_CODE_INTEGRATED','basis':'Reproduced deterministic read-state defect, 106 contracts/native API and exact real endpoint; live behavior unconfirmed due initial provider429',
 'files':changed,'all_working_candidate_files_equal':len(f['files']['candidate']),
 'before':{n:s['working_before'].get(n) for n in changed},'backup':str(backup.relative_to(ROOT)),
 'main_pointer_unchanged':True,'main_promoted':False,'genos_deployed':False,
 'rollback':'Verify current after hashes, restore only listed files from integration-before; newly added paths have before=null. Keep prior experiments and unrelated files.'})
print('Integrated',len(changed),'paths; exact frozen',len(f['files']['candidate']),'files; MAIN unchanged')
