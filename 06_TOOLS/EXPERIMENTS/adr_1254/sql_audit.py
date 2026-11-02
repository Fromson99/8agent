from pathlib import Path
import json,sys,collections,datetime
R=Path('/home/jin/8-AGENT');O=R/'04_EXPERIMENTS/ADR/ADR-1254-main129-oracle-reused-space-live/artifacts/run-001'
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
starts={};groups={};shapes={}
for line in (O/'live-console.log').open():
 try:v=json.loads(line)
 except ValueError:continue
 if v.get('event')!='oracle.sql':continue
 key=(v['binding'],v['call']);g=groups.setdefault(v['binding'],{'started':0,'acknowledged':0,'boundary_seconds':0,'writes':0,'failed_before_ack':0})
 if v['status']=='STARTED':starts[key]=v;g['started']+=1;g['writes']+=int(v.get('write',False))
 elif v['status']=='ACKNOWLEDGED':
  g['acknowledged']+=1;old=starts.pop(key,None)
  if old:
   seconds=(datetime.datetime.fromisoformat(v['ts'])-datetime.datetime.fromisoformat(old['ts'])).total_seconds();g['boundary_seconds']+=seconds;k=(v['binding'],old['sql_sha256']);row=shapes.setdefault(k,{'binding':k[0],'sql_sha256':k[1],'calls':0,'seconds':0});row['calls']+=1;row['seconds']+=seconds

 elif v['status']=='FAILED':
  g['failed_before_ack']+=1;starts.pop(key,None)
value={'groups':groups,'unclosed_calls':[{'binding':k[0],'call':k[1]} for k in starts],'top_shapes_by_time':sorted(shapes.values(),key=lambda x:x['seconds'],reverse=True)[:20],'top_shapes_by_calls':sorted(shapes.values(),key=lambda x:x['calls'],reverse=True)[:20],'boundary':'SQL client STARTED to ACKNOWLEDGED, includes transport/serialization/DB; not Oracle CPU'}
write_summary(O/'sql-audit.json',value);print(json.dumps(groups))
