"""Lossless archive of this task's completed synthetic fixtures only."""
from pathlib import Path
import gzip,hashlib,json,os,shutil,tarfile
H=Path(__file__).resolve().parent
names=['test-code','test-runtime','final-transfer','initial-final-transfer']
assert all((H/n).is_dir() and not (H/n).is_symlink() for n in names)
# No process may retain a cwd, open descriptor or command line in these fixtures.
roots=[str(H/n) for n in names]
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
 try:
  paths=[os.readlink(proc/'cwd')]+[os.readlink(p) for p in (proc/'fd').iterdir()]
  command=(proc/'cmdline').read_bytes().decode(errors='replace')
 except (OSError,PermissionError):continue
 hits=[v for v in paths if any(v.startswith(root+'/') or v==root for root in roots)]
 assert not hits,(proc.name,command[:300],hits[:5])
 assert not any(root in command for root in roots),proc.name

def hash_file(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
files={};links={};size=0
for n in names:
 for p in (H/n).rglob('*'):
  name=str(p.relative_to(H))
  if p.is_symlink():links[name]=os.readlink(p)
  elif p.is_file():files[name]=hash_file(p);size+=p.stat().st_size
archive=H/'SYNTHETIC_TESTS.tar.gz';assert not archive.exists()
with tarfile.open(archive,'w:gz',compresslevel=6) as t:
 for n in names:t.add(H/n,arcname=n,recursive=True)
seen={};seen_links={}
with tarfile.open(archive,'r:gz') as t:
 for info in t:
  if info.isfile():
   h=hashlib.sha256();f=t.extractfile(info)
   for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
   seen[info.name]=h.hexdigest()
  elif info.issym():seen_links[info.name]=info.linkname
  elif info.islnk():seen[info.name]=files[info.linkname]
assert seen==files and seen_links==links
manifest=H/'SYNTHETIC_TESTS_FILES.json.gz';manifest.write_bytes(gzip.compress((json.dumps({'files':files,'symlinks':links},ensure_ascii=False,sort_keys=True)+'\n').encode(),mtime=0))
receipt={'status':'VERIFIED_AND_COMPACTED','archive':archive.name,'sha256':hash_file(archive),'source_files':len(files),'source_bytes':size,
 'archive_bytes':archive.stat().st_size,'manifest':manifest.name,'manifest_sha256':hash_file(manifest),
 'roots':names,'restore':'From this handoff directory: tar -xzf SYNTHETIC_TESTS.tar.gz; compare file SHA-256 with SYNTHETIC_TESTS_FILES.json.gz before reusing evidence.'}
for n in names:shutil.rmtree(H/n)
(H/'TEST_RUNTIME_ARCHIVE.json').write_text(json.dumps(receipt,indent=2)+'\n')
# Preserve submitted MIME bytes losslessly; final attachment artifacts stay separately available.
p=H/'EMAIL_ARGS.json'
with p.open('rb') as src,gzip.open(H/'EMAIL_ARGS.json.gz','wb',compresslevel=6) as dst:shutil.copyfileobj(src,dst)
with gzip.open(H/'EMAIL_ARGS.json.gz','rb') as f:
 h=hashlib.sha256()
 for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
assert h.hexdigest()==hash_file(p);p.unlink()
print(json.dumps({k:v for k,v in receipt.items() if k not in ('roots','restore')}))
