"""Local SIDDA90%-of-original-quota fence. No table DDL/data edits."""
from pathlib import Path
import importlib.util,json,os,fcntl,time,subprocess,sys,signal
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1262-main130-progress-dedup-live';O=A/'artifacts/run-001';D=A/'artifacts/design'
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
 import hashlib
 lock=R/'90_RUNTIME/oracle-heavy-model-run.lock';lock.parent.mkdir(exist_ok=True);fd=lock.open('a');fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 freeze=json.loads((D/'freeze.json').read_text())
 for relative,expected in freeze['files'].items():
  with (R/relative).open('rb') as source:assert hashlib.file_digest(source,'sha256').hexdigest()==expected,'Frozen input changed:'+relative
 db=connect();before=inspect(db);assert before['quota_bytes']==CAP and before['used_bytes']<=CAP and not before['unlimited_tablespace_grant_count']
 write_summary(O/'quota-before.json',before);child=None;exitcode=None
 def interrupted(signum,frame):raise KeyboardInterrupt('controller interrupted')
 signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
 try:
  with (O/'live-console.log').open('x') as log:
   child=subprocess.Popen([str(R/'.venv/bin/python'),'-u',str(R/'06_TOOLS/EXPERIMENTS/adr_1262/run.py'),'gold-369'],cwd=R,stdout=log,stderr=subprocess.STDOUT);exitcode=child.wait()
 finally:
  if child is not None and child.poll() is None:
   child.terminate()
   try:child.wait(timeout=8)
   except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
  after=inspect(db);write_summary(O/'retained-quota.json',{'capacity':after,'child_exit_code':exitcode,'hard270MiB_still_present':after['quota_bytes']==CAP,'allocation_under_original90percent':after['used_bytes']<=CAP,'quota_alter_by_controller':0});db.close();fd.close()
 write_summary(O/'process-exit.json',{'exit_code':exitcode,'quota_retained270MiB':after['quota_bytes']==CAP});print('Worker exit',exitcode,'quota retained270MiB')
 assert after['quota_bytes']==CAP and after['used_bytes']<=CAP
 if exitcode:raise SystemExit(exitcode if exitcode>0 else 128-exitcode)
if __name__=='__main__':main()
