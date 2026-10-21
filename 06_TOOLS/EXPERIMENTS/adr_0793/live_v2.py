"""One known public case through the frozen actual HTTP API; no gold passed."""
from pathlib import Path
import hashlib,json,os,sys,time,traceback
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0793-definition-entry-navigation';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'probe-freeze.json');C=R/f['code_roots']['connected'];case=read(D/'criteria.json')['live']
O=A/'artifacts/live';O.mkdir(parents=True,exist_ok=False)
assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in f['files'].items())
sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(R/'02_BACKEND')]
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(R),AD_WORKER_ENABLED='0')
import lawrag
lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport,provider_request
from semantic_runtime.legal_agent.errors import ContractError,TransportError
from semantic_runtime.legal_agent.model_contract import structured_content
from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,ExperimentProviderError,ExperimentTransportError
class ExperimentTransport(LocalGemmaTransport):
 def __init__(self):
  super().__init__(C,R);self.client=ExperimentClient(R,O/'raw',max_calls=case['max_calls'],max_output_tokens=6400,max_repairs=0)
 def send_once(self,*,body,ticket):
  try:raw=self.client.chat_completions(provider_request(body),phase='definition-entry-public',timeout_seconds=min(180,ticket['remaining_seconds']))
  except ExperimentFormatError as exc:
   if exc.response:
    try:structured_content(exc.response['body_json'],require_complete=True)
    except Exception as error:error.response=exc.response;raise
   raise
  except ExperimentProviderError as exc:
   status=(exc.response or {}).get('status_code',0)
   raise TransportError('experiment provider failure',retryable=status==429,unknown=status>=500,response=exc.response) from exc
  except ExperimentTransportError as exc:raise TransportError('experiment outcome unknown',unknown=True) from exc
  if raw['body_json'].get('model')!=self.binding['model'] or raw['body_json'].get('provider')!='Parasail':raise ContractError('actual model/provider mismatch')
  raw['acceptance']='ACCEPTED';return raw
from semantic_runtime.app import create_app
from fastapi.testclient import TestClient
t=ExperimentTransport();profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=t.binding;profile['wall_seconds']=case['max_seconds'];data=read(D/'data-binding.json')
app=create_app(R,R/data['path'],contracts_root=C,workspace_root=R,provider=object(),implementation='legal-agent-unified-v6',runtime_root=O/'runtime',legal_agent_profile=profile,legal_agent_transport=t)
started=time.monotonic();result={'case':case,'code_root':str(C.relative_to(R)),'in_sample':True,'quality_certified':False}
print('Known public case started',flush=True)
try:
 client=TestClient(app)
 response=client.post('/v1/rag/ask',json={'question':case['question'],'document_ids':sorted(t.public_scope),'public_question':True,'use_llm':True})
 put(O/'response.json',response.json());result.update(http_status=response.status_code)
except Exception as exc:
 result.update(error=type(exc).__name__,message=str(exc));(O/'error.txt').write_text(traceback.format_exc())
finally:
 result.update(model_calls=t.client.calls,model_usage=t.client.usage,elapsed_seconds=time.monotonic()-started)
 put(O/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('case','model_usage')},ensure_ascii=False),flush=True);app.state.pipeline.store.close()
