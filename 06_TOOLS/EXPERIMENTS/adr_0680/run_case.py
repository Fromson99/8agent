"""One immutable, isolated product case. Gold is never loaded by this process."""
from pathlib import Path
import hashlib,importlib.util,json,os,shutil,sys,time,traceback,argparse
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0680-investigation-main-consumer-integration';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=argparse.ArgumentParser();p.add_argument('--arm',choices=['baseline','integrated'],required=True);p.add_argument('--case',required=True);p.add_argument('--setup-only',action='store_true');args=p.parse_args()
b=read(D/'bindings.json')
for seal in ['freeze.json','release-freeze.json']:
 for file,h in read(D/seal)['files'].items():assert sha(R/file)==h,file
code=R/b['baseline_code' if args.arm=='baseline' else 'stage'];dataset=read(D/'dataset.json');case=next(c for c in dataset['cases']+dataset.get('regression_cases',[]) if c['case_id']==args.case)
directory=A/'artifacts'/('setup-check' if args.setup_only else 'regression' if args.case.startswith('REG-') else 'run-001')/args.arm/args.case;directory.mkdir(parents=True,exist_ok=args.setup_only)
source=R/b['source_generation'];generation=A/'artifacts/prepared-generations'/args.arm/args.case
def copy_file(src,dst):
 if '/cache/' in str(src) or Path(src).suffix=='.json':return shutil.copy2(src,dst)
 os.symlink(str(Path(src).resolve()),dst);return dst
if not generation.exists():raise RuntimeError('generation preflight must complete for every arm/case before requests')
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('audited_experiment_client',R/'02_BACKEND/lawrag/research/candidates/adr_0680/integrated/revisions/rev-001/snapshot/02_BACKEND/lawrag/research/experiment_client.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
import semantic_runtime.legal_agent.local_gemma as local_model
provider_request=getattr(local_model,'provider_request',lambda body:body)
from semantic_runtime.legal_agent.errors import ContractError
from fastapi.testclient import TestClient
client=audit.ExperimentClient(R,directory/'provider',max_calls=40,max_output_tokens=6400,max_repairs=0)
class Transport(LocalGemmaTransport):
 def send_once(self,*,body,ticket):
  v=json.loads(body['messages'][1]['content'])['view'];phase=v.get('source_stage',v['phase']);print('MODEL_START',client.calls+1,phase,flush=True)
  result=client.chat_completions(provider_request(body),phase='product-'+str(client.calls+1)+'-'+phase,timeout_seconds=ticket['remaining_seconds']);raw=result['body_json']
  if raw.get('provider')!='Parasail' or raw.get('model')!=self.binding['model']:raise ContractError('provider binding')
  print('MODEL_DONE',client.calls,client.usage[-1]['seconds'],flush=True);return result
transport=Transport(code,R);profile=read(code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=transport.binding
principal={'user_id':'adr0680-'+args.arm+'-'+args.case,'team_id':'public-laws','authenticated':True,'document_ids':list(transport.public_scope)}
body={'question':case['question'],'document_ids':list(transport.public_scope),'public_question':True,'use_llm':True,'session_id':'adr0680-'+args.arm+'-'+args.case,'request_id':'adr0680-run001-'+args.arm+'-'+args.case}
put(directory/'profile.json',profile);put(directory/'request.json',body)
start=time.monotonic();row={'case_id':args.case,'arm':args.arm,'question':case['question'],'code_root':str(code),'source_generation':str(source),'model':client.model,'field_execution':False,'active_pointer_before':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')}
try:
 app=create_app(directory,generation,contracts_root=code,workspace_root=R,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=transport,runtime_root=directory/'runtime',memory_identity=lambda _:principal)
 from semantic_runtime.stage_runner import StageRunner
 StageRunner(app.state.pipeline).verify_profile()
 with TestClient(app) as api:
  ready=time.monotonic();row['app_setup_seconds']=ready-start
  if args.setup_only:row.update(http_status=200,setup_only=True)
  else:
   response=api.post('/v1/rag/ask',json=body);row.update(http_status=response.status_code,output=response.json(),request_seconds=time.monotonic()-ready)
except Exception as exc:
 row.update(http_status=500,error_type=type(exc).__name__,error=str(exc));(directory/'error.txt').write_text(traceback.format_exc())
finally:
 row.update(total_seconds=time.monotonic()-start,model_calls=client.calls,usage=client.usage,active_pointer_after=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'));put(directory/'result.json',row)
 print('RESULT',json.dumps({k:v for k,v in row.items() if k not in ('output','usage')},ensure_ascii=False),flush=True)
