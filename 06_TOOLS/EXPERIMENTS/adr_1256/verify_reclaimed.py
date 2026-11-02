from pathlib import Path
import json,sys,hashlib,gzip,time
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1256-oracle-body-space-reclaim';O=A/'artifacts/run-001'
sys.path[:0]=[str(R/'06_TOOLS/maintenance'),str(R/'06_TOOLS/EXPERIMENTS/adr_1254')]
from experiment_json import write_summary as put
import quota_fence as fence
TABLES=('LGL_AGT_RUN_A','LGL_AGT_REC_A','LGL_AGT_BODY_A','LGL_EXEC_ST_A');TARGET='LGL_AGT_BODY_A'
saved=json.loads((O/'before.json').read_text());archive=R/saved['backup_path']
with archive.open('rb') as z:assert hashlib.file_digest(z,'sha256').hexdigest()==saved['backup_sha256']
with gzip.open(archive,'rb') as z:header=json.loads(z.readline())['header']
db=fence.connect()
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
current=fence.inspect(db);meta=metadata();values=stream();movement=query("SELECT ROW_MOVEMENT FROM DBA_TABLES WHERE OWNER='SIDDA' AND TABLE_NAME='LGL_AGT_BODY_A'")[0][0]
checks={'quota_fixed270MiB':current['quota_bytes']==fence.CAP,'allocation_under90percent_of_original300MiB':current['used_bytes']<=fence.CAP,'metadata_equal':meta==saved['metadata'],'all_four_table_values_equal':values==saved['values'],'rowmovement_disabled':movement=='DISABLED','usage_lower':current['used_bytes']<saved['capacity']['used_bytes']}
put(O/'observed-state-mismatch.json',{'checks':checks,'values_before':saved['values'],'values_after':values,'capacity':current})
assert all(checks.values()),checks
out={'status':'ALREADY_RECLAIMED_OBSERVED','strict_success':True,'checks':checks,'before_capacity':saved['capacity'],'after_capacity':current,'freed_bytes':saved['capacity']['used_bytes']-current['used_bytes'],'all_four_table_values_before':saved['values'],'all_four_table_values_after':values,'backup_sha256':saved['backup_sha256'],'table_ddl_by_this_apply_attempt':0,'quota_changes_by_this_apply_attempt':0,'row_deletes_by_this_apply_attempt':0,'new_models':0,'attribution':'At first approved apply precondition, quota already270MiB and BODY heap already4.75MiB; our apply rejected before DDL. Executor/time of external change not established. Do not claim this process performed SHRINK. Read-only verified approved target state and exact full backup equality.'}
put(O/'result.json',out);db.close();print(json.dumps({'checks':checks,'freed_MiB':out['freed_bytes']/1024**2,'used_percent':current['used_percent_of_original']}))
