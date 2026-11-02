"""Local SIDDA90%-of-original-quota fence. No table DDL/data edits."""
from pathlib import Path
import importlib.util,json,os,fcntl,time,subprocess,sys,signal
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1252-main129-pinned-oracle-live';O=A/'artifacts/run-001';D=A/'artifacts/design'
ORIGINAL=300*1024**2;CAP=270*1024**2
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary

def connect():
 sp=importlib.util.spec_from_file_location('local_capacity_admin',R/'06_TOOLS/maintenance/agent_record_oracle_r2.py');a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a);return a.connection()
def inspect(db):
 with db.cursor() as c:
  c.execute("SELECT MAX_BYTES FROM DBA_TS_QUOTAS WHERE USERNAME='SIDDA' AND TABLESPACE_NAME='USERS'");quota=c.fetchone()[0]
  c.execute("SELECT COALESCE(SUM(BYTES),0) FROM DBA_SEGMENTS WHERE OWNER='SIDDA'");used=c.fetchone()[0]
  c.execute("SELECT COUNT(*) FROM DBA_SYS_PRIVS WHERE GRANTEE='SIDDA' AND PRIVILEGE='UNLIMITED TABLESPACE'");unlimited=c.fetchone()[0]
 return {'quota_bytes':quota,'used_bytes':used,'used_percent_of_original':100*used/ORIGINAL,'unlimited_tablespace_grant_count':unlimited}
def alter(db,expected,target):
 before=inspect(db)
 if before['quota_bytes']==target:return {'already_target':True,**before}
 if before['quota_bytes']!=expected:raise RuntimeError('Unexpected external SIDDA quota change; do not overwrite')
 if before['used_bytes']>CAP or before['unlimited_tablespace_grant_count']:raise RuntimeError('Quota fence precondition failed')
 with db.cursor() as c:c.execute('ALTER USER SIDDA QUOTA '+str(target//1024**2)+'M ON USERS')
 after=inspect(db);assert after['quota_bytes']==target and after['used_bytes']<=CAP
 return {'before':before,'after':after}

def main():
 lock=(R/'90_RUNTIME').resolve();lock.mkdir(exist_ok=True);fd=(lock/'adr1252-quota-fence.lock').open('a');fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 freeze=json.loads((D/'freeze.json').read_text())
 for relative,expected in freeze['files'].items():
  import hashlib
  with (R/relative).open('rb') as source:assert hashlib.file_digest(source,'sha256').hexdigest()==expected,'Frozen input changed:'+relative
 db=connect();before=inspect(db);assert before['quota_bytes']==ORIGINAL and before['used_bytes']<=CAP and not before['unlimited_tablespace_grant_count']
 write_summary(O/'quota-original.json',before);child=None;exitcode=None
 def interrupted(signum,frame):raise KeyboardInterrupt('quota controller interrupted')
 signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
 try:
  write_summary(O/'quota-applied.json',alter(db,ORIGINAL,CAP))
  with (O/'live-console.log').open('x') as log:
   child=subprocess.Popen([str(R/'.venv/bin/python'),'-u',str(R/'06_TOOLS/EXPERIMENTS/adr_1252/run.py'),'gold-369'],cwd=R,stdout=log,stderr=subprocess.STDOUT)
   exitcode=child.wait()
 finally:
  if child is not None and child.poll() is None:
   child.terminate()
   try:child.wait(timeout=8)
   except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
  try:restored=alter(db,CAP,ORIGINAL)
  except Exception:
   db.close();db=connect();restored=alter(db,CAP,ORIGINAL)
  write_summary(O/'quota-restored.json',{'restoration':restored,'child_exit_code':exitcode,'restored_original_quota':inspect(db)['quota_bytes']==ORIGINAL})
  db.close();fd.close()
 write_summary(O/'process-exit.json',{'exit_code':exitcode,'quota_restored':True});print('Worker exit',exitcode,'original quota restored')
 if exitcode:raise SystemExit(exitcode if exitcode>0 else 128-exitcode)
if __name__=='__main__':main()
