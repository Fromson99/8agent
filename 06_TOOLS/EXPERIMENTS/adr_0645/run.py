"""Frozen v6 parent versus procedure cold/warm HTTP requests, no gold access."""
import argparse,hashlib,importlib.util,json,sys,time,traceback
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0645-shortcut-deterministic-procedure';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main(arm,cid,check=False):
 b=read(D/'bindings.json')
 for file,h in read(D/'freeze.json')['files'].items():assert sha(R/file)==h,file
 assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['active_pointer_hash']
 c=R/b['parent_candidate' if arm=='baseline' else 'candidate'];m=read(c/'candidate.json')
 for row in m['revisions'][0]['files']:assert sha(R/row['frozen_path'])==row['snapshot_sha256']
 code=c/'revisions/rev-001/snapshot';sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
 spec=importlib.util.spec_from_file_location('audit',R/'02_BACKEND/lawrag/research/experiment_client.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
 from semantic_runtime.app import create_app
 from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
 from semantic_runtime.legal_agent.errors import ContractError,ProposalError
 from fastapi.testclient import TestClient
 case=next(c for c in read(D/'inputs.json') if c['case_id']==cid)
 directory=A/'artifacts'/('bootstrap' if check else 'run-001')/cid/arm;directory.mkdir(parents=True,exist_ok=False)
 client=audit.ExperimentClient(R,directory/'provider',max_calls=0 if check else 60,max_output_tokens=6400,max_repairs=0)
 class Transport(LocalGemmaTransport):
  def send_once(self,*,body,ticket):
   if check:raise AssertionError('bootstrap model forbidden')
   result=client.chat_completions(body,phase='product-'+str(client.calls+1),timeout_seconds=ticket['remaining_seconds'])
   raw=result['body_json'];choices=raw.get('choices',[])
   if raw.get('provider')!='Parasail' or raw.get('model')!=self.binding['model']:raise ContractError('provider binding')
   if len(choices)!=1 or choices[0].get('finish_reason')!='stop':
    error=ProposalError('incomplete response');error.response=result;raise error
   if ((raw.get('usage',{}).get('completion_tokens_details') or {}).get('reasoning_tokens')) or choices[0]['message'].get('reasoning'):raise ContractError('unexpected reasoning')
   return result
 transport=Transport(code,R);profile=read(code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
 profile.update(model_binding=transport.binding,max_model_attempts=40,wall_seconds=480,max_output_tokens=6400)
 principal={'user_id':'probe-'+cid,'team_id':'public-procedure-probe','authenticated':True,'document_ids':[case['document_id']]}
 app=create_app(directory,R/b['generation'],contracts_root=code,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=transport,runtime_root=directory/'runtime',memory_identity=lambda _:principal)
 put(directory/'profile.json',profile);rows=[]
 with TestClient(app) as api:
  if check:
   from semantic_runtime.stage_runner import StageRunner
   StageRunner(app.state.pipeline).verify_profile()
   put(directory/'result.json',{'bootstrap':True,'calls':0});return 0
  for temperature in (['parent'] if arm=='baseline' else ['cold','warm']):
   body={'question':case['question'],'document_ids':[case['document_id']],'public_question':True,'use_llm':True,'session_id':cid+'-'+temperature,'request_id':temperature}
   calls=client.calls;usage=len(client.usage);start=time.monotonic()
   try:
    response=api.post('/v1/rag/ask',json=body);row={'http_status':response.status_code,'output':response.json()}
   except Exception as exc:
    row={'http_status':500,'output':{'error_type':type(exc).__name__,'error':str(exc)}}
    (directory/(temperature+'-error.txt')).write_text(traceback.format_exc())
   row.update(case_id=cid,arm=arm,temperature=temperature,input=body,seconds=time.monotonic()-start,provider_calls=client.calls-calls,usage=client.usage[usage:])
   rows.append(row);put(directory/(temperature+'.json'),row)
   print(json.dumps({k:row[k] for k in ['case_id','arm','temperature','http_status','provider_calls','seconds']},ensure_ascii=False),flush=True)
 put(directory/'result.json',rows)
 return 0 if all(r['http_status']==200 for r in rows) else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--arm',choices=['baseline','procedure'],required=True);p.add_argument('--case',required=True);p.add_argument('--check-only',action='store_true');args=p.parse_args();raise SystemExit(main(args.arm,args.case,args.check_only))
