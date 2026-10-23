"""CAS the validated candidate deltas; preserve preexisting and concurrent work."""
from common import *
import shutil,zipfile
assert read(ART/'analysis.json')['strict_success'] and read(ART/'contracts-final.json')['passed']
s=read(ART/'stage.json');C=ROOT/s['roots']['candidate'];record=read(ROOT/s['candidate_dir']/'candidate.json')
frozen={r['target_path']:r['snapshot_sha256'] for r in record['files']}
changes=[n for n,h in frozen.items() if s['working_baseline'][n]!=h]
for n in changes:
 p=ROOT/n;assert (sha(p) if p.exists() else None)==s['working_baseline'][n],('working drift',n)
 assert sha(C/n)==frozen[n]
backup=ART/'working-before-integration.zip'
with zipfile.ZipFile(backup,'x',zipfile.ZIP_DEFLATED) as z:
 for n in changes:
  if (ROOT/n).exists():z.write(ROOT/n,n)
for n in changes:
 (ROOT/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,ROOT/n)
assert all(sha(ROOT/n)==h for n,h in frozen.items())
save(ART/'working-integration.json',{'changed_files':changes,'created_files':[n for n in changes if s['working_baseline'][n] is None],
 'backup_sha256':sha(backup),'frozen_files_match':len(frozen),'serving_files_match':len(s['files']['candidate']),'main_changed':False})
print('Integrated',len(changes),'files; active MAIN unchanged')
