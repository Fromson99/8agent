"""Reclaim only already-empty heap extents; no data DELETE, no LOB/index cascade."""
from pathlib import Path
import sys,json,hashlib,gzip,datetime,time
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1256-oracle-body-space-reclaim';D=A/'artifacts/design';O=A/'artifacts/run-001';D.mkdir(exist_ok=True);O.mkdir(exist_ok=True)
sys.path[:0]=[str(R/'06_TOOLS/maintenance'),str(R/'06_TOOLS/EXPERIMENTS/adr_1254')]
from experiment_json import write_summary as put
import quota_fence as fence
TABLES=('LGL_AGT_RUN_A','LGL_AGT_REC_A','LGL_AGT_BODY_A','LGL_EXEC_ST_A');TARGET='LGL_AGT_BODY_A'
criteria={'action':'Physical reclamation of already empty BODY heap extents after approved ADR1253 cleanup; no additional row deletion','success':['All four Agent table values, counts and PK-sorted full-stream SHA identical before/after','All columns/types/constraints/index status preserved; rowmovement original DISABLED restored','Allocated schema usage decreases, never above original90percent under270MiB server cap','Original300MiB quota restored; no other table/Gold/LOB/index DDL'],'plan':['ALTER TABLE SIDDA.LGL_AGT_BODY_A ENABLE ROW MOVEMENT','ALTER TABLE SIDDA.LGL_AGT_BODY_A SHRINK SPACE','ALTER TABLE SIDDA.LGL_AGT_BODY_A DISABLE ROW MOVEMENT'],'no_cascade':True,'no_delete':True,'new_models':0,'docs':'https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html','doc_scope':'ASSM heap SHRINK releases empty allocation; no SecureFiles LOB shrink, no CASCADE'}
put(D/'criteria.json',criteria);db=fence.connect();before=fence.inspect(db);assert before['quota_bytes']==fence.ORIGINAL and before['used_bytes']<=fence.CAP

def query(sql,**kw):
 with db.cursor() as c:c.execute(sql,**kw);return [list(r) for r in c.fetchall()]
def metadata():
 v={}
 for table in TABLES:
  v[table]={'columns':query('SELECT COLUMN_NAME,DATA_TYPE,DATA_LENGTH,CHAR_LENGTH,NULLABLE FROM DBA_TAB_COLUMNS WHERE OWNER=\'SIDDA\' AND TABLE_NAME=:t ORDER BY COLUMN_ID',t=table),'constraints':query('SELECT CONSTRAINT_NAME,CONSTRAINT_TYPE,STATUS,VALIDATED FROM DBA_CONSTRAINTS WHERE OWNER=\'SIDDA\' AND TABLE_NAME=:t ORDER BY CONSTRAINT_NAME',t=table),'indexes':query('SELECT INDEX_NAME,INDEX_TYPE,STATUS FROM DBA_INDEXES WHERE OWNER=\'SIDDA\' AND TABLE_NAME=:t ORDER BY INDEX_NAME',t=table)}
 return v
meta=metadata();assert all(i[1]=='NORMAL' and i[2]=='VALID' for i in meta[TARGET]['indexes']);assert query("SELECT COUNT(*) FROM DBA_TRIGGERS WHERE TABLE_OWNER='SIDDA' AND TABLE_NAME='LGL_AGT_BODY_A'")[0][0]==0
assert query("SELECT ROW_MOVEMENT,IOT_TYPE,PARTITIONED FROM DBA_TABLES WHERE OWNER='SIDDA' AND TABLE_NAME='LGL_AGT_BODY_A'")[0]==['DISABLED',None,'NO']
assert query("SELECT SEGMENT_SPACE_MANAGEMENT FROM DBA_TABLESPACES WHERE TABLESPACE_NAME='USERS'")[0][0]=='AUTO'
assert query("SELECT COUNT(*) FROM DBA_MVIEW_DETAIL_RELATIONS WHERE DETAILOBJ_OWNER='SIDDA' AND DETAILOBJ_NAME='LGL_AGT_BODY_A'")[0][0]==0

def leases_clear():
 for row in query('SELECT ST_JSON_CN FROM SIDDA.LGL_EXEC_ST_A'):
  v=row[0].read() if hasattr(row[0],'read') else row[0];v=json.loads(v) if isinstance(v,str) else v
  if isinstance(v,dict) and v.get('token') and v.get('expires',0)>time.time():raise RuntimeError('Live Agent lease exists; no maintenance allowed')
