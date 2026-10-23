"""Known failing public question through the actual service/API path, sequential."""
from common import *
from stop_policy import StopPolicy, RunStopped, terminal_failure
import os,sys,resource,asyncio,importlib.util,time,traceback
sys.dont_write_bytecode=True
arm='candidate';s=read(ART/'stage.json');C=ROOT/s['roots'][arm];out=ART/'known-query'/arm;out.mkdir(parents=True,exist_ok=False)
f=read(ART/'design-freeze.json');assert all(sha(C/n)==h for n,h in f['files'][arm].items())
assert int(Path('/proc/meminfo').read_text().split('MemAvailable:')[1].split()[0])>3*1024**2
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
client=ExperimentClient(ROOT,out/'model',max_calls=8)
stop=StopPolicy(ART/'stop.json',8)
class Audited(LocalGemmaTransport):
 def send_once(self,*,body,ticket):
  try:stop.before_call(client.calls)
  except RunStopped as exc:raise TransportError(str(exc),retryable=False,unknown=False) from exc
  payload=provider_request(body)
  try:return client.chat_completions(payload,phase='service',timeout_seconds=ticket['remaining_seconds'])
  except ExperimentTransportError as exc:
   stop.stop('TRANSPORT_FAILURE',client.calls)
   raise TransportError(str(exc),retryable=False,unknown=exc.unknown) from exc
  except ExperimentProviderError as exc:
   stop.stop('PROVIDER_FAILURE',client.calls,(exc.response or {}).get('status_code'))
   raise TransportError(str(exc),retryable=False,unknown=False,response=exc.response) from exc
  except ExperimentFormatError as exc:
   error=ProposalError(str(exc));error.response=exc.response;raise error from exc
transport=Audited(C,ROOT);profile=normalize_profile({**read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),'model_binding':transport.binding,'max_output_tokens':transport.policy['max_output_tokens'],'max_model_attempts':8,'max_transport_retries':0,'wall_seconds':480},require_model=True)
app=create_app(ROOT,ROOT/s['base_release']['data_path'],contracts_root=C,workspace_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',runtime_root=out/'runtime',legal_agent_profile=profile,legal_agent_transport=transport,release={'mode':'local-release','release_id':'bounded-recheck-0989'})
spec=importlib.util.spec_from_file_location('qualification_service',C/'service.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod._APP=app;mod._BINDING={'mode':'local-release','code_root':str(C)}
save(out/'effective-profile.json',profile)
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
 stop.stop(failure,client.calls)
 raise SystemExit(2)
