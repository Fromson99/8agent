"""Research-only common SQL accounting and prewrite capacity observation."""
from pathlib import Path
import json,time,os,threading,shutil
from semantic_runtime.oracle_dp_io import DPError,BudgetPause
class SharedBudget:
 def __init__(self,limit,initial_calls=0):self.limit=limit;self.calls=initial_calls;self.by_port={'source':initial_calls,'agent':0};self.lock=threading.RLock()
 def reserve(self,port):
  with self.lock:
   if self.calls>=self.limit:raise BudgetPause('EXPERIMENT_SHARED_SQL_LIMIT: source+Agent request10000 exhausted; no redispatch')
   self.calls+=1;self.by_port[port]+=1
class CapacityGuard:
 def __init__(self,db,out,quota_limit=.9,reserve_bytes=2*1024**2,reference_quota=None):
  self.reference_quota=reference_quota
  self.db=db;self.out=Path(out);self.limit=quota_limit;self.reserve=reserve_bytes;self.lock=threading.RLock();self.queries=0
  self.stream=(self.out/'capacity-samples.jsonl').open('x',buffering=1)
 def sample(self,write=False):
  with self.lock:
   with self.db.cursor() as c:
    c.execute("SELECT COALESCE(SUM(BYTES),0) FROM DBA_SEGMENTS WHERE OWNER='SIDDA'");used=c.fetchone()[0]
    c.execute("SELECT MAX_BYTES FROM DBA_TS_QUOTAS WHERE USERNAME='SIDDA' AND TABLESPACE_NAME='USERS'");quota=c.fetchone()[0];self.queries+=2
   actual_quota=quota;quota=self.reference_quota or quota
   disk=shutil.disk_usage('/home/jin/8-AGENT');v={'at':time.time(),'before_write':write,'sidda_used_bytes':used,'quota_bytes':quota,'actual_server_quota_bytes':actual_quota,'used_percent':used/quota*100,'reserve_bytes':self.reserve if write else 0,'disk_used_percent':disk.used/disk.total*100}
   self.stream.write(json.dumps(v)+'\n');self.stream.flush();os.fsync(self.stream.fileno())
   if actual_quota!=270*1024**2:raise DPError('SERVER_QUOTA_CHANGED: fixed270MiB cap absent, no write permitted')
   if used+(self.reserve if write else 0)>quota*self.limit or disk.used>disk.total*self.limit:
    p=self.out/'capacity-stop.json'
    if not p.exists():p.write_text(json.dumps(v,indent=2)+'\n')
    raise DPError('EXPERIMENT_CAPACITY_GUARD: reserve before next Agent write; no quota extension/delete/retry')
   return v
 def close(self):self.stream.close();self.db.close()
