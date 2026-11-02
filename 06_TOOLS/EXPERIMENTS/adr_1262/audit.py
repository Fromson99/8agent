"""Fresh-process read-only Oracle readback and offline original/wire checks. No model calls."""
from pathlib import Path
import json,gzip,hashlib,sys,os,importlib.util,time,sqlite3,collections,statistics
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1262-main130-progress-dedup-live';D=A/'artifacts/design';O=A/'artifacts/run-001';P=O/'live/gold-369'
def read(p):
 with (gzip.open(p,'rt') if str(p).endswith('.gz') else p.open()) as f:return json.load(f)
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary as put,write_raw_json
b=read(D/'before.json')['binding'];C=R/b['engine_root'];sys.path.insert(0,str(C/'02_BACKEND'))
# This is an audit-only process after the inference process exits.
os.environ.update(DP='oracle',GENOS_RUNTIME_DIR='/__oracle_agent__/runtime/adr1262',GENOS_ORACLE_AGENT_NAMESPACE=read(P/'record-binding.json')['namespace'])
for key in ('GENOS_STATE_DIR','GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR','GENOS_SYSTEM_LOG_DIR'):os.environ.pop(key,None)
sp=importlib.util.spec_from_file_location('local_record_transport',R/'06_TOOLS/EXPERIMENTS/adr_1244/test_records.py');local=importlib.util.module_from_spec(sp);sp.loader.exec_module(local)
sp=importlib.util.spec_from_file_location('local_admin',R/'06_TOOLS/maintenance/agent_record_oracle_r2.py');admin=importlib.util.module_from_spec(sp);sp.loader.exec_module(admin)
from semantic_runtime import oracle_runtime_paths as paths,runtime_sqlite,detailed_log_storage as details
from semantic_runtime.oracle_agent_records import AgentRecords,RecordSQL
from semantic_runtime.contracts import digest
conn=admin.connection();client=local.LocalOracle(conn);sql=RecordSQL(client,binding='adr1262-readonly-audit',deadline=time.monotonic()+900,max_calls=10000);records=AgentRecords(sql,namespace=read(P/'record-binding.json')['namespace'])
paths.configure(lambda:records);root=paths.Path(os.environ['GENOS_RUNTIME_DIR'])
original=sqlite3.connect((R/b['data_path']/'store.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True);original.execute('PRAGMA cache_size=-4096')
scope=set(read(D/'cases.json')[0]['request']['json']['document_ids']);a={'scope':records.scope,'fresh_process':True,'oracle_tables':{},'journals':[],'attempts':[],'source_checks':0,'nested_checks':0,'flat_checks':0,'source_mismatches':[],'acl_violations':[],'raw_response_leaks':[],'wire_source_checks':0,'wire_comparison':'Independent original text and scope checks on archived actual wire; full pre-wire request equality not asserted because product raw prompts are intentionally absent without NFS','model_view_count':0,'structured_proposals':0,'publications':[],'events':[],'data_store_sqlite_used_only_offline':True,'physical_runtime_exists':Path(str(root)).exists()}
for table in ('LGL_AGT_RUN_A','LGL_AGT_REC_A','LGL_AGT_BODY_A','LGL_EXEC_ST_A'):
 with conn.cursor() as cursor:
  cursor.execute('SELECT COUNT(*) FROM SIDDA.'+table+' WHERE SCOPE_HASH_VAL=:scope',scope=records.scope);a['oracle_tables'][table]=cursor.fetchone()[0]
def verify(did,s,where):
 if not isinstance(s,dict) or not all(k in s for k in ('block_id','start_cp','end_cp','text')):return
 row=original.execute('SELECT text FROM source_block WHERE document_id=? AND block_id=?',(did,str(s['block_id']))).fetchone()
 if not row or row[0][s['start_cp']:s['end_cp']]!=s['text']:a['source_mismatches'].append({'where':where,'document_id':did,'block_id':s['block_id']})
 if did not in scope:a['acl_violations'].append({'where':where,'document_id':did})
def walk(v):
 if isinstance(v,dict):
  if v.get('document_id') and isinstance(v.get('spans'),list):
   for s in v['spans']:
    if isinstance(s,dict) and all(k in s for k in ('text','block_id','start_cp','end_cp')):verify(v['document_id'],s,'view');a['nested_checks']+=1
  for child in v.values():walk(child)
 elif isinstance(v,list):
  for child in v:walk(child)
raw_requests=[read(p) for p in sorted((P/'raw').glob('*/request.json.gz'))]
for p in (P/'canonical').glob('*.json.gz'):
 if '-output' not in p.name:walk(read(p).get('view',{}))
with paths.using(records):
 for jp in root.rglob('*.sqlite'):
  from semantic_runtime.legal_agent import journal_storage
  db=journal_storage.connect(jp.as_uri()+'?mode=ro',uri=True,isolation_level=None)
  tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")};j={'path':str(jp),'tables':sorted(tables)}
  if 'run' in tables:
   try:j['runs']=[dict(x) for x in db.execute('SELECT * FROM run')]
   except sqlite3.DatabaseError:pass
  if 'budget' in tables:j['budget']=[dict(x) for x in db.execute('SELECT * FROM budget')]
  if {'evidence_unit','evidence_span'}<=tables:
   for row in db.execute('SELECT u.document_id,u.source_id,s.block_id,s.start_cp,s.end_cp,s.text FROM evidence_unit u JOIN evidence_span s ON s.evidence_id=u.evidence_id'):
    v=dict(row);verify(v['document_id'],v,'acquired');a['source_checks']+=1
  if 'model_attempt' in tables:
   for row in db.execute('SELECT * FROM model_attempt ORDER BY created_seq'):
    v=dict(row);request=json.loads(v['request_json']);response=json.loads(v['response_json']) if v.get('response_json') else None;receipt=json.loads(v['receipt_json']) if v.get('receipt_json') else {}
    out={'attempt_id':v['attempt_id'],'status':v['status'],'request_is_diagnostic_reference':details.is_reference(request),'capture_status':request.get('capture_status'),'response_present':response is not None,'receipt_response_storage':receipt.get('response_storage'),'diagnostic_response':receipt.get('diagnostic_response')}
    if response is not None:
     # These are transport-only envelope fields, rather than keys inside legal structured JSON content.
     for key in ('stream_events','raw_body','reasoning','reasoning_content','debug'):
      if key in response:a['raw_response_leaks'].append({'attempt_id':v['attempt_id'],'field':key})
     for choice in response.get('body_json',{}).get('choices',[]):
      message=choice.get('message',{})
      for key in ('reasoning','reasoning_content','reasoning_details'):
       if key in message:a['raw_response_leaks'].append({'attempt_id':v['attempt_id'],'field':key})
      try:
       value=json.loads(message.get('content','null'))
       if isinstance(value,(dict,list)):a['structured_proposals']+=1
      except (ValueError,TypeError):pass
    a['attempts'].append(out)
  if 'model_view' in tables:
   for row in db.execute('SELECT * FROM model_view'):
    v=dict(row);a['model_view_count']+=1
  if 'publication' in tables:a['publications'] += [dict(x) for x in db.execute('SELECT * FROM publication')]
  if 'event' in tables and {'seq','kind','payload_json'}<={r[1] for r in db.execute('PRAGMA table_info(event)')}:
   for row in db.execute('SELECT seq,kind,payload_json FROM event ORDER BY seq'):
    if any(t in row['kind'] for t in ('FAILED','REJECT','UNKNOWN','SUPERVISOR','PROVIDER','ONTOLOGY','SOURCE_GOAL')):a['events'].append({'seq':row['seq'],'kind':row['kind'],'payload':json.loads(row['payload_json'])})
  if 'case_commit' in tables:j['case_commits']=[dict(x) for x in db.execute('SELECT * FROM case_commit')]
  a['journals'].append(j);db.close()
# Exact canonical-to-wire checks use the archived transport requests, not product NFS.
wire_before=a['nested_checks']
for wire in raw_requests:
 for message in wire.get('messages',[]):
  if message.get('role')=='user':
   try:walk(json.loads(message['content']))
   except (ValueError,TypeError):pass
a['wire_source_checks']=a['nested_checks']-wire_before
# Preserve source text once in original journals; audit records carry coordinates/hashes only.

calls=read(P/'calls.json') if (P/'calls.json').exists() else []
a['physical_model_calls']=len(calls);a['complete_responses']=sum(x['status']=='responded' for x in calls);a['unknown_outcomes']=sum(x['status'] in ('unknown','started') for x in calls)
a['post_unknown_calls']=sum(len(calls)-i-1 for i,x in enumerate(calls) if x['status'] in ('unknown','started'))
a['reported_cost_usd']=sum((x.get('usage') or {}).get('cost',0) or 0 for x in calls);a['reported_input_tokens']=sum((x.get('usage') or {}).get('prompt_tokens',0) or 0 for x in calls);a['reported_output_tokens']=sum((x.get('usage') or {}).get('completion_tokens',0) or 0 for x in calls)
a['physical_budget_reserved']=sum(row.get('model_reserved',0) for j in a['journals'] for row in j.get('budget',[]));a['physical_budget_matches']=a['physical_budget_reserved']==len(calls)
a['model_seconds']=sum(x.get('seconds',0) for x in calls);a['missing_usage_calls']=sum(not bool(x.get('usage')) for x in calls)
samples=[json.loads(x) for x in (P/'resource-samples.jsonl').read_text().splitlines()] if (P/'resource-samples.jsonl').exists() else []
a['resources']={'samples':len(samples),'max_host_swap_growth_MiB':max((x['host_swap_growth']/1024**2 for x in samples),default=None),'max_RSS_GiB':max((x['VmRSS']/1024**3 for x in samples),default=None),'min_available_GiB':min((x['MemAvailable']/1024**3 for x in samples),default=None),'resource_stop':read(P/'resource-stop.json') if (P/'resource-stop.json').exists() else None}
response=read(P/'response.json') if (P/'response.json').exists() else {};answer=(response.get('body') or {}).get('answer') or {};a['http_status']=response.get('http_status');a['answer_present']=bool(answer.get('text','').strip()) if isinstance(answer,dict) else False;a['answer_chars']=len(answer.get('text','')) if isinstance(answer,dict) else 0
f=read(D/'freeze.json');a['frozen_files']=len(f['files']);a['changed_frozen_files']=[p for p,h in f['files'].items() if sha(R/p)!=h];a['provider_counts']=dict(collections.Counter('/'.join(x.get('provider',{}).get('only',[])) for x in calls));a['finish_reasons']=dict(collections.Counter(ch.get('finish_reason') for p in (P/'raw').glob('*/response.json.gz') for ch in read(p).get('choices',[])));a['sql_errors']=client.errors;a['audit_sql_calls']=sql.calls
original.close();conn.close();put(O/'audit-decoded.json',a);print(json.dumps({k:a[k] for k in ('http_status','answer_present','oracle_tables','physical_model_calls','unknown_outcomes','source_checks','source_mismatches','acl_violations','resources','changed_frozen_files')},ensure_ascii=False))
