"""Sequential real model through the frozen native API; no injected decisions."""
from common import *
import time,traceback,resource,importlib,ast,re,base64
from copy import deepcopy
case_id,arm=sys.argv[1:3];preflight='--preflight' in sys.argv
assert arm in ('baseline','guided')
case=next(c for c in read(DES/'live-cases.json') if c['id']==case_id)
candidate=read(DES/('candidate-baseline.json' if arm=='baseline' else 'candidate-selected.json'));C=ROOT/candidate['code_root']
assert all(sha(C/n)==h for n,h in candidate['selected_files'].items())
for p,h in read(DES/'freeze-live.json')['files'].items():assert sha(ROOT/p)==h,p
assert not (ART/'STOP_EXTERNAL.json').exists()
base=ART/('public-ready' if preflight else 'public-live')/(case_id+'-'+arm);base.mkdir(parents=True,exist_ok=False)
runtime=base/'runtime';os.environ.update(GENOS_RUNTIME_DIR=str(runtime),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',LAWRAG_WORKSPACE_ROOT=str(ROOT),OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',PYTHONDONTWRITEBYTECODE='1')
for k in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_ONTOLOGY_CONFIG','GENOS_RAG_ONTOLOGY_ENABLED','TEAM_ID','AD_WORKSPACE','GENOS_STATE_DIR','GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR'):os.environ.pop(k,None)
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(ROOT/'02_BACKEND')]
import lawrag;lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
from semantic_runtime.app import create_app
from semantic_runtime.provider import Haiku
from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport,provider_request
from semantic_runtime.legal_agent import gateway,errors
from semantic_runtime import team_scope
from lawrag.research.experiment_client import ExperimentClient
from lawrag.research.openrouter_legal_adapter import send_reserved
from lawrag.core import request_deadline
from fastapi.testclient import TestClient
from resource_guard import Guard
guard=Guard(base);guard.start()
calls=[];generations=[];active=[];app=None;client=None;results=[];current_body={}
def gz(p,v):write_raw_json(p,v)
try:
 data=ROOT/read(DES/'baseline.json')['release']['data_path'];metadata=read(data/'manifest.json')
 assert sha(data/'store.sqlite')==metadata['store_sha256']
 profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');t=LocalQwen38Transport(C,ROOT)
 assert t.provider_policy==read(DES/'provider-policy.json')
 allowed=set(case['document_ids']) & set(t.public_scope)
 profile.update(model_binding=t.binding,max_output_tokens=None)
 audited=ExperimentClient(ROOT,base/'experiment-client',max_calls=40,max_repairs=0,provider_policy=DES/'provider-policy.json')
 def send(*,body,ticket):
  assert not preflight
  if (ART/'STOP_EXTERNAL.json').exists():raise errors.ContractError('Previous UNKNOWN; all sends stopped')
  return send_reserved(audited,body=body,ticket=ticket,phase=active[-1] if active else 'request',error_module=errors,request_encoder=provider_request)
 t.send_once=send
 original_post=request_deadline.post_json
 def post(url,**kwargs):
  guard.check()
  allcalls=[c for p in (ART/'public-live').glob('*/calls.json') for c in read(p)]
  if len(allcalls)>=40 or sum((c.get('usage') or {}).get('cost',0) for c in allcalls)>=2:raise errors.BudgetExhausted('Frozen global experiment budget')
  if (ART/'STOP_EXTERNAL.json').exists():raise errors.ContractError('Previous UNKNOWN')
  payload=kwargs['json_body'];assert payload['model']=='qwen/qwen3.8-27b' and payload['reasoning']=={'effort':'none'}
  assert not any(k in payload for k in ('max_tokens','max_output_tokens','max_completion_tokens'))
  n=len(calls)+1;out=base/'raw'/f'call-{n:03d}';out.mkdir(parents=True,exist_ok=False)
  row={'number':n,'case_id':case_id,'arm':arm,'turn':current_body.get('request_id'),'stage':active[-1] if active else None,'status':'started','provider':payload['provider']}
  calls.append(row);put(base/'calls.json',calls);gz(out/'request.json.gz',payload);begin=time.monotonic()
  print('MODEL',case_id,arm,n,row['stage'],flush=True)
  try:
   response=original_post(url,**kwargs)
   try:value=response.json()
   except ValueError:value={'non_json':response.text}
   gz(out/'response.json.gz',value)
   row.update(status='unknown' if response.status_code>=500 else 'responded',http_status=response.status_code,usage=value.get('usage'),actual_provider=value.get('provider'),actual_model=value.get('model'),transport_diagnostics=response.extensions.get('absolute_deadline',{}))
   if row['status']=='unknown':put(ART/'STOP_EXTERNAL.json',{'cell':base.name,'call':n,'reason':'remote5xx'})
   return response
  except Exception as exc:
   row.update(status='unknown',error_type=type(exc).__name__,transport_diagnostics=getattr(exc,'diagnostics',{}))
   if hasattr(exc,'partial_body'):gz(out/'partial.json.gz',{'body_base64':base64.b64encode(exc.partial_body).decode(),'diagnostics':getattr(exc,'diagnostics',{})})
   put(ART/'STOP_EXTERNAL.json',{'cell':base.name,'call':n,'reason':'unknown physical outcome'});raise
  finally:row['seconds']=time.monotonic()-begin;put(out/'finished.json',row);put(base/'calls.json',calls)
 request_deadline.post_json=post
 original_generate=gateway.ModelGateway.generate
 def generate(self,phase,view,schema_name,**kwargs):
  n=len(generations)+1;stage=view.get('source_stage',phase);row={'number':n,'stage':stage};generations.append(row);active.append(stage)
  gz(base/'canonical'/f'{n:03d}.json.gz',{'phase':phase,'view':view,'schema':self.protocol.schema(schema_name)})
  try:
   value=original_generate(self,phase,view,schema_name,**kwargs);gz(base/'canonical'/f'{n:03d}-output.json.gz',value);row['status']='accepted';return value
  except Exception as exc:row.update(status='rejected',error_type=type(exc).__name__,error=str(exc));raise
  finally:active.pop();put(base/'generations.json',generations)
 gateway.ModelGateway.generate=generate
 app=create_app(runtime,data,contracts_root=C,provider=Haiku(C,runtime/'provider',False,backend='source-only',trust_zone='internal'),
  implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=t,workspace_root=ROOT,runtime_root=runtime,
  memory_identity=lambda _:{'user_id':'adr1411','team_id':'financial_team','document_ids':sorted(allowed)})
 allowed &= set(team_scope.select_documents(app.state.pipeline.store,'financial_team'));assert allowed
 client=TestClient(app,raise_server_exceptions=False);client.__enter__();assert client.get('/health').status_code==200
 from semantic_runtime.chat_adapter import views
 ui=views()
 tree=ast.parse((C/'service.py').read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_normalize')
 globals_={'Any':object,'re':re,'os':os};exec(compile(ast.Module(body=[node],type_ignores=[]),str(C/'service.py'),'exec'),globals_)
 def request(step):
  raw=ui._request_body(step['question'],{'applied_fields':{'mode':'외규'},'team_id':'financial_team','session_id':'adr1411-'+case_id+'-'+arm+('-reuse' if step.get('new_session') else ''),'request_id':'adr1411-'+case_id+'-'+arm+'-'+str(step['number']),'document_ids':sorted(allowed),'memory':True,'public_question':True,'use_llm':True})
  raw['public_question']=True;return globals_['_normalize'](raw)['json']
 put(base/'binding.json',{'code_root':str(C),'scope':sorted(allowed),'profile':profile,'source':metadata,'source_storage':'selected local SQLite','state_storage':'isolated SQLite','arm':arm,'case_id':case_id,'native_API':True})
 if preflight:
  body=request(case['steps'][0]);t.authorize({'question':body['question'],'scope':{'document_version_ids':sorted(allowed)}},body,metadata,public_question=True)
  put(base/'result.json',{'ready':True,'model_calls':0,'scope_documents':len(allowed)});print('PREFLIGHT_READY',case_id,arm,flush=True)
 else:
  for step in case['steps']:
   if (ART/'STOP_EXTERNAL.json').exists():break
   if step.get('requires_resolved') and (not results or results[-1].get('needs_guidance') or not results[-1].get('claims')):break
   if step.get('requires_saved_knowledge') and (not results or not results[-1].get('knowledge_id')):break
   current_body=request(step);turn=base/f"turn-{step['number']}";turn.mkdir();put(turn/'request.json',current_body)
   begin=time.monotonic();r=client.post('/v1/rag/ask',json=deepcopy(current_body));elapsed=time.monotonic()-begin
   value=r.json();gz(turn/'response.json.gz',{'http_status':r.status_code,'body':value})
   answer=value.get('answer') or {};reply=value.get('assembly',{}).get('term_agent',{}).get('guided_reply',{})
   text=answer.get('text','') if isinstance(answer,dict) else str(answer);(turn/'answer.txt').write_text(text+'\n')
   result={'step':step['number'],'http_status':r.status_code,'seconds':elapsed,'physical_calls':len(calls),'status':value.get('status'),'goal_id':value.get('goal_id'),'revision':value.get('revision'),'knowledge_id':value.get('knowledge_id'),'needs_guidance':reply.get('needs_guidance'),'claims':len(answer.get('claims',[])) if isinstance(answer,dict) else 0,'executed':value.get('executed')}
   if r.status_code==200:
    before=len(calls);again=client.post('/v1/rag/ask',json=deepcopy(current_body));result['duplicate']={'same_answer':again.json().get('answer')==value.get('answer'),'extra_calls':len(calls)-before}
    assert result['duplicate']['same_answer'] and result['duplicate']['extra_calls']==0
   results.append(result);put(turn/'result.json',result);put(base/'result.json',{'case_id':case_id,'arm':arm,'turns':results,'physical_calls':len(calls),'unknown':sum(x['status']=='unknown' for x in calls)})
   print('TURN',json.dumps(result,ensure_ascii=False),flush=True)
   if r.status_code!=200:break
except Exception as exc:
 put(base/'runner-failure.json',{'type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc(),'calls':len(calls)});raise
finally:
 if client:client.__exit__(None,None,None)
 if app:app.state.pipeline.store.close()
 guard.done.set();guard.thread.join(2)
 put(base/'resource-final.json',{'sample':guard.check(),'peak_rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'code_unchanged':all(sha(C/n)==h for n,h in candidate['selected_files'].items()),'oracle_driver_loaded':'oracledb' in sys.modules})
