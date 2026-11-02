from common import *
import importlib.util,shutil
p=ROOT/'06_TOOLS/maintenance/agent_record_oracle_r2.py';s=importlib.util.spec_from_file_location('storage_repair_admin',p);a=importlib.util.module_from_spec(s);s.loader.exec_module(a);db=a.connection();old=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1245-main128-oracle-records-live/artifacts/run-001/live/gold-369/record-binding.json')['scope']
with db.cursor() as c:
 c.execute("SELECT SUM(BYTES) FROM DBA_SEGMENTS WHERE OWNER='SIDDA'");used=c.fetchone()[0]
 c.execute("SELECT MAX_BYTES FROM DBA_TS_QUOTAS WHERE USERNAME='SIDDA' AND TABLESPACE_NAME='USERS'");quota=c.fetchone()[0]
 counts={}
 for table in ('LGL_AGT_RUN_A','LGL_AGT_REC_A','LGL_AGT_BODY_A','LGL_EXEC_ST_A'):
  c.execute('SELECT COUNT(*) FROM SIDDA.'+table+' WHERE SCOPE_HASH_VAL=:scope',scope=old);counts[table]=c.fetchone()[0]
 c.execute('SELECT ST_CD FROM SIDDA.LGL_AGT_RUN_A WHERE SCOPE_HASH_VAL=:scope',scope=old);status=c.fetchone()[0]
db.close();assert list(counts.values())==[1,2987,52742,52] and status=='FAILED'
disk=shutil.disk_usage(ROOT);value={'sidda_used_bytes':used,'sidda_quota_bytes':quota,'sidda_used_percent':100*used/quota,'disk_used_percent':100*disk.used/disk.total,'maximum_allowed_percent':90,'within_limit':used/quota<=.9 and disk.used/disk.total<=.9,'original_failed_scope_counts':counts,'original_failed_status':status,'old_records_deleted_or_reencoded':False}
assert value['within_limit'];put(RUN/'capacity-after.json',value);print(json.dumps(value))
