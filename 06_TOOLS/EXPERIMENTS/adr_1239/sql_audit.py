from pathlib import Path
import json,datetime,collections,sys,gzip,hashlib
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1239-main124-gold-live-revalidation';O=A/'artifacts/run-001';cid=sys.argv[1];P=O/'live'/cid
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
pending={};groups=collections.defaultdict(lambda:{'started':0,'acknowledged':0,'seconds':0.0,'max_seconds':0.0});errors=[]
for line in (O/('live-'+cid+'.log')).read_text().splitlines():
 try:x=json.loads(line)
 except ValueError:continue
 if x.get('event')!='oracle.sql':continue
 key=(x['binding'],x['call']);stamp=datetime.datetime.fromisoformat(x['ts']).timestamp()
 if x['status']=='STARTED':
  h=x['sql_sha256'];g=groups[h];pending[key]=(stamp,h);g['started']+=1
 elif key in pending:
  begin,h=pending.pop(key);g=groups[h];seconds=stamp-begin;g['seconds']+=seconds;g['max_seconds']=max(g['max_seconds'],seconds)
  if x['status']=='ACKNOWLEDGED':g['acknowledged']+=1
  else:errors.append(x)
if '--progress' in sys.argv:print(json.dumps({'started':sum(g['started'] for g in groups.values()),'acknowledged':sum(g['acknowledged'] for g in groups.values()),'SQL_boundary_seconds':sum(g['seconds'] for g in groups.values()),'top_shapes':sorted(groups.items(),key=lambda x:x[1]['seconds'],reverse=True)[:3]},ensure_ascii=False,indent=2));raise SystemExit()
with gzip.open(P/'sql-statements.json.gz','rt') as f:statements=json.load(f)
shapes={hashlib.sha256(s.encode()).hexdigest():s for s in statements};rows=[]
for h,g in sorted(groups.items(),key=lambda x:x[1]['seconds'],reverse=True):rows.append({'sql_sha256':h,**g,'statement_available':h in shapes})
result={'traced_physical_statements':len(statements),'metadata_preflight_selects':1,'all_observed_sql_including_mapping_preflight':len(statements)+1,'separate_pre_run_preflight_sql_including_metadata':5,'log_started':sum(g['started'] for g in groups.values()),'log_acknowledged':sum(g['acknowledged'] for g in groups.values()),'SQL_boundary_seconds':sum(g['seconds'] for g in groups.values()),'boundary':'oracle.sql STARTED to ACKNOWLEDGED/FAILED: includes transport/Oracle/result boundary, not Oracle CPU alone; mapping metadata preflight is a separate SELECT. Overall run seconds exclude connector open/preflight.','unclosed_log_calls':len(pending),'errors':errors,'shapes':rows,'new_sql':0,'new_models':0}
write_summary(P/'sql-audit.json',result);print(json.dumps({k:v for k,v in result.items() if k!='shapes'},ensure_ascii=False,indent=2))
