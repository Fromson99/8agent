from pathlib import Path
import json,sys,hashlib,random,time
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1261-oracle-progress-snapshot-dedup';D=A/'artifacts/design';O=A/'artifacts/run-001';read=lambda p:json.loads(p.read_text());F=read(D/'freeze.json');C=R/F['code_root'];sys.path[:0]=[str(C/'02_BACKEND'),str(R/'06_TOOLS/EXPERIMENTS/adr_1246'),str(R/'06_TOOLS/maintenance')]
from semantic_runtime.oracle_agent_records import AgentRecords,sha
from semantic_runtime.oracle_dp_io import canonical
from test_safety import MemorySQL
from experiment_json import write_summary
policy={'seeds':[20261101,20261102,20261103,20261104],'revisions':6,'unchanged_fields':['ontology','budget','scope','missing','claims'],'type':'New technical lossless fixtures fixed before running; no model/legal-quality grade','code_root':F['code_root'],'candidate':F['candidate_revision']};write_summary(D/'holdout-policy.json',policy)
count=0
for seed in policy['seeds']:
 rnd=random.Random(seed);data={'scope':['owner','doc'+str(seed)],'ontology':{'anchor':'A1','hash':'d'*64},'claims':[None,True,1.25,'인용😀\n"\\'],'missing':['unknown'],'budget':{'models':3,'tools':17,'deadline':1700000000},'frames':[rnd.randbytes(700).hex() for i in range(130)]};sql=MemorySQL();s=AgentRecords(sql,namespace='heldout'+str(seed));originals=[]
 for rev in range(6):
  data['revision']=rev;data['frames'][rev]+='정정'+str(rev);raw=canonical({'table':'stage_progress','columns':['payload'],'values':[['text',canonical(data)]],'key':[['integer','1']],'rowid':True}).encode();s.put_bodies([raw]);originals.append(raw)
 fresh=AgentRecords(sql,namespace='heldout'+str(seed))
 for raw in originals:assert fresh.body(sha(raw))==raw;count+=1
write_summary(O/'holdout.json',{'passed':count,'failed':0,'new_models':0,'fixture_policy':policy,'all_versions_exact':True});print('New technical holdout',count,'exact roundtrips')
