"""READ-ONLY export/verification and reviewable cleanup plan. Executes no DELETE/DDL."""
from pathlib import Path
import sys,json,hashlib,gzip,os,importlib.util,collections,sqlite3
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1252-main129-pinned-oracle-live';O=A/'artifacts/run-001';B=R/'09_ARTIFACTS/AUDITS/20261030-main129-pinned-oracle-live/space-recovery';B.mkdir(parents=True,exist_ok=True,mode=0o700)
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
scope=json.loads((R/'04_EXPERIMENTS/ADR/ADR-1245-main128-oracle-records-live/artifacts/run-001/live/gold-369/record-binding.json').read_text())['scope']
columns={
 'LGL_AGT_RUN_A':['SCOPE_HASH_VAL','RUN_KEY_HASH_VAL','SESS_KEY_HASH_VAL','REQ_KEY_HASH_VAL','PRNT_RUN_KEY_HASH_VAL','ST_CD','STRT_DTTM','CHG_DTTM','BODY_HASH_VAL'],
 'LGL_AGT_REC_A':['SCOPE_HASH_VAL','OWNER_KEY_HASH_VAL','REC_KIND_CD','REC_KEY_HASH_VAL','REC_REV_NO','ORD_SEQ_NO','LOOKUP_HASH_VAL','BODY_HASH_VAL'],
 'LGL_AGT_BODY_A':['SCOPE_HASH_VAL','BODY_HASH_VAL','PART_SEQ_NO','PART_JSON_CN'],
 'LGL_EXEC_ST_A':['SCOPE_HASH_VAL','ST_KEY_ID','CHG_SEQ_NO','ST_HASH_VAL','ST_JSON_CN']}
keys={'LGL_AGT_RUN_A':[0,1],'LGL_AGT_REC_A':[0,1,2,3,4],'LGL_AGT_BODY_A':[0,1,2],'LGL_EXEC_ST_A':[0,1]}
sp=importlib.util.spec_from_file_location('readonly_export_admin',R/'06_TOOLS/maintenance/agent_record_oracle_r2.py');a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a);db=a.connection();db.rollback();archive=B/'ADR1245_original_scope.jsonl.gz';counts=collections.Counter();rawhash=hashlib.sha256();rawbytes=0
with db.cursor() as c:
 c.execute('SET TRANSACTION READ ONLY')
 c.execute('SELECT CURRENT_SCN FROM V$DATABASE');scn=c.fetchone()[0]
