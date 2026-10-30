"""Remove only this experiment's superseded, reproducible export copies."""
from pathlib import Path
import json,hashlib,shutil,subprocess,fcntl,datetime
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1214-gold-main120-engine-implementation/artifacts'
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert (A/'run-001/import-result.json').exists()
assert json.loads((A/'run-001/import-result.json').read_text())['status']=='COMPLETE_NOT_ACTIVATED'
names=['attempt-full-glossary-before-user-scope','attempt-scoped-rowid-error','attempt-scoped-fts-view-stall','attempt-scoped-mapping-status']
assert not (A/'cleanup-result.json').exists()
with (A/'run-001/publisher.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 paths=[]
 for name in names:
  directory=A/name
  for base in ('extension.sqlite','extension.partial.sqlite'):
   for suffix in ('','-journal','-wal','-shm'):
    p=directory/(base+suffix)
    if p.exists():
     assert not p.is_symlink() and p.resolve().parent==directory.resolve()
     status=subprocess.run(['fuser',str(p)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
     assert status.returncode==1,('file in use or ownership check failed',str(p))
     paths.append(p)
 records=[{'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':sha(p),'purpose':'superseded export copy; never an active source or Oracle publication'} for p in paths]
 before={str(p):shutil.disk_usage(p).free for p in (R,Path('/mnt/c'))}
 put(A/'cleanup-before.json',{'files':records,'free_bytes':before,'authorization':'User requested deletion of unneeded old DB/test copies; only our superseded exports selected','preserved':'Original 9 corpus databases, current extension.sqlite, all raw failure logs, manifests, frozen revisions, Oracle rows and model journals'})
 for p in paths:p.unlink()
 put(A/'cleanup-result.json',{'deleted_files':records,'logical_bytes_removed':sum(x['bytes'] for x in records),'free_bytes_before':before,'free_bytes_after':{str(p):shutil.disk_usage(p).free for p in (R,Path('/mnt/c'))},'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'all_selected_files_absent':all(not p.exists() for p in paths),'manual_trim_run':False})
 print('REMOVED_BYTES',sum(x['bytes'] for x in records))
