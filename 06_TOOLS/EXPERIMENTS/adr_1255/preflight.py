from pathlib import Path
import sys,json,hashlib,importlib.util,gzip
R=Path('/home/jin/8-AGENT');D=R/'04_EXPERIMENTS/ADR/ADR-1255-wiki-workspace-oracle-live/artifacts/design'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(n,v):(D/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def module(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
p=R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';gold=module('workspace_gold_preflight',p/'connect.py');DID='7bbe815ff43b6635'
with gold.open_store(documents=[DID],seconds=300,max_calls=1000) as (store,req,tr):
 from semantic_runtime.legal_agent.ontology_compiler import content_hash
 doc=req.sources.document(DID);originals=[]
 for uid in ['1420','1421','1422','1423']:
  anchor={'document_id':DID,'version':doc['source_artifact_sha256'],'unit_id':uid};text=store.gold_ports.source_reader(anchor)
  anchor.update(content_sha256=content_hash(text),label='상법 제369조 / 단위 '+uid)
  originals.append({'id':'S'+uid,'anchor':anchor,'text':text})
 put('originals.json',originals)
 put('source-binding.json',{'document':doc,'request_release':req.release_id,'generation':store.manifest.get('generation_id') if hasattr(store,'manifest') else None,'sql_calls':req.sql.calls,'mapping_sha256':store.gold_ports.mapping.target_sha256})
admin=module('workspace_preflight_admin',R/'06_TOOLS/maintenance/agent_record_oracle_r2.py')
with admin.connection() as db:
 with db.cursor() as c:
  c.execute("SELECT username,bytes,max_bytes FROM dba_ts_quotas WHERE username IN ('SIDDA','A8_GONT_AGENT','A8_GR12_CM1208') ORDER BY username")
  quotas=[list(x) for x in c.fetchall()]
  c.execute("SELECT owner,table_name FROM all_tables WHERE (owner='A8_GONT_AGENT' AND table_name IN ('LGL_ONT_WORK_A','LGL_ONT_EVT_A')) OR (owner='SIDDA' AND table_name IN ('LGL_AGT_RUN_A','LGL_AGT_REC_A','LGL_AGT_BODY_A','LGL_EXEC_ST_A'))")
  tables=[list(x) for x in c.fetchall()]
 assert len(tables)==6
 put('oracle-preflight.json',{'quotas':quotas,'tables':tables,'DDL':0,'model_calls':0})
origin=R/'04_EXPERIMENTS/ADR/ADR-1235-gold-ontology-transport-live/artifacts/run-001/live/gold-369/canonical/007-output.json.gz';v=json.loads(gzip.decompress(origin.read_bytes()))
cases=[{'id':'past-voting-'+str(i),'origin':{'path':str(origin.relative_to(R)),'sha256':sha(origin),'pointer':f'/claims/{i}/rule/norms/0/text'},'payload':v['claims'][i]['rule']['norms'][0]['text']} for i in (0,1)]
put('records.json',cases)
print(json.dumps({'source_units':len(originals),'source_chars':sum(len(x['text']) for x in originals),'records':len(cases),'quotas':quotas,'sql_calls':req.sql.calls},ensure_ascii=False))
