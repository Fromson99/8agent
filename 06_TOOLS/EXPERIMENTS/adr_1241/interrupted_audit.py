"""Recover only persisted evidence after resource guard exit125; never resume inference."""
from pathlib import Path
import json,hashlib,sys,datetime,collections,os
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1241-main125-gold-live-revalidation';D=A/'artifacts/design';O=A/'artifacts/run-001';P=O/'live/gold-369';POST=P/'post-stop';POST.mkdir()
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
read=lambda p:json.loads(p.read_text())
stop=read(P/'resource-stop.json');calls=read(P/'calls.json');assert stop['reason']=='HOST_SWAP_GROWTH' and not (P/'result.json').exists() and len(calls)==4 and calls[-1]['status']=='started'
seconds=(P/'resource-stop.json').stat().st_mtime-(P/'request.json').stat().st_mtime
r={'schema_version':'post-stop-persisted-evidence-v1','case_id':'gold-369','status':'RESOURCE_INTERRUPTED','http_status':None,'seconds':seconds,'elapsed_basis':'Approximate persisted request.json mtime to resource-stop.json mtime, not normal monotonic run timer','model_calls':len(calls),'known_complete_responses':3,'unknown':1,'unknown_classification':'One request entered transport boundary and lacked persisted result at host resource interruption; provider acceptance/outcome unknown, not observed blank response or native timeout','resource_stop':stop,'normal_finally_artifacts_missing':['result.json','resources.json.gz','sql-statements.json.gz','sqlite-opens.json'],'exact_peak_memory_and_swap_growth':None,'swap_growth_trigger_bytes':128*1024**2,'worker_exit_code_observed':125,'rerun':False,'quality_certified':False}
write_summary(POST/'interruption.json',r)
# Reuse the original read-only source/ACL/wire inspector, with explicit missing
# measurements and separate derived output destinations. Original checkpoints stay intact.
s=(R/'06_TOOLS/EXPERIMENTS/adr_1241/audit.py').read_text()
s=s.replace("result=read(P/'result.json')",'result=INTERRUPTION')
s=s.replace("a['other_seconds']=result['seconds']-a['model_seconds']","a['other_seconds']=None;a['elapsed_basis']=result['elapsed_basis'];a['model_seconds_complete_only']=True")
s=s.replace("for name in read(P/'sqlite-opens.json'):","a['sqlite_corpus_fallback']=None\nfor name in []:")
s=s.replace("P/'audit-detail.json.gz'","POST/'audit-detail.json.gz'").replace("P/'audit.json'","POST/'audit.json'")
s=s.replace("print(json.dumps({k:v for k,v in a.items() if k not in ['runs','detail']},ensure_ascii=False,indent=2))","print('Persisted source/wire audit',a['source_checks'],a['nested_view_checks'],a['wire_request_matches'])")
sys.argv=[sys.argv[0],'gold-369'];exec(compile(s,'interrupted-source-audit','exec'),{'__name__':'__main__','INTERRUPTION':r,'POST':POST})
# Actual SQL timing derives from durable log pairs; full statement array was in memory.
pending={};groups=collections.defaultdict(lambda:{'started':0,'acknowledged':0,'seconds':0.0});errors=[]
for line in (O/'live-gold-369.log').read_text().splitlines():
 try:x=json.loads(line)
 except ValueError:continue
 if x.get('event')!='oracle.sql':continue
 key=(x['binding'],x['call']);stamp=datetime.datetime.fromisoformat(x['ts']).timestamp()
 if x['status']=='STARTED':h=x['sql_sha256'];pending[key]=(stamp,h);groups[h]['started']+=1
 elif key in pending:
  begin,h=pending.pop(key);groups[h]['seconds']+=stamp-begin
  if x['status']=='ACKNOWLEDGED':groups[h]['acknowledged']+=1
  else:errors.append(x)
sql={'source':'persisted oracle.sql events only','log_started':sum(g['started'] for g in groups.values()),'log_acknowledged':sum(g['acknowledged'] for g in groups.values()),'SQL_boundary_seconds':sum(g['seconds'] for g in groups.values()),'unclosed_log_calls':len(pending),'errors':errors,'top_shapes':sorted([{'sql_sha256':h,**g} for h,g in groups.items()],key=lambda x:x['seconds'],reverse=True),'metadata_preflight_selects':1,'full_SQL_statement_array_preserved':False,'Oracle_CPU_only':False,'new_SQL':0};write_summary(POST/'sql-audit.json',sql)
s=(R/'06_TOOLS/EXPERIMENTS/adr_1241/post_audit.py').read_text().replace("a=read(P/'audit.json');result=read(P/'result.json')","a=read(POST/'audit.json');result=INTERRUPTION")
s=s.replace("vector_sql=sum('VECTOR_DISTANCE(' in s for s in read(P/'sql-statements.json.gz'))","vector_sql=None")
s=s.replace("unknowns=[x['number'] for x in calls if x['status']=='unknown']","unknowns=[x['number'] for x in calls if x['status'] in ('unknown','started')]")
s=s.replace("P/'post-audit-detail.json.gz'","POST/'post-audit-detail.json.gz'").replace("P/'post-audit.json'","POST/'post-audit.json'")
s=s.replace("print(json.dumps({k:v for k,v in summary.items() if k not in ('rejection_events','detail','model_attempts','ontology_acquisitions')},ensure_ascii=False,indent=2))","print('Post-stop stage audit',summary['final_model_inputs'],summary['unknown'])")
exec(compile(s,'interrupted-stage-audit','exec'),{'__name__':'__main__','INTERRUPTION':r,'POST':POST})
s=(R/'06_TOOLS/EXPERIMENTS/adr_1241/ontology_audit.py').read_text().replace("a=read(P/'audit.json');r=read(P/'result.json')","a=read(POST/'audit.json');r={**INTERRUPTION,'sql_calls':LOG_SQL}")
s=s.replace("print(json.dumps(result,ensure_ascii=False,indent=2))","print('Ontology E2E incomplete',result['gates'])")
exec(compile(s,'interrupted-ontology-audit','exec'),{'__name__':'__main__','INTERRUPTION':r,'POST':POST,'LOG_SQL':sql['log_started']})
print('No model/SQL dispatch; original partial checkpoints preserved')
