from pathlib import Path
import json,hashlib,gzip,sys,importlib.util,time,os
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1253-approved-oracle-failure-archive';D=A/'artifacts/design';O=A/'artifacts/run-001';D.mkdir(parents=True,exist_ok=True);O.mkdir(exist_ok=True);B=R/'09_ARTIFACTS/AUDITS/20261030-main129-pinned-oracle-live/space-recovery';receipt=json.loads((B/'backup-verification.json').read_text());archive=R/receipt['archive_path'];scope=receipt['scope']
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary as put
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
criteria={'action':'Only explicitly approved archived ADR1245 failed Oracle namespace removal; no production/other-scope/Gold changes','authorization':'검증 백업을 보존하고 해당 실패 실험만 Oracle에서 삭제 허용','success':['Archive complete hash/PK/all2175 body hashes verified before cleanup','Current Oracle rows byte-value stream matches original archive','Only approved scope removed, exact four table row counts, all other scope rows unchanged','Original300MiB90% allocation never exceeded under temporary270MiB server quota; quota restored','Measure reusable ASSM blocks; do not assume DELETE lowers allocated bytes'],'new_models':0,'table_ddl':0,'quota_changes':'temporary270MiB then restore300MiB','no_shrink_or_other_ddl':True};
if not (D/'criteria.json').exists():put(D/'criteria.json',criteria)
authorization={'user_instruction':criteria['authorization'],'target_scope':scope,'original_namespace':receipt['namespace'],'archive_sha256':receipt['archive_sha256'],'expected_counts':receipt['counts']}
if not (D/'authorization.json').exists():put(D/'authorization.json',authorization)
assert sha(archive)==receipt['archive_sha256']
with gzip.open(archive,'rb') as z:
 header=json.loads(z.readline())['header'];table_order=[]
 for line in z:
  t=json.loads(line)['table']
  if t not in table_order:table_order.append(t)
sys.path.insert(0,str(R/'06_TOOLS/EXPERIMENTS/adr_1252'));import quota_fence as fence
import oracledb
db=fence.connect();before=fence.inspect(db);assert before['quota_bytes']==fence.ORIGINAL and before['used_bytes']<=fence.CAP

def other_scope_counts():
 result={}
 with db.cursor() as c:
  for table in header['columns']:
   c.execute('SELECT SCOPE_HASH_VAL,COUNT(*) FROM SIDDA.'+table+' WHERE SCOPE_HASH_VAL<>:s GROUP BY SCOPE_HASH_VAL',s=scope);result[table]=dict(c.fetchall())
 return result

def space():
 names=('unformatted_blocks','unformatted_bytes','fs1_blocks','fs1_bytes','fs2_blocks','fs2_bytes','fs3_blocks','fs3_bytes','fs4_blocks','fs4_bytes','full_blocks','full_bytes')
 with db.cursor() as c:
  out=[c.var(oracledb.DB_TYPE_NUMBER) for _ in names]
  c.callproc('DBMS_SPACE.SPACE_USAGE',['SIDDA','LGL_AGT_BODY_A','TABLE',*out])
  return dict(zip(names,[int(v.getvalue()) for v in out]))

others=other_scope_counts();space_before=space();put(O/'before.json',{'capacity':before,'other_scope_counts':others,'body_space':space_before})
raw=hashlib.sha256();raw.update((json.dumps({'header':header},ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode());counts={};delete_counts={};applied=False
try:
 put(O/'quota-applied.json',fence.alter(db,fence.ORIGINAL,fence.CAP));applied=True
 # Serialize the exact same physical row values/ordering as the verified archive.
 for table in table_order:
  cols=header['columns'][table]
  projection=[('TO_CHAR('+n+',\'YYYY-MM-DD"T"HH24:MI:SS.FF6 TZH:TZM\') AS '+n) if n in ('STRT_DTTM','CHG_DTTM') else n for n in cols];counts[table]=0
  with db.cursor() as c:
   c.arraysize=250;c.execute('SELECT '+','.join(projection)+' FROM SIDDA.'+table+' WHERE SCOPE_HASH_VAL=:s ORDER BY '+','.join(cols[i] for i in header['primary_keys'][table]),s=scope)
   for row in c:
    values=[v.read() if hasattr(v,'read') else v for v in row];raw.update((json.dumps({'table':table,'row':values},ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode());counts[table]+=1
 assert counts==receipt['counts'] and raw.hexdigest()==receipt['uncompressed_sha256']
 with db.cursor() as c:
  c.execute('SELECT ST_CD FROM SIDDA.LGL_AGT_RUN_A WHERE SCOPE_HASH_VAL=:s FOR UPDATE',s=scope);assert c.fetchone()[0]=='FAILED'
  c.execute('SELECT ST_JSON_CN FROM SIDDA.LGL_EXEC_ST_A WHERE SCOPE_HASH_VAL=:s',s=scope)
  for (v,) in c:
   v=v.read() if hasattr(v,'read') else v;state=v if isinstance(v,dict) else json.loads(v)
   assert not(state.get('token') and state.get('expires',0)>time.time()),'Old scope still has active lease'
  for table in ('LGL_AGT_REC_A','LGL_AGT_RUN_A','LGL_EXEC_ST_A','LGL_AGT_BODY_A'):
   c.execute('DELETE FROM SIDDA.'+table+' WHERE SCOPE_HASH_VAL=:s',s=scope);delete_counts[table]=c.rowcount
  assert delete_counts==receipt['counts']
  assert other_scope_counts()==others
  for table in header['columns']:
   c.execute('SELECT COUNT(*) FROM SIDDA.'+table+' WHERE SCOPE_HASH_VAL=:s',s=scope);assert c.fetchone()[0]==0
 db.commit()
 after=fence.inspect(db);assert after['used_bytes']<=fence.CAP;space_after=space();assert other_scope_counts()==others
 result={'status':'complete','strict_success':True,'checks':{'archive_sha_verified':True,'current_oracle_rows_match_archive':True,'approved_only_exact_counts_removed':True,'other_scopes_same':True,'under_original90percent':True,'no_table_ddl':True},'removed_scope':scope,'deleted_counts':delete_counts,'archive':receipt,'before_capacity':before,'after_capacity':after,'body_space_before':space_before,'body_space_after':space_after,'new_real_model_calls':0,'user_authorization':criteria['authorization']};put(O/'result.json',result)
except BaseException:
 db.rollback();raise
finally:
 if applied:put(O/'quota-restored.json',fence.alter(db,fence.CAP,fence.ORIGINAL))
 db.close()
print(json.dumps({'deleted':delete_counts,'used_percent_after':result['after_capacity']['used_percent_of_original'],'space_before':space_before,'space_after':space_after},ensure_ascii=False))
