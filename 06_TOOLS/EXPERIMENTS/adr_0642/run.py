"""One isolated public-law arm. No product access to offline gold or prior answers."""
import argparse,hashlib,importlib.util,inspect,json,sys,time,traceback
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0642-shortcut-main-integration-holdout';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main(arm,cid,check=False):
 b=read(D/'bindings.json');freeze=read(D/'freeze.json')
 for file,h in freeze['files'].items():assert sha(R/file)==h,file
 assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['active_pointer_hash']
 if arm=='baseline':
  code=R/b['baseline_code']
  for file,h in b['baseline_files'].items():assert sha(code/file)==h,file
 else:
  c=R/b['candidate'];m=read(c/'candidate.json');rev=m['revisions'][0]
  for row in rev['files']:assert sha(R/row['frozen_path'])==row['snapshot_sha256']
  code=c/'revisions/rev-001/snapshot'
 sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
 # The audited host client is separate from the selected product package.
 spec=importlib.util.spec_from_file_location('audited_experiment_client',R/'02_BACKEND/lawrag/research/experiment_client.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
 from semantic_runtime.app import create_app
 from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
 from semantic_runtime.legal_agent.errors import TransportError,ProposalError,ContractError
 from fastapi.testclient import TestClient
 case=next(c for c in read(D/'inputs.json') if c['case_id']==cid)
 directory=A/'artifacts'/('bootstrap' if check else 'run-001')/cid/arm
 directory.mkdir(parents=True,exist_ok=False)
 client=audit.ExperimentClient(R,directory/'provider',max_calls=0 if check else 40,max_output_tokens=6400,max_repairs=0)
 class Transport(LocalGemmaTransport):
  def send_once(self,*,body,ticket):
   if check:raise AssertionError('bootstrap cannot call a model')
   if sha(R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')!=b['policy_hash']:raise ContractError('policy drift')
   result=client.chat_completions(body,phase='product-'+str(client.calls+1),timeout_seconds=ticket['remaining_seconds'])
   raw=result['body_json'];choices=raw.get('choices',[])
   if raw.get('provider')!='Parasail' or raw.get('model')!=self.binding['model']:raise ContractError('provider binding')
   if len(choices)!=1 or choices[0].get('finish_reason')!='stop':
    error=ProposalError('incomplete response');error.response=result;raise error
   if ((raw.get('usage',{}).get('completion_tokens_details') or {}).get('reasoning_tokens')) or choices[0]['message'].get('reasoning'):raise ContractError('unexpected reasoning')
   return result
 transport=Transport(code,R)
 profile=read(code/('00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json' if arm=='baseline' else '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'))
 profile.update(model_binding=transport.binding,max_model_attempts=40,wall_seconds=480,max_output_tokens=6400)
 principal={'user_id':'holdout-'+cid,'team_id':'public-shortcut-holdout','authenticated':True,'document_ids':[case['document_id']]}
 kwargs={'contracts_root':code,'provider':object(),'implementation':'legal-agent-tools-v5' if arm=='baseline' else 'legal-agent-unified-v6',
         'legal_agent_profile':profile,'legal_agent_transport':transport,'runtime_root':directory/'runtime'}
 if 'memory_identity' in inspect.signature(create_app).parameters:kwargs['memory_identity']=lambda _:principal
 body={'question':case['question'],'document_ids':[case['document_id']],'public_question':True,'use_llm':True}
 if arm!='baseline':body.update(session_id=cid,request_id='initial')
 put(directory/'input.json',body);put(directory/'profile.json',profile)
 start=time.monotonic();row={}
 try:
  app=create_app(directory,R/b['generation'],**kwargs)
  with TestClient(app) as api:
   if check:
    from semantic_runtime.stage_runner import StageRunner
    if hasattr(StageRunner,'verify_profile'):StageRunner(app.state.pipeline).verify_profile()
    row={'bootstrap':True,'model_calls':0}
   else:
    started=time.monotonic();response=api.post('/v1/rag/ask',json=body)
    row={'http_status':response.status_code,'output':response.json(),'seconds':time.monotonic()-started}
 except Exception as exc:
  row={'http_status':500,'output':{'error_type':type(exc).__name__,'error':str(exc)},'seconds':time.monotonic()-start}
  (directory/'error.txt').write_text(traceback.format_exc())
 row.update(case_id=cid,arm=arm,provider_calls=client.calls,usage=client.usage,bootstrap_seconds=time.monotonic()-start-row.get('seconds',0))
 put(directory/'result.json',row)
 print(json.dumps({k:row.get(k) for k in ['case_id','arm','http_status','bootstrap','provider_calls','seconds']},ensure_ascii=False),flush=True)
 return 0 if row.get('http_status',200)==200 else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--arm',choices=['baseline','integrated'],required=True);p.add_argument('--case',required=True);p.add_argument('--check-only',action='store_true');a=p.parse_args();raise SystemExit(main(a.arm,a.case,a.check_only))
