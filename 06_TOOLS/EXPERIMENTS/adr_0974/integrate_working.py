"""CAS only exact candidate deltas after live/model and contract gates pass."""
from common import *
import zipfile,shutil
assert read(ART/'analysis.json')['strict_success'] and read(ART/'contracts-final.json')['passed']
s=read(ART/'stage.json');C=ROOT/s['roots']['candidate'];changes=[n for n,h in s['files']['candidate'].items() if s['working_baseline'][n]!=h]
for n in changes:assert sha(ROOT/n)==s['working_baseline'][n],('working drift',n)
with zipfile.ZipFile(ART/'working-before-integration.zip','x',zipfile.ZIP_DEFLATED) as z:
 for n in changes:z.write(ROOT/n,n)
for n in changes:shutil.copyfile(C/n,ROOT/n)
assert all(sha(ROOT/n)==h for n,h in s['files']['candidate'].items())
save(ART/'working-integration.json',{'changed_files':changes,'backup_sha256':sha(ART/'working-before-integration.zip'),'all419_match':True,'main_changed':False})
print('Integrated exact candidate',len(changes),'files; MAIN unchanged')
