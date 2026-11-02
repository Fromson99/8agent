from pathlib import Path
import json,sys,hashlib,gzip
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1256-oracle-body-space-reclaim';O=A/'artifacts/run-001';D=A/'artifacts/design'
sys.path[:0]=[str(R/'06_TOOLS/maintenance'),str(R/'06_TOOLS/EXPERIMENTS/adr_1254')]
from experiment_json import write_summary as put
import quota_fence as fence
TABLES=('LGL_AGT_RUN_A','LGL_AGT_REC_A','LGL_AGT_BODY_A','LGL_EXEC_ST_A');TARGET='LGL_AGT_BODY_A'
saved=json.loads((O/'before.json').read_text());archive=R/saved['backup_path']
def file_sha(p):
 with p.open('rb') as z:return hashlib.file_digest(z,'sha256').hexdigest()
assert file_sha(archive)==saved['backup_sha256']
canonical=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
index={};header=None;header_indices={};old_counts={}
with gzip.open(archive,'rt') as z:
 header=json.loads(z.readline())['header']
 for t,v in header['tables'].items():header_indices[t]=[list(x[0] for x in v['columns']).index(k) for k in v['primary_key']]
 for line in z:
  v=json.loads(line);t=v['table'];row=v['row'];key=(t,canonical([row[i] for i in header_indices[t]]));assert key not in index;index[key]=hashlib.sha256(canonical(row).encode()).hexdigest();old_counts[t]=old_counts.get(t,0)+1
recovery=R/'04_EXPERIMENTS/ADR/ADR-1257-wiki-oracle-space-recovery/artifacts/run-001/result.json';rec=json.loads(recovery.read_text());assert rec['all_four_table_values_before']==saved['values'] and rec['all_four_table_values_after']==saved['values']
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
current=fence.inspect(db);meta=metadata();checked={};added={};mismatches=[];seen=set()
for table in TABLES:
 conf=header['tables'][table];projections=["TO_CHAR("+n+",'YYYY-MM-DD\"T\"HH24:MI:SS.FF6 TZH:TZM')" if typ.startswith('TIMESTAMP') else n for n,typ,*_ in conf['columns']]
 with db.cursor() as c:
  c.arraysize=100;c.execute('SELECT '+','.join(projections)+' FROM SIDDA.'+table+' ORDER BY '+','.join(conf['primary_key']))
  for row in c:
   row=[v.read() if hasattr(v,'read') else v for v in row];key=(table,canonical([row[i] for i in header_indices[table]]));value_hash=hashlib.sha256(canonical(row).encode()).hexdigest()
   if key in index:
    seen.add(key);checked[table]=checked.get(table,0)+1
    if index[key]!=value_hash:mismatches.append({'table':table,'pk_hash':hashlib.sha256(key[1].encode()).hexdigest()})
   else:added[table]=added.get(table,0)+1
missing=len(set(index)-seen);movement=query("SELECT ROW_MOVEMENT FROM DBA_TABLES WHERE OWNER='SIDDA' AND TABLE_NAME='LGL_AGT_BODY_A'")[0][0]
checks={'backup_original_rows_all_present_and_identical':missing==0 and not mismatches,'metadata_equal':meta==saved['metadata'],'quota_fixed270MiB':current['quota_bytes']==fence.CAP,'under_original90percent':current['used_bytes']<=fence.CAP,'rowmovement_disabled':movement=='DISABLED','actual_1257_before_after_full_hash_matches_our_backup':True}
assert all(checks.values()),checks
put(O/'result.json',{'status':'ADOPT_VERIFIED_COMPLETED_RECLAMATION_1257','strict_success':True,'checks':checks,'before_capacity':saved['capacity'],'after_capacity':current,'freed_at_reclamation_bytes':rec['freed_bytes'],'original_full_values_hash':saved['values']['uncompressed_sha256'],'original_counts_verified':checked,'subsequent_additional_rows':added,'missing_original_rows':missing,'changed_original_rows':mismatches,'new_models_by_this_audit':0,'table_quota_ddl_by_this_audit':0,'additional_row_deletes':0,'completed_reclamation_result':str(recovery.relative_to(R)),'completed_reclamation_sha256':file_sha(recovery),'scope':'Read-only adoption of exact approved physical target already completed by parallel ADR1257; no repeated SHRINK. New appended rows explain full-stream difference after that receipt.'});db.close();print(json.dumps({'checks':checks,'extra':added,'current_percent':current['used_percent_of_original']}))
