"""One frozen public product request. This process never loads evaluator gold."""
from pathlib import Path
import hashlib,importlib.util,json,sys,time,traceback,argparse
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0701-structure-preserved-final-holdout';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=argparse.ArgumentParser();p.add_argument('--arm',choices=['baseline','structured-reading'],required=True);p.add_argument('--case',required=True);p.add_argument('--setup-only',action='store_true');args=p.parse_args()
freeze=read(D/'freeze.json')
for file,h in freeze['files'].items():assert sha(R/file)==h,file
b=read(D/'bindings.json');code=R/b['codes'][args.arm];case=next(c for c in read(D/'dataset.json')['cases'] if c['case_id']==args.case)
out=A/'artifacts'/('setup-check' if args.setup_only else 'run-001')/args.arm/args.case;out.mkdir(parents=True,exist_ok=False)
generation=R/b['source_generation'];sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('frozen_experiment_client',R/b['experiment_client']);audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport,provider_request
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.stage_runner import StageRunner
from semantic_runtime.legal_agent.unified_runtime import open_cases
from fastapi.testclient import TestClient
client=audit.ExperimentClient(R,out/'provider',max_calls=40,max_output_tokens=6400,max_repairs=0)
class Transport(LocalGemmaTransport):
 def send_once(self,*,body,ticket):
  view=json.loads(body['messages'][1]['content'])['view'];phase=view.get('source_stage',view['phase']);print('MODEL_START',client.calls+1,phase,flush=True)
  result=client.chat_completions(provider_request(body),phase='product-'+str(client.calls+1)+'-'+phase,timeout_seconds=ticket['remaining_seconds']);raw=result['body_json']
  if raw.get('provider')!='Parasail' or raw.get('model')!=self.binding['model']:raise ContractError('provider binding')
  print('MODEL_DONE',client.calls,client.usage[-1]['seconds'],flush=True);return result
transport=Transport(code,R);profile=read(code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=transport.binding
principal={'user_id':'adr0701-'+args.arm+'-'+args.case,'team_id':'public-laws','authenticated':True,'document_ids':list(transport.public_scope)}
body={'question':case['question'],'document_ids':list(transport.public_scope),'public_question':True,'use_llm':True,'session_id':'adr0701-'+args.arm+'-'+args.case,'request_id':'adr0701-run001-'+args.arm+'-'+args.case}
put(out/'profile.json',profile);put(out/'request.json',body)
start=time.monotonic();row={'case_id':args.case,'arm':args.arm,'question':case['question'],'code_root':str(code),'source_generation':str(generation),'model':client.model,'field_execution':False,'active_pointer_before':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')}
try:
 app=create_app(out,generation,contracts_root=code,workspace_root=R,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=transport,runtime_root=out/'runtime',memory_identity=lambda _:principal)
 StageRunner(app.state.pipeline).verify_profile()
 cases=open_cases(app.state.pipeline,out/'binding-runtime',{},principal)
 try:row['expected_binding']=cases.executor.binding
 finally:cases.close()
 with TestClient(app) as api:
  ready=time.monotonic();row['app_setup_seconds']=ready-start
  if args.setup_only:row.update(http_status=200,setup_only=True)
  else:
   response=api.post('/v1/rag/ask',json=body);row.update(http_status=response.status_code,output=response.json(),request_seconds=time.monotonic()-ready)
except Exception as exc:
 row.update(http_status=500,error_type=type(exc).__name__,error=str(exc));(out/'error.txt').write_text(traceback.format_exc())
finally:
 row.update(total_seconds=time.monotonic()-start,model_calls=client.calls,usage=client.usage,active_pointer_after=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'));put(out/'result.json',row)
 print('RESULT',json.dumps({k:v for k,v in row.items() if k not in ('output','usage','expected_binding')},ensure_ascii=False),flush=True)
