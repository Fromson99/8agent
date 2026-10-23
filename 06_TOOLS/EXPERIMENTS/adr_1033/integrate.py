"""Selective, preconditioned working integration; selected release untouched."""
from common import *
import tarfile,shutil,re
s=read(ART/'stage.json');c=ROOT/s['root'];f=read(sorted(ART.glob('design-rev-*.json'))[-1])
assert sha(Path(__file__).with_name('run_contracts.py'))==f['runner_sha256']
assert all(sha(c/n)==h for n,h in f['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
logs=['contracts-final.log','regression-final.log']
counts={}
for name in logs:
 log=(ART/name).read_text();assert 'FAILURES' not in log and 'ERRORS' not in log,name
 counts[name]=int(re.findall(r'(\d+) passed',log)[-1])
changed=[n for n,h in f['files'].items() if s['working_before'].get(n)!=h]
for n in changed:
 assert (sha(ROOT/n) if (ROOT/n).exists() else None)==s['working_before'].get(n),n
save(ART/'integration-decision.json',{'authority':'User requested implementation; verified candidate selectively integrated into working code only.',
 'verified_logs':{n:sha(ART/n) for n in logs},'counts':counts,'revision':read(ADR/'실험/manifest.json')['design']['code_isolation']['candidates'][0]['revision_id'],
 'before':{n:s['working_before'].get(n) for n in changed},'after':{n:f['files'][n] for n in changed}})
with tarfile.open(ART/'working-before.tar.gz','w:gz') as archive:
 for n in changed:
  if (ROOT/n).is_file():archive.add(ROOT/n,arcname=n)
for n in changed:
 (ROOT/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(c/n,ROOT/n)
assert all(sha(ROOT/n)==f['files'][n] for n in changed)
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
save(ART/'working-integration.json',{'files':changed,'sha256':{n:sha(ROOT/n) for n in changed},
 'read_judgment':True,'MAIN102_pointer_unchanged':True,'GENOS_changed':False,
 'backup_sha256':sha(ART/'working-before.tar.gz'),
 'rollback':'After verifying current files match after-hashes, restore preexisting listed files from working-before.tar.gz; remove only unchanged new files listed with before=null. Do not alter selected MAIN pointer.'})
print('Integrated',len(changed),'files; selected MAIN unchanged')
