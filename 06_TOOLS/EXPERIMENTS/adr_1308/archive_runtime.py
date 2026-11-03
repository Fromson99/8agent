from common import *
import tarfile,shutil,os,gzip
rows=[]
for folder in sorted(ART.iterdir()):
 runtime=folder/'runtime'
 if not runtime.is_dir():continue
 assert (folder/'result.json').is_file() and not runtime.is_symlink()
 members=sorted(runtime.rglob('*'));files={str(p.relative_to(folder)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in members if p.is_file() and not p.is_symlink()}
 links={str(p.relative_to(folder)):os.readlink(p) for p in members if p.is_symlink()}
 archive=folder/'runtime.tar.gz';assert not archive.exists()
 with archive.open('xb') as raw:
  with tarfile.open(fileobj=raw,mode='w:gz',compresslevel=1) as tar:
   for p in [runtime,*members]:tar.add(p,arcname=str(p.relative_to(folder)),recursive=False)
 verified=set();link_seen={}
 with tarfile.open(archive,'r:gz') as tar:
  for member in tar:
   if member.isfile():
    assert hashlib.file_digest(tar.extractfile(member),'sha256').hexdigest()==files[member.name]['sha256']
    assert member.size==files[member.name]['bytes'];verified.add(member.name)
   elif member.issym():link_seen[member.name]=member.linkname
 assert verified==set(files) and link_seen==links
 assert all(sha(folder/n)==v['sha256'] for n,v in files.items())
 inventory=folder/'runtime-inventory.json.gz'
 with gzip.open(inventory,'wt',encoding='utf-8') as z:json.dump({'files':files,'symlinks':links},z,ensure_ascii=False)
 row={'run':folder.name,'archive':bind(archive),'archive_bytes':archive.stat().st_size,
 'original_bytes':sum(v['bytes'] for v in files.values()),'file_count':len(files),'inventory':bind(inventory),
 'full_restore_hash_verified':True,'restore':'tar -xzf runtime.tar.gz in its run folder only if runtime does not exist'}
 put(folder/'runtime-archive.json',row);shutil.rmtree(runtime);rows.append(row)
put(ART/'runtime-archives-loader.json',{'rows':rows,'original_bytes':sum(r['original_bytes'] for r in rows),'archive_bytes':sum(r['archive_bytes'] for r in rows),'all_restore_hashes_verified':True})
print('Archived',len(rows),'completed test runtimes; every file hash and symlink verified')
