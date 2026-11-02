"""Explicitly approved BODY heap shrink, exact four-table backup verification, retained270MiB cap."""
from pathlib import Path
import json,sys,hashlib,gzip,time,datetime,os
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1256-oracle-body-space-reclaim';D=A/'artifacts/design';O=A/'artifacts/run-001'
sys.path[:0]=[str(R/'06_TOOLS/maintenance'),str(R/'06_TOOLS/EXPERIMENTS/adr_1254')]
from experiment_json import write_summary as put
import quota_fence as fence
TABLES=('LGL_AGT_RUN_A','LGL_AGT_REC_A','LGL_AGT_BODY_A','LGL_EXEC_ST_A');TARGET='LGL_AGT_BODY_A'
def sha(p):
 with p.open('rb') as z:return hashlib.file_digest(z,'sha256').hexdigest()
authorization=json.loads((D/'explicit-user-approval.json').read_text());assert authorization['answer']=='공간 반환·90% 상한 고정·재실험 승인'
freeze=json.loads((D/'approved-freeze.json').read_text())
for relative,expected in freeze['files'].items():assert sha(R/relative)==expected,'APPROVED_INPUT_CHANGED:'+relative
assert not (O/'result.json').exists(),'Already completed; no repeat'
saved=json.loads((O/'before.json').read_text());archive=R/saved['backup_path'];assert sha(archive)==saved['backup_sha256']
h=hashlib.sha256()
with gzip.open(archive,'rb') as z:
 for block in iter(lambda:z.read(1024**2),b''):h.update(block)
assert h.hexdigest()==saved['values']['uncompressed_sha256']
with gzip.open(archive,'rb') as z:header=json.loads(z.readline())['header']
db=fence.connect();db.call_timeout=60000
def query(sql, **kw):
    with db.cursor() as c:
        c.execute(sql, **kw)
        return [list(r) for r in c.fetchall()]

def metadata():
    v = {}
    for table in TABLES:
        v[table] = {'columns': query("SELECT COLUMN_NAME,DATA_TYPE,DATA_LENGTH,CHAR_LENGTH,NULLABLE FROM DBA_TAB_COLUMNS WHERE OWNER='SIDDA' AND TABLE_NAME=:t ORDER BY COLUMN_ID", t=table), 'constraints': query("SELECT CONSTRAINT_NAME,CONSTRAINT_TYPE,STATUS,VALIDATED FROM DBA_CONSTRAINTS WHERE OWNER='SIDDA' AND TABLE_NAME=:t ORDER BY CONSTRAINT_NAME", t=table), 'indexes': query("SELECT INDEX_NAME,INDEX_TYPE,STATUS FROM DBA_INDEXES WHERE OWNER='SIDDA' AND TABLE_NAME=:t ORDER BY INDEX_NAME", t=table)}
    return v

def leases_clear():
    for row in query('SELECT ST_JSON_CN FROM SIDDA.LGL_EXEC_ST_A'):
        v = row[0].read() if hasattr(row[0], 'read') else row[0]
        v = json.loads(v) if isinstance(v, str) else v
        if isinstance(v, dict) and v.get('token') and (v.get('expires', 0) > time.time()):
            raise RuntimeError('Live Agent lease exists; no maintenance allowed')

