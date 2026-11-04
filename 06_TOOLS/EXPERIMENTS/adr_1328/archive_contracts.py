from common import *
import tarfile,shutil
folders=[ART/n for n in ('contracts','working-api')]
for proc in Path('/proc').glob('[0-9]*/cmdline'):
 try:args=proc.read_bytes().split(b'\0')
 except (FileNotFoundError,PermissionError):continue
 assert not any(a.endswith(('/adr_'+n+'/check.py').encode()) for a in args for n in ('1328',)),'test process active'
out=ART/'runtime-archives';out.mkdir(exist_ok=True);rows=[]
for folder in folders:
 runtime=folder/'runtime'
 if not runtime.exists():continue
 assert (folder/'result.json').is_file() and not runtime.is_symlink()
 tag=folder.parent.parent.name.split('-')[1]+'-'+folder.name;members=sorted(runtime.rglob('*'))
 files={str(p.relative_to(folder)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in members if p.is_file() and not p.is_symlink()}
 links={str(p.relative_to(folder)):os.readlink(p) for p in members if p.is_symlink()};archive=out/(tag+'.tar.gz')
 with archive.open('xb') as f:
  with tarfile.open(fileobj=f,mode='w:gz',compresslevel=1,dereference=False) as tar:
   for p in [runtime,*members]:tar.add(p,arcname=str(p.relative_to(folder)),recursive=False)
 verified=set();seen_links={}
 with tarfile.open(archive,'r:gz') as tar:
  for member in tar:
   if member.isfile():
    assert member.name in files and hashlib.file_digest(tar.extractfile(member),'sha256').hexdigest()==files[member.name]['sha256'];verified.add(member.name)
   elif member.issym():seen_links[member.name]=member.linkname
 assert verified==set(files) and seen_links==links
 assert all(sha(folder/n)==v['sha256'] for n,v in files.items())
 inv=write_raw_json(out/(tag+'-inventory.json.gz'),{'files':files,'symlinks':links})
 row={'original_folder':str(folder.relative_to(ROOT)),'archive':str(archive.relative_to(ROOT)),'archive_sha256':sha(archive),'file_count':len(files),'original_bytes':sum(v['bytes'] for v in files.values()),'archive_bytes':archive.stat().st_size,'inventory':inv,'full_restore_hash_verified':True,'restore':'Extract archive in original_folder only when runtime absent'}
 put(out/(tag+'-receipt.json'),row);shutil.rmtree(runtime);rows.append(row)
put(ART/'contract-runtime-archives.json',{'rows':rows,'no_live_process':True,'all_files_hash_verified':True,'failed_results_unchanged':True})
print('Archived',len(rows),'closed fixture runtimes with every file hash verified')
