"""Integrate only tested navigation changes, preserving concurrent UI edits."""
from common import *
import shutil
b=read(DES/'baseline.json');f=read(DES/'candidate-repaired.json');C=ROOT/f['code_root']
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer']
assert read(ART/'regression-comparison.json')['new_failures']==0
tested=read(ART/'prepared-review/result.json')
assert tested['failed']==0 and tested['code_unchanged']
changed=read(DES/'delta.json')['changed'];assert len(changed)==36
assert all(sha(ROOT/n)==b['working_files'][n] for n in changed)
preserved={n:sha(ROOT/n) for n in f['selected_files'] if n not in changed}
backup=ART/'working-before';backup.mkdir(exist_ok=False)
for n in changed:
 p=backup/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
for n in changed:
 assert sha(ROOT/n)==b['working_files'][n]
 shutil.copyfile(C/n,ROOT/n)
assert all(sha(ROOT/n)==f['selected_files'][n] for n in changed)
assert all(sha(ROOT/n)==h for n,h in preserved.items())
test=ROOT/'05_TESTS/CONTRACTS/test_coherent_navigation_contract.py';assert not test.exists()
shutil.copyfile(Path(__file__).with_name('test_navigation_contract.py'),test)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from genos_codespace_engine_preflight import check
engines,count,errors=check(ROOT);assert not errors,errors
put(ART/'working-integration.json',{'changed':changed,'product_changes':5,'dependent_pins':31,
 'engines':engines,'engine_files':count,'errors':errors,'preserved_other_files':preserved,
 'working_differences_from_release':[n for n,h in f['selected_files'].items() if sha(ROOT/n)!=h],
 'new_contract_path':str(test.relative_to(ROOT)),'new_contract_sha256':sha(test),
 'selected_MAIN_unchanged':b['pointer'],'backup':str(backup.relative_to(ROOT))})
print('Applied navigation5 and pins31; all other working files preserved')
