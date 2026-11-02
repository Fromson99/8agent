"""Offline assertion against independently decoded Oracle publications; no model/database writes."""
from pathlib import Path
import json,hashlib,sys
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1258-main129-fixed-cap-oracle-live';O=A/'artifacts/run-001';P=O/'live/gold-369';D=A/'artifacts/design';read=lambda p:json.loads(p.read_text())
x=read(O/'audit-decoded.json');response=read(P/'response.json') if (P/'response.json').exists() else {};body=response.get('body',{});answer=body.get('answer');states=[v['status'] for j in x['journals'] for v in j.get('runs',[])];pubs=x['publications'];matches=[]
C=R/read(D/'before.json')['binding']['engine_root'];sys.path.insert(0,str(C/'02_BACKEND'));from semantic_runtime.contracts import digest
for p in pubs:
 value=json.loads(p['result_json']);matches.append({'status':p['status'],'hash_valid':digest(value)==p['result_hash'],'same_answer':bool(answer) and value.get('answer')==answer,'result_hash':p['result_hash']})
checks={'api200':response.get('http_status')==200,'nonempty_answer':isinstance(answer,dict) and bool(answer.get('text','').strip()),'fresh_oracle_published_same_answer':any(p['status']=='PUBLISHED' and p['hash_valid'] and p['same_answer'] for p in matches),'oracle_run_completed':'COMPLETED' in states,'duplicate_same_answer_no_calls':False}
if (P/'duplicate.json').exists():
 v=read(P/'duplicate.json');checks['duplicate_same_answer_no_calls']=v['status']==200 and v['same_answer'] and v['extra_model_calls']==0
out={'checks':checks,'strict_success':all(checks.values()),'publication_results':matches,'oracle_run_states':states,'fresh_process_oracle_readback':True,'actual_answer_text':answer.get('text','') if isinstance(answer,dict) else None,'answer_is_model_proposal_not_legal_quality_certification':True,'new_model_calls':0,'database_writes':0}
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
write_summary(O/'final-readback.json',out);print(json.dumps({k:out[k] for k in ('checks','strict_success','oracle_run_states')},ensure_ascii=False))
