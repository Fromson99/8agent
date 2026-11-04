from common import *
import tarfile,shutil
for name in ['ADR-1315-bounded-structure-query-main']:
 art=ROOT/'04_EXPERIMENTS/ADR'/name/'artifacts';records=[]
 folders=[p for p in art.iterdir() if p.is_dir() and (p/'runtime').is_dir()]+[p for p in (art/'actual').iterdir() if (p/'runtime').is_dir()]
 for folder in folders:
  runtime=folder/'runtime';assert (folder/'result.json').exists();r=read(folder/'result.json');assert r['code_unchanged'];members=sorted(runtime.rglob('*'));files={str(p.relative_to(folder)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in members if p.is_file() and not p.is_symlink()};links={str(p.relative_to(folder)):os.readlink(p) for p in members if p.is_symlink()};archive=folder/'runtime.tar.gz'
  with archive.open('xb') as out:
   with tarfile.open(fileobj=out,mode='w:gz',compresslevel=1,dereference=False) as tar:
    for p in [runtime,*members]:tar.add(p,arcname=str(p.relative_to(folder)),recursive=False)
  checked=set();seenlinks={}
  with tarfile.open(archive,'r:gz') as tar:
   for member in tar:
    if member.isfile():assert member.name in files;assert hashlib.file_digest(tar.extractfile(member),'sha256').hexdigest()==files[member.name]['sha256'];checked.add(member.name)
    elif member.issym():seenlinks[member.name]=member.linkname
  assert checked==set(files) and seenlinks==links;assert all(sha(folder/n)==v['sha256'] for n,v in files.items())
  inventory=write_raw_json(folder/'runtime-inventory.json.gz',{'files':files,'symlinks':links});row={'folder':str(folder.relative_to(ROOT)),'file_count':len(files),'original_bytes':sum(v['bytes'] for v in files.values()),'archive':str(archive.relative_to(ROOT)),'archive_sha256':sha(archive),'inventory':inventory,'every_file_restore_hash_verified':True,'restore':'When runtime absent: tar -xzf runtime.tar.gz from this folder'};put(folder/'runtime-archive.json',row);shutil.rmtree(runtime);records.append(row)
 put(art/'runtime-archives.json',{'rows':records,'all_restore_hashes_verified':True});print(name,'closed runtimes',len(records),flush=True)
