"""Post-output lossless preservation of closed SQLite databases AND retained WAL/SHM bytes.
No experiment/product file changes; no SQLite checkpoint or writes; restore all listed files together.
"""
from pathlib import Path
import gzip,hashlib,json,os,time,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization/artifacts'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
while True:
 done=list(A.glob('run-001/integrated/*/result.json'))+list(A.glob('regression/integrated/*/result.json'))
 for result in done:
  if time.time()-result.stat().st_mtime<20:continue
  d=result.parent;cid=d.name
  live=subprocess.run(['ps','-eo','args'],capture_output=True,text=True,check=True).stdout.splitlines()
  if any(('run_case.py' in x or 'archive_case.py' in x) and '--case '+cid in x for x in live):continue
  receipt=d/'runtime-archives.json';rows=json.loads(receipt.read_text()) if receipt.exists() else []
  files=[p for p in (d/'runtime').rglob('*') if p.is_file() and any(p.name==n+s for n in ('journal.sqlite','cases-v4.sqlite') for s in ('','-wal','-shm','-journal'))]
  for p in files:
   target=p.with_name(p.name+'.gz');before=p.stat();h=sha(p)
   if not target.exists():
    with p.open('rb') as f,gzip.open(target,'wb',compresslevel=6) as out:
     for block in iter(lambda:f.read(8*1024*1024),b''):out.write(block)
   digest=hashlib.sha256();size=0
   with gzip.open(target,'rb') as f:
    for block in iter(lambda:f.read(8*1024*1024),b''):digest.update(block);size+=len(block)
   assert digest.hexdigest()==h and size==before.st_size and before.st_mtime_ns==p.stat().st_mtime_ns
   row={'path':str(p.relative_to(R)),'uncompressed_sha256':h,'uncompressed_bytes':size,'archive_path':str(target.relative_to(R)),'archive_sha256':sha(target),'archive_bytes':target.stat().st_size,'verified_lossless':True,'restore_rule':'Restore database plus any archived -wal/-shm/-journal under their original names before SQLite open; raw bytes never checkpointed or changed.'}
   if not any(x['path']==row['path'] for x in rows):rows.append(row)
   receipt.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
   with receipt.open('rb') as f:os.fsync(f.fileno())
   p.unlink();print('ARCHIVED_EXACT_BYTES',cid,p.name,size,target.stat().st_size,flush=True)
 if len(done)==40 and all(not any(p.is_file() and p.name in ('journal.sqlite','cases-v4.sqlite','cases-v4.sqlite-wal','cases-v4.sqlite-shm') for p in (x.parent/'runtime').rglob('*')) for x in done):break
 time.sleep(15)
