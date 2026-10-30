from common import *
import shutil
f=read(DES/'freeze.json');C=ROOT/f['code_root'];b=read(DES/'baseline.json');old=b['manifest']['files']
new=['02_BACKEND/semantic_runtime/'+n+'.py' for n in ('initial_vector','vector_publish','vector_navigation','oracle_silver_reads')]+['00_SYSTEM/ORACLE/physical_mapping.yaml']
files={n:f['files'][n] for n in [*old,*new]};S=ART/'staged-code'
for n,h in files.items():
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,p)
if not (S/'01_DATA').exists():(S/'01_DATA').symlink_to(ROOT/'01_DATA',target_is_directory=True)
put(DES/'staging.json',{'code_root':str(S.relative_to(ROOT)),'files':files,'changed':sorted(n for n,h in files.items() if old.get(n)!=h),'data_shipped':False})
print('serving',len(files),'changed',len(read(DES/'staging.json')['changed']))
