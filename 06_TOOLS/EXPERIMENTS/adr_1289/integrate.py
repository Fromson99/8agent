"""Integrate only the verified delta after checking every upstream precondition."""
from common import *
import shutil,os
from datetime import datetime,timezone
f=read(DES/'freeze.json');before=read(DES/'working-before.json');C=ROOT/f['code_root']
assert all(sha(C/n)==h for n,h in f['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
for name in ('contracts-r2-local','native-r2-local'):
 r=read(ART/name/'result.json');assert r['failed']==0 and r['code_unchanged'] and r['active_unchanged']
assert all(sha(ROOT/n)==h for n,h in before.items()),'concurrent upstream drift'
rows=[{'path':n,'before':before.get(n),'after':h} for n,h in f['files'].items() if before.get(n)!=h]
assert len(rows)==38
for row in rows:
 p=ROOT/row['path'];assert (sha(p) if p.exists() else None)==row['before'],row['path']
backup=ART/'working-before';backup.mkdir(exist_ok=False)
for row in rows:
 if row['before']:
  p=backup/row['path'];p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/row['path'],p)
  assert sha(p)==row['before']
put(ART/'integration-preflight.json',{'candidate':bind(DES/'freeze.json'),'rows':rows,'at':datetime.now(timezone.utc).isoformat(),
 'tests':{str(p.relative_to(ROOT)):sha(p) for p in sorted(Path(__file__).parent.glob('test_*.py'))},
 'authorization':'User: 더 할꺼 있나? 더 진행해봐; verified scoped working-code integration, MAIN133 unchanged'})
for row in rows:
 dst=ROOT/row['path'];temporary=dst.with_name('.'+dst.name+'.adr1289')
 assert not temporary.exists();shutil.copy2(C/row['path'],temporary);os.replace(temporary,dst)
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
put(ART/'working-integration.json',{'status':'PASS','rows':rows,'changed_files':len(rows),'product_files':7,'pins':31,
 'frozen_working_equal':len(f['files']),'candidate':bind(DES/'freeze.json'),'active_pointer':bind(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
 'backup_directory':str(backup.relative_to(ROOT)),'main_changed':False,'quality_certified':False})
print('Integrated 38 files: 7 product +31 pins; all 528 match; MAIN133 unchanged')
