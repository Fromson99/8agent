from pathlib import Path
import json,sys,importlib.util,shutil
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1252-main129-pinned-oracle-live';sp=importlib.util.spec_from_file_location('oracle_capacity',R/'06_TOOLS/maintenance/agent_record_oracle_r2.py');a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a);db=a.connection()
with db.cursor() as c:
 c.execute("SELECT COALESCE(SUM(BYTES),0) FROM DBA_SEGMENTS WHERE OWNER='SIDDA'");used=c.fetchone()[0]
 c.execute("SELECT MAX_BYTES FROM DBA_TS_QUOTAS WHERE USERNAME='SIDDA' AND TABLESPACE_NAME='USERS'");quota=c.fetchone()[0]
 c.execute("SELECT MAX(NEXT_EXTENT) FROM DBA_SEGMENTS WHERE OWNER='SIDDA'");extent=c.fetchone()[0]
db.close();disk=shutil.disk_usage(R);v={'sidda_used_bytes':used,'sidda_quota_bytes':quota,'sidda_used_percent':100*used/quota,'largest_next_extent_bytes':extent,'prewrite_reserve_bytes':2*1024**2,'disk_used_percent':100*disk.used/disk.total,'maximum_used_percent':90,'within_limit':used/quota<=.9 and disk.used/disk.total<=.9,'has_initial_write_reserve':used+2*1024**2<=quota*.9}
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary;write_summary(A/'artifacts'/sys.argv[1],v);assert v['within_limit'] and (v['has_initial_write_reserve'] if sys.argv[1].startswith('design/') else True);print(json.dumps(v))
