"""Selective integration; no release/MAIN/generation cutover."""
from common import *
import shutil
s=read(ART/'stage.json');f=read(ART/'design-freeze.json');C=ROOT/s['roots']['candidate']
audit=read(ART/'observations.json');assert audit['source_checks']['mismatches']==audit['source_checks']['scope_violations']==0
assert not read(ART/'selected-scope-audit.json')['navigation_has_combined_dependency_cards']
assert all(sha(C/n)==h for n,h in f['files']['candidate'].items())
changed={n:h for n,h in f['files']['candidate'].items() if s['working_before'].get(n)!=h}
# All checks before writes: preserve edits belonging to any other work.
for n,h in changed.items():
 p=ROOT/n;previous=s['working_before'].get(n)
 assert (sha(p)==previous if previous else not p.exists()), 'Concurrent change: '+n
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
backup=ART/'integration-before';assert not backup.exists()
for n,h in changed.items():
 p=ROOT/n
 if p.exists():
  b=backup/n;b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,b)
 p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(C/n,p)
assert all(sha(ROOT/n)==h for n,h in f['files']['candidate'].items())
save(ART/'integration.json',{'status':'WORKING_CODE_INTEGRATED','files':changed,'all_working_candidate_files_equal':len(f['files']['candidate']),
 'before':{n:s['working_before'].get(n) for n in changed},'backup':str(backup.relative_to(ROOT)),
 'main_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256'],
 'main_promoted':False,'genos_deployed':False,'rollback':'Restore only changed file paths from integration-before; newly added paths have before=null. Check current hashes against this receipt before rollback.'})
print('Integrated',len(changed),'changed files; all',len(f['files']['candidate']),'candidate bytes match; MAIN unchanged')
