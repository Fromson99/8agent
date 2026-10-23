"""Preserve byte-verified completed runtime in a lossless archive."""
from common import *
import tarfile,hashlib,shutil
assert read(ART/'result.json')['status']=='COMPLETE'
assert all(r['exit_code']==0 for r in read(ART/'guard-result.json')['records'])
for process in Path('/proc').iterdir():
 if not process.name.isdigit():continue
 try:args=(process/'cmdline').read_bytes().split(b'\0')
 except OSError:continue
 assert not any(a.endswith((b'adr_0992/full_query.py',b'adr_0992/run_case.py')) for a in args)
runtime=ART/'known-query/candidate/runtime';archive=runtime.with_name('runtime.tar.gz')
assert runtime.is_dir() and not archive.exists()
assert not any(p.is_symlink() for p in runtime.rglob('*'))
members=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(runtime.rglob('*')) if p.is_file()]
with tarfile.open(archive,'w:gz',compresslevel=6) as out:
 for item in members:out.add(ROOT/item['path'],arcname=item['path'],recursive=False)
with tarfile.open(archive,'r:gz') as inp:
 for item in members:
  f=inp.extractfile(item['path']);assert f is not None
  assert hashlib.file_digest(f,'sha256').hexdigest()==item['sha256']
  assert inp.getmember(item['path']).size==item['bytes']
save(archive.with_name('runtime-archive.json'),{'archive':str(archive.relative_to(ROOT)),'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'original_bytes':sum(i['bytes'] for i in members),'members':members,'all_members_verified':True,'restore_from_repository_root':'tar -xzf '+str(archive.relative_to(ROOT)),'reason':'Completed own process; only verified uncompressed duplicate removed. Raw model requests/responses remain directly accessible.'})
shutil.rmtree(runtime)
print(len(members),'runtime files archived; bytes',sum(i['bytes'] for i in members),'->',archive.stat().st_size)
