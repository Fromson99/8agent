"""Fixed small real Oracle workload; counts statements/parts, not model latency."""
from test_records import oracle_agent
from semantic_runtime.legal_agent import journal_storage as js
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]

def test_small_real_oracle_structured_journal_workload(oracle_agent,monkeypatch):
 records,client,root=oracle_agent;monkeypatch.setenv('GENOS_JOURNAL_STORAGE','compact')
 # 100 structured evidence objects and8 revisions, specified before comparison.
 source=[{'id':str(i),'document':'fixture','coords':[i,0,80],'text':'권한을 보존한 원문과 조건 확인. '*80} for i in range(100)]
 db=js.connect(root/'metrics.sqlite',isolation_level=None);js.initialize(db);db.execute('CREATE TABLE observations(id INTEGER PRIMARY KEY,payload TEXT)')
 for i in range(8):
  text=json.dumps({'iteration':i,'evidence':source,'gaps':['미확인 조건'],'accepted':False},ensure_ascii=False,sort_keys=True,separators=(',',':'))
  db.execute('INSERT INTO observations VALUES(?,?)',(i,js.store(db,text)))
 db.close();before_reopen=records.sql.calls
 db=js.connect(root/'metrics.sqlite',isolation_level=None)
 values=[json.loads(r[0]) for r in db.execute('SELECT payload FROM observations ORDER BY id')]
 assert len(values)==8 and all(v['evidence']==source and v['iteration']==i for i,v in enumerate(values));db.close()
 with client.db.cursor() as c:
  c.execute('SELECT COUNT(*),COALESCE(SUM(DBMS_LOB.GETLENGTH(PART_JSON_CN)),0) FROM SIDDA.LGL_AGT_BODY_A WHERE SCOPE_HASH_VAL=:scope',scope=records.scope);parts,characters=c.fetchone()
  c.execute('SELECT COUNT(*) FROM SIDDA.LGL_AGT_REC_A WHERE SCOPE_HASH_VAL=:scope',scope=records.scope);rows=c.fetchone()[0]
 value={'body_parts':parts,'body_envelope_characters':characters,'record_rows':rows,'write_phase_sql':before_reopen,'all_sql':records.sql.calls,'readback_equal':True,'real_model_calls':0,'actual_oracle':True,'source_objects':100,'revisions':8,'legacy_compact_new_writes':db.compact}
 sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'));from experiment_json import write_summary
 write_summary(ROOT/'04_EXPERIMENTS/ADR/ADR-1246-oracle-record-storage-safety/artifacts'/('metrics-'+os.environ['ADR1246_METRIC_TAG']+'.json'),value)
