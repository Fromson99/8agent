"""Archive only this completed task's disposable test runtimes, with full hashes."""
from common import *
import tarfile,shutil,os
rows=[]
for name in ('native-r1','contracts-r2','native-r1-local','native-r2-local','contracts-r2-local','working-native'):
 folder=ART/name;runtime=folder/'runtime'
 assert (folder/'result.json').is_file() or (folder/'environment-stop.json').is_file()
 assert runtime.is_dir() and not runtime.is_symlink()
 members=sorted(runtime.rglob('*'));files={str(p.relative_to(folder)):{'sha256':sha(p),'bytes':p.stat().st_size}
     for p in members if p.is_file() and not p.is_symlink()}
 links={str(p.relative_to(folder)):os.readlink(p) for p in members if p.is_symlink()}
 archive=folder/'runtime.tar.gz';assert not archive.exists()
 with archive.open('xb') as raw:
  with tarfile.open(fileobj=raw,mode='w:gz',compresslevel=1) as tar:
   for p in [runtime,*members]:tar.add(p,arcname=str(p.relative_to(folder)),recursive=False)
 verified=set();link_seen={}
 with tarfile.open(archive,'r:gz') as tar:
  for member in tar:
   if member.isfile():
    stream=tar.extractfile(member)
    assert hashlib.file_digest(stream,'sha256').hexdigest()==files[member.name]['sha256']
    assert member.size==files[member.name]['bytes'];verified.add(member.name)
   elif member.issym():link_seen[member.name]=member.linkname
 assert verified==set(files) and link_seen==links
 assert all(sha(folder/n)==v['sha256'] for n,v in files.items())
 from experiment_json import write_raw_json
 inventory=write_raw_json(folder/'runtime-inventory.json.gz',{'files':files,'symlinks':links})
 receipt={'archive':bind(archive),'archive_bytes':archive.stat().st_size,
     'original_bytes':sum(v['bytes'] for v in files.values()),'file_count':len(files),
     'inventory':inventory,'full_restore_hash_verified':True,
     'restore':'tar -xzf runtime.tar.gz in this run folder, only when runtime does not exist',
     'scope':'Only terminated local test runtime; failed proposals and SQLite journals preserved byte-exact.'}
 put(folder/'runtime-archive.json',receipt)
 shutil.rmtree(runtime)
 rows.append({'run':name,**receipt})
put(ART/'runtime-archives.json',{'rows':rows,'original_bytes':sum(r['original_bytes'] for r in rows),
    'archive_bytes':sum(r['archive_bytes'] for r in rows),'all_restore_hashes_verified':True})
print('Archived',len(rows),'completed test runtimes; full contents verified')