leases_clear()
header={'tables':{},'serialization':'JSONL sorted PK, TZ TO_CHAR, CLOB read verbatim, nativeJSON values canonicalized'}
for table in TABLES:
 cols=meta[table]['columns'];pk=query("SELECT cc.COLUMN_NAME FROM DBA_CONSTRAINTS c JOIN DBA_CONS_COLUMNS cc ON cc.OWNER=c.OWNER AND cc.CONSTRAINT_NAME=c.CONSTRAINT_NAME WHERE c.OWNER='SIDDA' AND c.TABLE_NAME=:t AND c.CONSTRAINT_TYPE='P' ORDER BY cc.POSITION",t=table);header['tables'][table]={'columns':cols,'primary_key':[x[0] for x in pk]}
def stream(out=None):
 h=hashlib.sha256();counts={}
 def emit(v):
  raw=(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode();h.update(raw)
  if out:out.write(raw)
 emit({'header':header})
 for table in TABLES:
  conf=header['tables'][table];projections=["TO_CHAR("+n+",'YYYY-MM-DD\"T\"HH24:MI:SS.FF6 TZH:TZM')" if typ.startswith('TIMESTAMP') else n for n,typ,*_ in conf['columns']];counts[table]=0
  with db.cursor() as c:
   c.arraysize=100;c.execute('SELECT '+','.join(projections)+' FROM SIDDA.'+table+' ORDER BY '+','.join(conf['primary_key']))
   for row in c:
    vals=[v.read() if hasattr(v,'read') else v for v in row];emit({'table':table,'row':vals});counts[table]+=1
 return {'uncompressed_sha256':h.hexdigest(),'counts':counts}
with db.cursor() as c:c.execute('LOCK TABLE SIDDA.LGL_AGT_BODY_A IN EXCLUSIVE MODE NOWAIT')
backup=O/'all-agent-values-before.jsonl.gz'
with backup.open('xb') as raw:
 with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0) as z:values_before=stream(z)
compressed_sha=hashlib.file_digest(backup.open('rb'),'sha256').hexdigest();verify=hashlib.sha256()
with gzip.open(backup,'rb') as z:
 while b:=z.read(1024**2):verify.update(b)
assert verify.hexdigest()==values_before['uncompressed_sha256'];db.commit();put(O/'before.json',{'capacity':before,'metadata':meta,'values':values_before,'backup_path':str(backup.relative_to(R)),'backup_sha256':compressed_sha,'compressed_bytes':backup.stat().st_size})
leases_clear();applied=False;row_enabled=False;events=[]
try:
 put(O/'quota-applied.json',fence.alter(db,fence.ORIGINAL,fence.CAP));applied=True
 for statement in criteria['plan']:
  with db.cursor() as c:c.execute(statement)
  row_enabled=statement.endswith('ENABLE ROW MOVEMENT') or(row_enabled and not statement.endswith('DISABLE ROW MOVEMENT'));events.append({'statement':statement,'capacity':fence.inspect(db)});put(O/('ddl-'+str(len(events))+'.json'),events[-1]);assert events[-1]['capacity']['used_bytes']<=fence.CAP
 after=fence.inspect(db);values_after=stream();meta_after=metadata();assert values_after==values_before and meta_after==meta
 assert query("SELECT ROW_MOVEMENT FROM DBA_TABLES WHERE OWNER='SIDDA' AND TABLE_NAME='LGL_AGT_BODY_A'")[0][0]=='DISABLED'
 assert after['used_bytes']<before['used_bytes']
 put(O/'result.json',{'status':'complete','strict_success':True,'before_capacity':before,'after_capacity':after,'freed_bytes':before['used_bytes']-after['used_bytes'],'all_four_table_values_before':values_before,'all_four_table_values_after':values_after,'metadata_equal':True,'row_movement_restored':True,'table_ddl_count':len(events),'row_deletes':0,'lob_index_gold_ddl':0,'new_models':0,'backup_sha256':compressed_sha,'criteria':criteria});print('Reclaimed',before['used_bytes']-after['used_bytes'],'bytes; all four table values unchanged')
finally:
 if row_enabled:
  with db.cursor() as c:c.execute('ALTER TABLE SIDDA.LGL_AGT_BODY_A DISABLE ROW MOVEMENT')
  put(O/'row-movement-restored.json',{'restored':True})
 if applied:put(O/'quota-restored.json',fence.alter(db,fence.CAP,fence.ORIGINAL))
 db.close()
