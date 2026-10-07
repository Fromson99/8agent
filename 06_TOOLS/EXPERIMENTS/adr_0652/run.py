"""Frozen, gold-free live HTTP sequences; no scripted model decisions."""
import argparse,hashlib,importlib.util,json,sys,time,traceback,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[3]
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main(adr,arm,cid):
 A=R/adr;D=A/'artifacts/design';b=read(D/'bindings.json')
 for f,h in read(D/'freeze.json')['files'].items():assert sha(R/f)==h,f
 for f,h in read(D/'release-freeze.json')['files'].items():assert sha(R/f)==h,f
 assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['active_pointer_hash']
 c=R/b['parent_candidate' if arm=='baseline' else 'candidate'];m=read(c/'candidate.json');rev=m['revisions'][-1]
 for row in rev['files']:assert sha(R/row['frozen_path'])==row['snapshot_sha256']
 code=c/'revisions'/rev['revision_id']/'snapshot';sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
 spec=importlib.util.spec_from_file_location('audit',R/'02_BACKEND/lawrag/research/experiment_client.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
 from semantic_runtime.app import create_app
 from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
 from semantic_runtime.legal_agent.errors import ContractError,ProposalError
 from fastapi.testclient import TestClient
 case=next(c for c in read(D/'inputs.json') if c['case_id']==cid);directory=A/'artifacts/run-001'/cid/arm;directory.mkdir(parents=True,exist_ok=False)
 client=audit.ExperimentClient(R,directory/'provider',max_calls=100,max_output_tokens=6400,max_repairs=0)
 class Transport(LocalGemmaTransport):
  def send_once(self,*,body,ticket):
   result=client.chat_completions(body,phase='product-'+str(client.calls+1),timeout_seconds=ticket['remaining_seconds'])
   raw=result['body_json'];choices=raw.get('choices',[])
   if raw.get('provider')!='Parasail' or raw.get('model')!=self.binding['model']:raise ContractError('provider binding')
   if len(choices)!=1 or choices[0].get('finish_reason')!='stop':
    error=ProposalError('incomplete response');error.response=result;raise error
   if ((raw.get('usage',{}).get('completion_tokens_details') or {}).get('reasoning_tokens')) or choices[0]['message'].get('reasoning'):raise ContractError('unexpected reasoning')
   return result
 transport=Transport(code,R);profile=read(code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile.update(model_binding=transport.binding,max_model_attempts=40,wall_seconds=480,max_output_tokens=6400)
 principal={'user_id':'validation-'+cid,'team_id':'public-procedure-validation','authenticated':True,'document_ids':[case['document_id']]}
 app=create_app(directory,R/b['generation'],contracts_root=code,provider=object(),implementation='legal-agent-unified-v6' if arm=='baseline' else None,legal_agent_profile=profile,legal_agent_transport=transport,runtime_root=directory/'runtime',memory_identity=lambda _:principal)
 put(directory/'profile.json',profile);rows=[];investigation=None;goal=None;session=cid+'-s1'
 with TestClient(app) as api:
  for n,turn in enumerate(case['turns']):
   if turn.get('new_case') or turn.get('new_session'):session=cid+'-s'+str(n+1)
   body={'question':turn['question'],'document_ids':[case['document_id']],'public_question':True,'use_llm':True,'session_id':session,'request_id':'turn-'+str(n+1)}
   if investigation and not turn.get('new_case'):body['investigation_id']=investigation
   calls=client.calls;usage=len(client.usage);start=time.monotonic()
   try:
    response=api.post('/v1/rag/ask',json=body);row={'http_status':response.status_code,'output':response.json()}
   except Exception as exc:
    row={'http_status':500,'output':{'error_type':type(exc).__name__,'error':str(exc)}};(directory/('turn-'+str(n+1)+'-error.txt')).write_text(traceback.format_exc())
   row.update(case_id=cid,arm=arm,turn=n+1,input=body,seconds=time.monotonic()-start,provider_calls=client.calls-calls,usage=client.usage[usage:],same_goal_expected=bool(turn.get('same_goal')),same_goal=not turn.get('same_goal') or (goal is not None and row['output'].get('goal_id')==goal))
   if row['http_status']==200:
    investigation=row['output'].get('investigation_id');goal=row['output'].get('goal_id')
    q=api.post('/v1/rag/memory/query',json={'query_kind':'investigation','investigation_id':investigation,'session_id':session,'request_id':'inspect-'+str(n)});row['current_case']=q.json()
   dbpath=directory/'runtime/case-memory/cases-v4.sqlite'
   if dbpath.exists():
    with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
     db.row_factory=sqlite3.Row
     row['fact_heads']=[dict(x) for x in db.execute('SELECT f.* FROM sw_fact f JOIN sw_fact_head h ON f.id=h.id AND f.revision=h.revision')]
   rows.append(row);put(directory/('turn-'+str(n+1)+'.json'),row);put(directory/'result.json',rows)
   print(json.dumps({k:row[k] for k in ['case_id','arm','turn','http_status','provider_calls','seconds','same_goal']},ensure_ascii=False),flush=True)
 return 0 if all(r['http_status']==200 and r['same_goal'] for r in rows) else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--adr',default='04_EXPERIMENTS/ADR/ADR-0649-shortcut-selection-multiturn-repair');p.add_argument('--arm',required=True);p.add_argument('--case',required=True);a=p.parse_args();raise SystemExit(main(a.adr,a.arm,a.case))
