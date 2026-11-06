"""Apply only the reviewed parser and dependent pins; preserve concurrent work."""
from common import *
import shutil
b=read(DES/'baseline.json');f=read(DES/'candidate-repaired.json');C=ROOT/f['code_root']
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer']
assert read(ART/'regression-comparison.json')['new_failures']==0
prepared=read(ART/'prepared-review/result.json')
assert prepared['failed']==0 and prepared['exit_code']==0 and prepared['code_unchanged']
assert all(sha(ROOT/n)==h for n,h in b['working_files'].items())
changed=read(DES/'delta.json')['changed']
assert len(changed)==32
assert [n for n in changed if not n.startswith('02_BACKEND/ENGINES/') and n!='00_SYSTEM/PIPELINE.json']==['02_BACKEND/lawrag/core/legal_coordinate.py']
backup=ART/'working-before';backup.mkdir(exist_ok=False)
for n in changed:
 p=backup/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
for n in changed:
 assert sha(ROOT/n)==b['working_files'][n]
 shutil.copyfile(C/n,ROOT/n)
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
test=ROOT/'05_TESTS/CONTRACTS/test_annex_dash_coordinate.py'
assert not test.exists()
shutil.copyfile(Path(__file__).with_name('test_annex_dash.py'),test)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from genos_codespace_engine_preflight import check
engines,count,errors=check(ROOT);assert not errors,errors
put(ART/'working-integration.json',{'all530_exact':True,'changed':changed,'product_changes':1,
 'dependent_pins':31,'engines':engines,'engine_files':count,'errors':errors,
 'new_contract_path':str(test.relative_to(ROOT)),'new_contract_sha256':sha(test),
 'selected_MAIN_unchanged':b['pointer'],'backup':str(backup.relative_to(ROOT))})
print('Working parser plus31 pins applied; all530 equal prepared candidate')
