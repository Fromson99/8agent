"""Known failing public question through the actual service/API path, sequential."""
from common import *
from stop_policy import StopPolicy, RunStopped, terminal_failure
import os,sys,resource,asyncio,importlib.util,time,traceback
sys.dont_write_bytecode=True
arm=sys.argv[1];assert arm in ('candidate','control');s=read(ART/'stage.json');C=ROOT/s['roots'][arm];out=ART/'known-query'/arm;out.mkdir(parents=True,exist_ok=False)
f=read(ART/'design-freeze.json');assert all(sha(C/n)==h for n,h in f['files'][arm].items())
assert sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py') == f['client_sha256']
assert int(Path('/proc/meminfo').read_text().split('MemAvailable:')[1].split()[0])>4*1024**2
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
os.environ.update(GENOS_RUNTIME_DIR=str(out/'runtime'),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1',LAWRAG_WORKSPACE_ROOT=str(ROOT))
for k in ('TEAM_ID','AD_WORKSPACE','DP'):os.environ.pop(k,None)
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient,ExperimentProviderError,ExperimentFormatError,ExperimentTransportError
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport,provider_request
from semantic_runtime.legal_agent.errors import TransportError,ProposalError
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.workflow_tiers_policy import profile as normalize_profile
client=ExperimentClient(ROOT,out/'model',max_calls=14)
stop=StopPolicy(ART/'stop.json',14)
class Audited(LocalGemmaTransport):
 def send_once(self,*,body,ticket):
  try:stop.before_call(client.calls)
  except RunStopped as exc:raise TransportError(str(exc),retryable=False,unknown=False) from exc
  payload=provider_request(body)
  view=json.loads(next(x['content'] for x in body['messages'] if x['role']=='user')).get('view',{})
  event={'call':client.calls+1,'phase':view.get('source_stage',view.get('phase')),'max_output_tokens':payload.get('max_tokens'),'started_at':time.time()}
  print('CALL_START',event['call'],event['phase'],flush=True)
  call_start=time.monotonic()
  try:
   response=client.chat_completions(payload,phase='service',timeout_seconds=ticket['remaining_seconds'])
   event['status']='returned'
   return response
  except ExperimentTransportError as exc:
   event['status']='transport_error'
   stop.stop('TRANSPORT_FAILURE',client.calls)
   raise TransportError(str(exc),retryable=False,unknown=exc.unknown) from exc
  except ExperimentProviderError as exc:
   event['status']='provider_error'
   stop.stop('PROVIDER_FAILURE',client.calls,(exc.response or {}).get('status_code'))
   raise TransportError(str(exc),retryable=False,unknown=False,response=exc.response) from exc
  except ExperimentFormatError as exc:
   event['status']='format_error'
   error=ProposalError(str(exc));error.response=exc.response;raise error from exc
  finally:
   event['seconds']=time.monotonic()-call_start
   with (out/'physical-calls.jsonl').open('a') as stream:stream.write(json.dumps(event,ensure_ascii=False)+'\n')
   print('CALL_END',event['call'],event.get('status','error'),round(event['seconds'],3),flush=True)
from trace import install
install(out)
transport=Audited(C,ROOT);profile=normalize_profile({**read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),'model_binding':transport.binding,'max_output_tokens':transport.policy['max_output_tokens'],'max_model_attempts':14,'max_transport_retries':0,'wall_seconds':1800},require_model=True)
# Keep current working navigation policy identical in both arms.
app=create_app(ROOT,ROOT/s['base_release']['data_path'],contracts_root=C,workspace_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',runtime_root=out/'runtime',legal_agent_profile=profile,legal_agent_transport=transport,release={'mode':'local-release','release_id':'scope-first-1024-'+arm})
spec=importlib.util.spec_from_file_location('qualification_service',C/'service.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod._APP=app;mod._BINDING={'mode':'local-release','code_root':str(C)}
save(out/'effective-profile.json',profile)
save(out/'execution-binding.json',{'release_id':s['base_release']['release_id'],'code_root':str(C),'data_path':s['base_release']['data_path'],'data_manifest_sha256':s['base_release']['data_manifest_sha256'],'app_module':sys.modules['semantic_runtime.app'].__file__,'entry_module':importlib.util.find_spec('semantic_runtime.legal_agent.request_entry').origin,'frozen_files_exact':all(sha(C/n)==h for n,h in f['files'][arm].items()),'transport_retries':0})
assert sha(ART/'known-request.json')==f['request_sha256']
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
request=read(ART/'known-request.json');save(out/'request.json',request)
start=time.monotonic();result={'code_root':str(C.relative_to(ROOT)),'known_in_sample':True,'model_policy':'qwen38-experiments-v1','error':None}
try:
 response=asyncio.run(mod.service({},request));save(out/'response.json',response);result['service_status']=response.get('status')
except Exception as exc:result['error']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
finally:
 result.update(seconds=time.monotonic()-start,model_calls=client.calls,usage=client.usage,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
 save(out/'result.json',result);app.state.pipeline.store.close()
print(json.dumps({k:v for k,v in result.items() if k!='usage'},ensure_ascii=False),flush=True)

failure=terminal_failure(result,read(stop.path) if stop.path.exists() else None)
if failure:
 # A native bounded/semantic failure is a recorded case result, not a provider retry.
 # Persisted provider/transport failures stop all later paired probes.
 if stop.path.exists():raise SystemExit(2)
 if result.get('error'):raise SystemExit(3)
