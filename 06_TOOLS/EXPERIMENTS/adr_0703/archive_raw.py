"""Losslessly archive this experiment's closed raw records once, with restore hashes."""
from pathlib import Path
import hashlib,json,tarfile,shutil,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0703-exception-coupled-final-holdout';O=A/'artifacts/run-001'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
assert (O/'result.json').exists(),'Audit all raw journals before archiving'
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:args=p.read_bytes().decode().split('\0')
 except (OSError,UnicodeError):continue
 assert not any(x.endswith('adr_0703/run_case.py') for x in args),'A case is still running'
for result in O.glob('*/*/result.json'):
 directory=result.parent;receipt=directory/'raw-archive-receipt.json'
 if receipt.exists():continue
 roots=[directory/k for k in ('provider','runtime') if (directory/k).is_dir()]
 files={str(p.relative_to(directory)):sha(p) for root in roots for p in root.rglob('*') if p.is_file()}
 assert all(not p.is_symlink() for root in roots for p in root.rglob('*')),'Unexpected link in raw runtime'
 archive=directory/'raw.tar.gz'
 with tarfile.open(archive,'x:gz',compresslevel=6) as t:
  for root in roots:t.add(root,arcname=root.name)
 restored={}
 with tarfile.open(archive,'r|gz') as t:
  for member in t:
   if member.isfile():
    h=hashlib.sha256();stream=t.extractfile(member)
    for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    restored[member.name]=h.hexdigest()
 assert files==restored
 record={'archive':str(archive.relative_to(R)),'sha256':sha(archive),'files':files,'verified_lossless':True,
  'restore':'tar -xzf raw.tar.gz in this case directory restores provider/ and runtime/. Restore all SQLite WAL/SHM/journal members together before opening a database.',
  'original_execution_not_replayed':True}
 receipt.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
 with receipt.open('rb') as f:os.fsync(f.fileno())
 for p,h in files.items():assert sha(directory/p)==h,p
 # Remove only newly created, closed raw copies after exact restoration checks.
 for root in roots:shutil.rmtree(root)
 print('Archived',directory.parent.name,directory.name,len(files),flush=True)
