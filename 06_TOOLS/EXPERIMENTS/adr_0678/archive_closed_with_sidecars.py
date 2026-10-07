"""Losslessly retain closed SQLite databases AND their durable sidecars.

No checkpoint, SQL update, or model replay. Restore every file in a bundle to
its original name before opening the database. Original bytes remain available
in gzip files with verified hashes; receipts are durable before unlinking.
"""
from pathlib import Path
import json,gzip,hashlib,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0678-investigation-contract-completion'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
active=set();scheduler_active=False
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:args=p.read_bytes().decode().split('\0')
 except (OSError,UnicodeError):continue
 if any(arg.endswith('/adr_0678/run_all.py') or arg=='06_TOOLS/EXPERIMENTS/adr_0678/run_all.py' for arg in args):scheduler_active=True
 if any('adr_0678/run_case.py' in arg for arg in args) and '--case' in args:active.add(args[args.index('--case')+1])
assert not scheduler_active and not active,'Wait for every product/archive worker to exit'
for result in sorted(list(A.glob('artifacts/run-001/integrated/*/result.json'))+list(A.glob('artifacts/regression/integrated/*/result.json'))):
 directory=result.parent
 if directory.name in active:continue
 receipt=directory/'runtime-sidecar-archives.json'
 if receipt.exists():continue
 groups=[]
 for db in sorted((directory/'runtime').rglob('*.sqlite')):
  if db.name not in ('journal.sqlite','cases-v4.sqlite','cases-v3.sqlite'):continue
  paths=[db]+[Path(str(db)+s) for s in ('-wal','-shm','-journal') if Path(str(db)+s).exists()]
  group={'database':str(db.relative_to(R)),'restore':'Restore all listed gzip members to their original paths before opening SQLite; do not omit WAL or a rollback journal.','files':[]}
  for source in paths:
   target=Path(str(source)+'.gz');assert not target.exists(),target
   before=source.stat();h=hashlib.sha256()
   with source.open('rb') as src,gzip.open(target,'xb',compresslevel=6) as dst:
    for chunk in iter(lambda:src.read(1024*1024),b''):h.update(chunk);dst.write(chunk)
   original=h.hexdigest();h=hashlib.sha256();size=0
   with gzip.open(target,'rb') as f:
    for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk);size+=len(chunk)
   assert original==h.hexdigest() and size==before.st_size and source.stat().st_mtime_ns==before.st_mtime_ns
   group['files'].append({'path':str(source.relative_to(R)),'archive_path':str(target.relative_to(R)),
      'uncompressed_sha256':original,'archive_sha256':sha(target),'uncompressed_bytes':size,'archive_bytes':target.stat().st_size,'verified_lossless':True})
  groups.append(group)
 if not groups:continue
 receipt.write_text(json.dumps({'schema_version':'sqlite-sidecar-lossless-v1','groups':groups},ensure_ascii=False,indent=2)+'\n')
 with receipt.open('rb') as f:os.fsync(f.fileno())
 for group in groups:
  for row in group['files']:
   source=R/row['path'];assert sha(source)==row['uncompressed_sha256'];source.unlink()
 print('LOSSLESS_DATABASE_BUNDLE',directory.name,len(groups),flush=True)
