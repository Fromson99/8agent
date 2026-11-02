from pathlib import Path
import sys,json,gzip,hashlib,base64,time,resource
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1261-oracle-progress-snapshot-dedup';D=A/'artifacts/design';O=A/'artifacts/run-001';read=lambda p:json.loads(p.read_text());mode=sys.argv[1];assert mode in ('baseline','candidate')
meta=read(D/'original-fixture.json');archive=R/meta['archive_path']
with archive.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==meta['archive_sha256']
C=R/(read(D/'baseline.json')['manifest']['code_root'] if mode=='baseline' else read(D/'freeze.json')['code_root']);sys.path[:0]=[str(C/'02_BACKEND'),str(R/'06_TOOLS/EXPERIMENTS/adr_1246'),str(R/'06_TOOLS/maintenance')]
from semantic_runtime.oracle_agent_records import AgentRecords,sha
from semantic_runtime.oracle_dp_io import canonical
from test_safety import MemorySQL
from experiment_json import write_summary
sql=MemorySQL();store=AgentRecords(sql,namespace='fixed-original-fixture');start=time.monotonic();count=0
with gzip.open(archive,'rt') as f:
 for line in f:
  row=json.loads(line);raw=base64.b64decode(row['raw_base64']);assert sha(raw)==row['sha256'];store.put_bodies([raw]);assert store.body(row['sha256'])==raw;count+=1
write_sql=sql.calls;fresh=AgentRecords(sql,namespace='fixed-original-fixture');before=sql.calls
with gzip.open(archive,'rt') as f:
 for line in f:
  row=json.loads(line);raw=base64.b64decode(row['raw_base64']);assert fresh.body(row['sha256'])==raw
layouts={}
for (h,n),v in sql.parts.items():
 if n==0:layouts[v['layout_version']]=layouts.get(v['layout_version'],0)+1
out={'mode':mode,'original_snapshots':count,'original_bytes':meta['body_original_bytes'],'readback_equal_all':True,'body_parts':len(sql.parts),'body_envelope_characters':sum(len(canonical(v)) for v in sql.parts.values()),'body_layouts':layouts,'write_phase_sql':write_sql,'fresh_read_sql':sql.calls-before,'all_sql':sql.calls,'seconds':time.monotonic()-start,'rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'models':0,'real_oracle_writes':0,'all_history_retained':True,'fixture_sha256':meta['archive_sha256']};write_summary(O/('codec-'+mode+'-final.json'),out);print(json.dumps(out))
