from pathlib import Path
import json,gzip,hashlib,base64,sys,importlib.util,time
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1261-oracle-progress-snapshot-dedup';D=A/'artifacts/design';b=json.loads((D/'baseline.json').read_text());sys.path.insert(0,str(R/b['manifest']['code_root']/'02_BACKEND'));sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from agent_record_oracle_r2 import connection;from experiment_json import write_summary
sp=importlib.util.spec_from_file_location('fixture_oracle',R/'06_TOOLS/EXPERIMENTS/adr_1244/test_records.py');module=importlib.util.module_from_spec(sp);sp.loader.exec_module(module)
from semantic_runtime.oracle_agent_records import AgentRecords,RecordSQL
scope='3668417bd1558049a4c16a16d8d2865fa47f97834da1ca83eeb7c9841f9d5f1f';db=connection()
with db.cursor() as c:
 c.execute("SELECT BODY_HASH_VAL,REC_REV_NO FROM SIDDA.LGL_AGT_REC_A WHERE SCOPE_HASH_VAL=:s AND REC_KIND_CD='SQLROW:stage_progress' AND REC_REV_NO>0 ORDER BY REC_REV_NO,REC_KEY_HASH_VAL",s=scope);rows=c.fetchall()
assert len(rows)==342 and len({r[0] for r in rows})==342
r=AgentRecords(RecordSQL(module.LocalOracle(db),binding='readonly-codec-fixture',deadline=time.monotonic()+600,max_calls=10000),namespace='adr1258-main129-live');assert r.scope==scope
out=D/'original-progress342.jsonl.gz';assert not out.exists();raw_hash=hashlib.sha256();total=0;maxsize=0
with out.open('xb') as f:
 with gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as z:
  for offset in range(0,len(rows),25):
   group=rows[offset:offset+25];values=r.bodies(h for h,_ in group)
   for h,revision in group:
    raw=values[h];assert hashlib.sha256(raw).hexdigest()==h
    line=(json.dumps({'sha256':h,'revision':revision,'raw_base64':base64.b64encode(raw).decode()},sort_keys=True,separators=(',',':'))+'\n').encode();raw_hash.update(line);z.write(line);total+=len(raw);maxsize=max(maxsize,len(raw))
with out.open('rb') as f:compressed_hash=hashlib.file_digest(f,'sha256').hexdigest()
v={'scope':scope,'original_progress_rows':342,'body_original_bytes':total,'largest_body_bytes':maxsize,'archive_path':str(out.relative_to(R)),'archive_sha256':compressed_hash,'uncompressed_archive_sha256':raw_hash.hexdigest(),'compressed_archive_bytes':out.stat().st_size,'oracle_reads':r.sql.calls,'no_mutations':True,'new_models':0,'data_roles':'Frozen historical storage replay only, not new quality or independent samples'};write_summary(D/'original-fixture.json',v);db.close();print(json.dumps(v))
