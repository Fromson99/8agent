"""Fresh-process Oracle readback; never models, writes, or job replay."""
from common import *
gold,C,F=frozen_gold();sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.contracts import digest
from semantic_runtime.oracle_agent_records import AgentRecords,RecordSQL
from semantic_runtime.ontology_work.store import OracleWorkStore
from semantic_runtime.ontology_work.repository import Repository
admin=module('rb_admin',R/'06_TOOLS/maintenance/agent_record_oracle_r2.py')
local=module('rb_local',R/'06_TOOLS/EXPERIMENTS/adr_1244/test_records.py')
conn=admin.connection();port=local.LocalOracle(conn);sql=RecordSQL(port,binding='adr1259-readback',deadline=time.monotonic()+180,max_calls=300)
objects=OracleWorkStore(AgentRecords(sql,namespace='adr1259-wiki-live'));repo=Repository(admin.connection,dialect='oracle',owner='A8_GONT_AGENT')
result={'fresh_process':True,'rows':[],'model_calls':0,'writes':0}
def check(bid):
 row=repo.latest(bid);assert row
 value=objects.get(row['work_hash']);assert value['bundle_id']==bid
 result['rows'].append({'bundle_id':bid,**row,'kind':value['kind']})
 return value
try:
 for r in read(O/'live/raws.json'):check(r['bundle_id'])
 for p in sorted((O/'live/authoring').glob('*-input.json.gz')):
  v=json.loads(gzip.decompress(p.read_bytes()));ctx=v['context']
  if 'glossary_candidates' not in ctx:continue
  bid='obs-'+digest([digest(ctx['raw']),ctx['profile_hash'],digest(ctx['glossary_candidates']),F['candidate_revision']['revision_sha256']])
  n=check(bid)['normalized'];raw(O/'readback-002'/f'{bid}.json.gz',n)
  for obs in n['proposal']['observations']:
   assert obs['reason']['state']=='NOT_RECORDED' and obs['purpose']['state']=='NOT_RECORDED'
 for r in read(O/'live/workspace.json')['items']:check(r['bundle_id'])
 result['verified']=True;result['sql_calls']=sql.calls;result['errors']=port.errors
 put(O/'readback.json',result);print(json.dumps(result,ensure_ascii=False))
finally:conn.close()
