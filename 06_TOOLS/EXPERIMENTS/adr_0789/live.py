"""Frozen real-question observations using the common ExperimentClient."""
from pathlib import Path
import hashlib,json,os,sys,time,asyncio,importlib.util,traceback
from types import SimpleNamespace
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0789-risk-workflow-rag-orchestration';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');C=R/f['code_root'];case=read(D/'criteria.json')['live']['cases'][int(sys.argv[1])]
O=A/'artifacts/live'/case['id'];O.mkdir(parents=True,exist_ok=False)
for n,h in f['files'].items():assert sha(R/n)==h,n
sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(R/'02_BACKEND')]
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(R),GENOS_RUNTIME_DIR=str(O/'runtime'),AD_WORKER_ENABLED='0')
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport,provider_request
from semantic_runtime.legal_agent.errors import ContractError,TransportError
from semantic_runtime.legal_agent.model_contract import structured_content
from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,ExperimentProviderError,ExperimentTransportError
class ExperimentTransport(LocalGemmaTransport):
    def __init__(self):
        super().__init__(C,R)
        self.client=ExperimentClient(R,O/'raw',max_calls=80,max_output_tokens=6400,max_repairs=0)
    def send_once(self,*,body,ticket):
        try:raw=self.client.chat_completions(provider_request(body),phase='rag-workflow',timeout_seconds=min(180,ticket['remaining_seconds']))
        except ExperimentFormatError as exc:
            if exc.response:
                try:structured_content(exc.response['body_json'],require_complete=True)
                except Exception as error:error.response=exc.response;raise
            raise
        except ExperimentProviderError as exc:
            status=(exc.response or {}).get('status_code',0)
            raise TransportError('experiment provider failure',retryable=status==429,unknown=status>=500,response=exc.response) from exc
        except ExperimentTransportError as exc:
            raise TransportError('experiment outcome unknown',unknown=True) from exc
        if raw['body_json'].get('model')!=self.binding['model'] or raw['body_json'].get('provider')!='Parasail':
            raise ContractError('actual model/provider mismatch')
        raw['acceptance']='ACCEPTED';return raw
from semantic_runtime.app import create_app
t=ExperimentTransport();profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=t.binding
data=read(D/'data-binding.json')
app=create_app(R,R/data['path'],contracts_root=C,workspace_root=R,provider=object(),
    implementation='legal-agent-unified-v6',runtime_root=O/'runtime',legal_agent_profile=profile,
    legal_agent_transport=t,memory_identity=lambda _:dict(user_id='jin',team_id='risk_team',
        document_ids=t.grant['workflow_authorization']['document_ids']))
spec=importlib.util.spec_from_file_location('workflow_qualified_service',C/'service.py');gateway=importlib.util.module_from_spec(spec);spec.loader.exec_module(gateway)
gateway._APP=app;gateway._ad_control=lambda:SimpleNamespace(intercept=lambda *args:None,start_worker=lambda *args:None)
started=time.monotonic();result=dict(case=case,environment='WSL local, frozen full RAG and workflow',in_sample=True,
    quality_certified=False,code_root=str(C.relative_to(R)),generation_manifest_sha256=data['manifest_sha256'])
print(json.dumps({'started':case['id']}),flush=True)
try:
    response=asyncio.run(gateway.service({},dict(API_TYPE='LEGAL_AGENT',question=case['question'],
        session_id='adr0789-'+case['id'],request_id='run-001')))
    put(O/'response.json',response);value=response.get('body',{})
    result.update(http_status=response.get('status'),status=value.get('status'),run_id=value.get('run_id'),
        sides={k:{key:v.get(key) for key in ('status','run_id','continuation','evidence_ids')} for k,v in value.get('rag_results',{}).items()},
        usage=value.get('usage'),answer=value.get('answer',{}).get('text'),response_sha256=sha(O/'response.json'))
except Exception as exc:
    result.update(error=type(exc).__name__,message=str(exc));(O/'error.txt').write_text(traceback.format_exc())
finally:
    app.state.pipeline.store.close();result.update(model_calls=t.client.calls,model_usage=t.client.usage,elapsed_seconds=time.monotonic()-started)
    put(O/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('answer','model_usage')},ensure_ascii=False),flush=True)
