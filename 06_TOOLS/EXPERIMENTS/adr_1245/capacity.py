from pathlib import Path
import json,sys,importlib.util,shutil
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1245-main128-oracle-records-live'
sp=importlib.util.spec_from_file_location('local_capacity',R/'06_TOOLS/maintenance/agent_record_oracle_r2.py');a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a)
db=a.connection()
with db.cursor() as c:
 c.execute("SELECT COALESCE(SUM(BYTES),0) FROM DBA_SEGMENTS WHERE OWNER='SIDDA'");used=c.fetchone()[0]
 c.execute("SELECT MAX_BYTES FROM DBA_TS_QUOTAS WHERE USERNAME='SIDDA' AND TABLESPACE_NAME='USERS'");quota=c.fetchone()[0]
db.close();disk=shutil.disk_usage(R);v={'sidda_used_bytes':used,'sidda_quota_bytes':quota,'sidda_used_percent':100*used/quota,'disk_used_percent':100*disk.used/disk.total,'limit_percent':90,'within_limit':used/quota<=.9 and disk.used/disk.total<=.9}
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
write_summary(A/'artifacts'/sys.argv[1],v);assert v['within_limit'];print(json.dumps(v))
