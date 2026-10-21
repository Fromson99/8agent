"""CAS-integrate only the qualified legacy compiler and derived manifests."""
from common import *
import gzip,shutil
s=read(ART/'stage.json');C=ROOT/s['roots']['candidate'];consumer=read(ART/'consumer-candidate.json')
assert consumer['status']=='PASS' and all(consumer['checks'].values())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['base_pointer']
assert all(sha(ROOT/n)==h for n,h in s['working_baseline'].items()),'Do not overwrite concurrent work'
A=ROOT/'09_ARTIFACTS/AUDITS/20261021-law-name-main';A.mkdir(exist_ok=True)
changes=[]
for n,h in s['files']['candidate'].items():
 assert sha(C/n)==h
 if s['working_baseline'].get(n)==h:continue
 backup=A/'pre-integration'/(n+'.gz');backup.parent.mkdir(parents=True,exist_ok=True)
 with gzip.open(backup,'wb') as out:out.write((ROOT/n).read_bytes())
 changes.append({'path':n,'before':sha(ROOT/n),'after':h,'backup':str(backup.relative_to(ROOT)),'backup_sha256':sha(backup)})
for row in changes:shutil.copyfile(C/row['path'],ROOT/row['path'])
assert all(sha(ROOT/n)==h for n,h in s['files']['candidate'].items())
save(A/'working-integration.json',{'changes':changes,'all_418_files_match':True,'preserved_other_work':True,'active_pointer_unchanged':True})
save(A/'previous-pointer.json',s['base_pointer'])
print('Integrated exact candidate bytes; backups retained;',len(changes),'files; MAIN pointer still unchanged')
