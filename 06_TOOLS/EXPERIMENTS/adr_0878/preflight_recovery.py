from pathlib import Path
import ast,hashlib,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0878-main85-cm-registered-live';D=A/'artifacts/design';read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
old=R/'06_TOOLS/EXPERIMENTS/adr_0878/live.py';p=old.with_name('live_v2.py');s=old.read_text().replace("D/'freeze.json'","D/'freeze-v2.json'").replace("A/'artifacts/run-001'","A/'artifacts/run-002'")
s=s.replace(",'session_id':'adr0878-'+case['id'],'request_id':'adr0878-'+case['id']",'');ast.parse(s);p.write_text(s)
# Ordinary public RAG entry remains unchanged; explicit durable-session mode was accidental.
pre=read(A/'artifacts/run-001/cm-001/result.json');assert pre['model_calls']==0
put(D/'preflight-recovery.json',{'cause':'Harness accidentally supplied optional session_id which requires a complete authenticated case principal. Ordinary public RAG supports no-session requests. No model call or product result occurred.','before_request':str((A/'artifacts/run-001/cm-001/request.json').relative_to(R)),'correction':'Remove accidental optional session/request selectors, preserving question, 65-document public grant, model, MAIN85 code and data. Durable case mode is outside this five-question observation.','original_runner_sha256':sha(old),'runner_v2_sha256':sha(p),'remaining_total_model_calls':200,'not_product_fix':True})
m=read(A/'실험/manifest.json');m['runs'][0].update(purpose='preflight',status='complete',selection_rule='Only cm-001 service envelope; rejected pre-model due to incomplete optional case principal',artifact_path=str((A/'artifacts/run-001/cm-001/result.json').relative_to(R)),sha256=sha(A/'artifacts/run-001/cm-001/result.json'))
m['runs'].append({'id':'run-002','purpose':'primary','parent_run_id':'run-001','arm_ids':['observed'],'selection_rule':read(D/'criteria.json')['selection'],'status':'planned','artifact_path':str((A/'artifacts/run-002/result.json').relative_to(R)),'sha256':'PENDING'})
m['retrieval_accounting']['stage_ledger'].update(summary_run_id='run-002',artifact_path=str((A/'artifacts/run-002/retrieval-ledger.json').relative_to(R)));put(A/'실험/manifest.json',m)
f=read(D/'freeze.json');f['files'][str(p.relative_to(R))]=sha(p);f['files'][str((D/'preflight-recovery.json').relative_to(R))]=sha(D/'preflight-recovery.json');f['files'][str(Path(__file__).relative_to(R))]=sha(Path(__file__));put(D/'freeze-v2.json',f)
print('Zero-model preflight retained; ordinary public RAG envelope frozen in run-002')
