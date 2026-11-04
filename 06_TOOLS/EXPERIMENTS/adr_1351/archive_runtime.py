"""Losslessly preserve closed isolated runtimes before removing duplicate bytes."""
from common import *
import tarfile,shutil
for proc in Path('/proc').glob('[0-9]*/cmdline'):
 try:args=proc.read_bytes().split(b'\0')
 except (FileNotFoundError,PermissionError):continue
 assert not any(a.endswith(b'/adr_1351/live_public.py') for a in args),'Live worker still running'
rows=[]
for area in ('public-ready','public-admission','public-live'):
 for folder in sorted((ART/area).glob('*')):
  runtime=folder/'runtime'
  if not runtime.exists():continue
  assert (folder/'result.json').exists() or (folder/'runner-failure.json').exists() or (folder/'preflight-stop.json').exists(), str(folder)
  assert runtime.is_dir() and not runtime.is_symlink()
  members=sorted(runtime.rglob('*'))
  files={str(p.relative_to(folder)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in members if p.is_file() and not p.is_symlink()}
  links={str(p.relative_to(folder)):os.readlink(p) for p in members if p.is_symlink()}
  archive=folder/'runtime.tar.gz'
  with archive.open('xb') as out:
   with tarfile.open(fileobj=out,mode='w:gz',compresslevel=1,dereference=False) as tar:
    for p in [runtime,*members]:tar.add(p,arcname=str(p.relative_to(folder)),recursive=False)
  verified=set();seen_links={}
  with tarfile.open(archive,'r:gz') as tar:
   for member in tar:
    if member.isfile():
     assert member.name in files
     assert hashlib.file_digest(tar.extractfile(member),'sha256').hexdigest()==files[member.name]['sha256']
     assert member.size==files[member.name]['bytes'];verified.add(member.name)
    elif member.issym():seen_links[member.name]=member.linkname
  assert verified==set(files) and seen_links==links
  assert all(sha(folder/n)==v['sha256'] for n,v in files.items())
  inv=write_raw_json(folder/'runtime-inventory.json.gz',{'files':files,'symlinks':links})
  receipt={'archive':{'path':str(archive.relative_to(ROOT)),'sha256':sha(archive)},'original_bytes':sum(v['bytes'] for v in files.values()),'archive_bytes':archive.stat().st_size,'file_count':len(files),'inventory':inv,'full_restore_hash_verified':True,'restore':'In this cell folder, only if runtime is absent: tar -xzf runtime.tar.gz','no_live_process':True}
  put(folder/'runtime-archive.json',receipt);shutil.rmtree(runtime);rows.append({'cell':folder.name,'area':area,**receipt})
put(ART/'runtime-archives.json',{'rows':rows,'all_restore_hashes_verified':True,'original_bytes':sum(r['original_bytes'] for r in rows),'archive_bytes':sum(r['archive_bytes'] for r in rows)})
print('Closed runtimes archived and every original file SHA verified:',len(rows))
