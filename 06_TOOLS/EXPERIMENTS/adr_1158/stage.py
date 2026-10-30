from common import *
import shutil
f=read(DES/'freeze.json');C=ROOT/f['code_root'];b=read(DES/'baseline.json');old=b['manifest']['files']
files={n:f['files'][n] for n in old}
for n,h in f['files'].items():
 if n.startswith('02_BACKEND/semantic_runtime/ontology_work/') or n in ('00_SYSTEM/SCHEMAS/ontology-bundle-v0.schema.json','00_SYSTEM/SCHEMAS/ontology-scenario-proposal-v1.schema.json','00_SYSTEM/SCHEMAS/ontology-db-mapping-v1.json'):files[n]=h
S=ART/'staged-code'
for n,h in files.items():
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,p)
(S/'01_DATA').symlink_to(ROOT/'01_DATA',target_is_directory=True)
changed=[n for n,h in files.items() if old.get(n)!=h]
put(DES/'staging.json',{'code_root':str(S.relative_to(ROOT)),'files':files,'changed':sorted(changed),'data_shipped':False,'test_data_symlink_only':True})
print('Staged serving files',len(files),'changed',len(changed),'schema included')