header={'schema_version':'oracle-agent-scope-backup-v1','owner':'SIDDA','scope':scope,'namespace':'adr1245-main128-live','original_adr':1245,'snapshot_scn':scn,'columns':columns,'timestamp_columns':{'LGL_AGT_RUN_A':['STRT_DTTM','CHG_DTTM']},'primary_keys':keys}
fd=os.open(archive,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'wb') as underlying:
 with gzip.GzipFile(fileobj=underlying,mode='wb',mtime=0,filename='',compresslevel=6) as z:
  def put(value):
   global rawbytes
   data=(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode();rawhash.update(data);rawbytes+=len(data);z.write(data)
  put({'header':header})
  for table,cols in columns.items():
   projection=[]
   for name in cols:
    projection.append('TO_CHAR('+name+',\'YYYY-MM-DD"T"HH24:MI:SS.FF6 TZH:TZM\') AS '+name if name in ('STRT_DTTM','CHG_DTTM') else name)
   with db.cursor() as c:
    c.arraysize=250;c.execute('SELECT '+','.join(projection)+' FROM SIDDA.'+table+' WHERE SCOPE_HASH_VAL=:scope ORDER BY '+','.join(cols[i] for i in keys[table]),scope=scope)
    for row in c:
     cells=[v.read() if hasattr(v,'read') else v for v in row];assert cells[0]==scope;put({'table':table,'row':cells});counts[table]+=1
 underlying.flush();os.fsync(underlying.fileno())
db.rollback();db.close()
assert dict(counts)=={'LGL_AGT_RUN_A':1,'LGL_AGT_REC_A':2987,'LGL_AGT_BODY_A':52742,'LGL_EXEC_ST_A':52}
# Read the entire archive again. Check PK uniqueness and every immutable body digest.
seen={t:set() for t in columns};rehash=hashlib.sha256();recounts=collections.Counter();parts={};refs=set();runstates=[]
with gzip.open(archive,'rb') as z:
 for n,line in enumerate(z):
  rehash.update(line);v=json.loads(line)
  if n==0:assert v['header']==header;continue
  t=v['table'];row=v['row'];key=tuple(row[i] for i in keys[t]);assert key not in seen[t];seen[t].add(key);assert len(row)==len(columns[t]) and row[0]==scope;recounts[t]+=1
  if t=='LGL_AGT_BODY_A':parts.setdefault(row[1],{})[row[2]]=json.loads(row[3])
  elif t=='LGL_AGT_REC_A':refs.add(row[7])
  elif t=='LGL_AGT_RUN_A':refs.add(row[8]);runstates.append(row[5])
assert rawhash.hexdigest()==rehash.hexdigest() and recounts==counts and runstates==['FAILED']
binding=json.loads((A/'artifacts/design/before.json').read_text())['binding'];sys.path.insert(0,str(R/binding['engine_root']/'02_BACKEND'))
from semantic_runtime.oracle_agent_records import AgentRecords
for h,p in parts.items():assert hashlib.sha256(AgentRecords._decode_body(h,p)).hexdigest()==h
assert refs<=parts.keys()
with archive.open('rb') as stream:packedhash=hashlib.file_digest(stream,'sha256').hexdigest()
receipt={'archive_path':str(archive.relative_to(R)),'archive_sha256':packedhash,'archive_bytes':archive.stat().st_size,'uncompressed_sha256':rawhash.hexdigest(),'uncompressed_bytes':rawbytes,'counts':dict(counts),'unique_bodies_fully_decoded_and_hash_verified':len(parts),'pk_unique':True,'all_record_and_run_body_refs_present':True,'namespace':header['namespace'],'scope':scope,'original_run_status':'FAILED','database_read_only':True,'database_rows_deleted':0,'actual_Oracle_restore_tested':False,'restore_verification':'All physical row values/PKs, CLOB strings, timestamp-offset strings and all2175 body content hashes verified from gzip; actual reinsert not executed due current capacity.'}
write_summary(B/'backup-verification.json',receipt)
# This is a plan, not an executable auto-cleanup: human approval is required.
text='-- REVIEW ONLY. DO NOT EXECUTE WITHOUT EXPLICIT USER APPROVAL.\n-- Archive verified: '+receipt['archive_path']+'\n-- SHA256: '+packedhash+'\n-- Only ADR1245 failed experiment namespace; no production/other-scope rows.\n'
for table in ('LGL_AGT_REC_A','LGL_AGT_RUN_A','LGL_EXEC_ST_A','LGL_AGT_BODY_A'):text+='DELETE FROM SIDDA.'+table+" WHERE SCOPE_HASH_VAL = '"+scope+"';\n"
text+='-- Compare deleted counts REC2987/RUN1/STATE52/BODY52742 before COMMIT; otherwise ROLLBACK.\n-- Do not assume DELETE reduces allocated segment bytes; free-block reuse/reclamation must be verified.\n-- Separate space-reclamation DDL requires a reviewed operation before execution.\n'
(B/'정리대상_검토용.sql').write_text(text)
write_summary(B/'proposed-plan.json',{'requires_explicit_user_approval':True,'archive':receipt,'target_only':'ADR1245 failed public-question experiment scope','delete_expected_counts':dict(counts),'preserve_all_other_scopes_and_Gold':True,'no_cleanup_executed':True,'allocated_bytes_reclaimed_not_guaranteed_by_delete':'Oracle DELETE frees reusable blocks but does not necessarily lower DBA_SEGMENTS; assess reusing freed blocks under hard quota or separately approved shrink/reclamation','blocker':'Current allocated89.604%; final answer not reached. Cannot arbitrarily delete original failed records under AGENTS.md.'})
print(json.dumps(receipt,ensure_ascii=False))