def stream(out=None):
    h = hashlib.sha256()
    counts = {}

    def emit(v):
        raw = (json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()
        h.update(raw)
        if out:
            out.write(raw)
    emit({'header': header})
    for table in TABLES:
        conf = header['tables'][table]
        projections = ['TO_CHAR(' + n + ',\'YYYY-MM-DD"T"HH24:MI:SS.FF6 TZH:TZM\')' if typ.startswith('TIMESTAMP') else n for n, typ, *_ in conf['columns']]
        counts[table] = 0
        with db.cursor() as c:
            c.arraysize = 100
            c.execute('SELECT ' + ','.join(projections) + ' FROM SIDDA.' + table + ' ORDER BY ' + ','.join(conf['primary_key']))
            for row in c:
                vals = [v.read() if hasattr(v, 'read') else v for v in row]
                emit({'table': table, 'row': vals})
                counts[table] += 1
    return {'uncompressed_sha256': h.hexdigest(), 'counts': counts}

before=fence.inspect(db);assert before['quota_bytes']==fence.ORIGINAL and not before['unlimited_tablespace_grant_count']
meta=metadata();assert meta==saved['metadata']
assert all(i[1] in ('NORMAL','LOB') for i in meta[TARGET]['indexes'])
assert query("SELECT COUNT(*) FROM DBA_TRIGGERS WHERE TABLE_OWNER='SIDDA' AND TABLE_NAME='LGL_AGT_BODY_A'")[0][0]==0
assert query("SELECT ROW_MOVEMENT,IOT_TYPE,PARTITIONED FROM DBA_TABLES WHERE OWNER='SIDDA' AND TABLE_NAME='LGL_AGT_BODY_A'")[0]==['DISABLED',None,'NO']
assert query("SELECT SEGMENT_SPACE_MANAGEMENT FROM DBA_TABLESPACES WHERE TABLESPACE_NAME='USERS'")[0][0]=='AUTO'
assert query("SELECT COUNT(*) FROM DBA_MVIEW_DETAIL_RELATIONS WHERE DETAILOBJ_OWNER='SIDDA' AND DETAILOBJ_NAME='LGL_AGT_BODY_A'")[0][0]==0
leases_clear()
with db.cursor() as c:c.execute('LOCK TABLE SIDDA.LGL_AGT_BODY_A IN EXCLUSIVE MODE NOWAIT')
values_before=stream();assert values_before==saved['values'],'Current rows differ from backup; no DDL'
db.commit();leases_clear();put(O/'approved-preflight.json',{'values_match_verified_backup':True,'metadata_equal':True,'capacity':before,'backup_sha256':saved['backup_sha256'],'new_models':0})
# These are exactly the four reviewed and explicitly authorized statements.
statements=['ALTER USER SIDDA QUOTA 270M ON USERS','ALTER TABLE SIDDA.LGL_AGT_BODY_A ENABLE ROW MOVEMENT','ALTER TABLE SIDDA.LGL_AGT_BODY_A SHRINK SPACE','ALTER TABLE SIDDA.LGL_AGT_BODY_A DISABLE ROW MOVEMENT']
row_enabled=False;events=[]
try:
 for statement in statements:
  with db.cursor() as c:c.execute(statement)
  if statement.endswith(' ENABLE ROW MOVEMENT'):row_enabled=True
  if statement.endswith(' DISABLE ROW MOVEMENT'):row_enabled=False
  current=fence.inspect(db);events.append({'statement':statement,'capacity':current});put(O/('approved-ddl-'+str(len(events))+'.json'),events[-1]);assert current['quota_bytes']==fence.CAP
  if len(events)<=2:assert current['used_bytes']<=before['used_bytes'],'Allocation unexpectedly grew during initial quota fencing'
  else:assert current['used_bytes']<=fence.CAP,'Post-reclaim allocation above90percent'
 after=fence.inspect(db);values_after=stream();meta_after=metadata();assert values_after==values_before and meta_after==meta
 assert query("SELECT ROW_MOVEMENT FROM DBA_TABLES WHERE OWNER='SIDDA' AND TABLE_NAME='LGL_AGT_BODY_A'")[0][0]=='DISABLED'
 assert after['used_bytes']<before['used_bytes'] and after['used_bytes']<=fence.CAP
 put(O/'result.json',{'status':'complete','strict_success':True,'before_capacity':before,'after_capacity':after,'freed_bytes':before['used_bytes']-after['used_bytes'],'all_four_table_values_before':values_before,'all_four_table_values_after':values_after,'metadata_equal':True,'row_movement_restored':True,'table_ddl_count':3,'quota_alter_count':1,'quota_retained_270MiB':True,'row_deletes':0,'lob_index_gold_ddl':0,'new_models':0,'backup_sha256':saved['backup_sha256'],'authorization':authorization,'already_over90_before_action':before['used_bytes']>fence.CAP})
 print('Reclaimed',before['used_bytes']-after['used_bytes'],'bytes; four-table values identical;270MiB hard quota retained',flush=True)
finally:
 if row_enabled:
  with db.cursor() as c:c.execute('ALTER TABLE SIDDA.LGL_AGT_BODY_A DISABLE ROW MOVEMENT')
  put(O/'row-movement-restored-after-error.json',{'restored':True})
 put(O/'retained-quota.json',fence.inspect(db));db.close()
