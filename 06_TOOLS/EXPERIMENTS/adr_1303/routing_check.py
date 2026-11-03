"""No network: exercise exact native send adapter and singleton429 policy."""
from common import *
import httpx,sqlite3,time
C=ROOT/read(DES/'candidate.json')['code_root']
from pinned_imports import install
install(ART/'transport')
import lawrag,lawrag.core,lawrag.research
for pkg,path in [(lawrag,'02_BACKEND/lawrag'),(lawrag.core,'02_BACKEND/lawrag/core'),(lawrag.research,'02_BACKEND/lawrag/research')]:
 pkg.__path__.extend([str(C/path),str(ROOT/path)])
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
from semantic_runtime.legal_agent import provider_routing as routing,errors
from semantic_runtime.legal_agent.local_gemma import provider_request
from lawrag.research.experiment_client import ExperimentClient,ExperimentProviderError
from lawrag.research.openrouter_legal_adapter import send_reserved
out=ART/'routing-selfcheck';out.mkdir(exist_ok=False)
policy=routing.validate_policy(read(DES/'nearai-only.json'));seen=[]
def mock(request):
 body=json.loads(request.content);seen.append(body)
 assert body['provider']==routing.route(policy['providers'][0])
 assert body['reasoning']=={'effort':'none'} and body['model']=='qwen/qwen3.8-27b'
 assert not any(k in body for k in ('max_tokens','max_output_tokens','max_completion_tokens'))
 return httpx.Response(200,json={'provider':'Near AI','model':body['model'],'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2,'cost':0}})
c=ExperimentClient(ROOT,out/'success',max_calls=2,max_repairs=0,provider_policy=DES/'nearai-only.json',transport=httpx.MockTransport(mock))
body={'model':c.model,'messages':[{'role':'user','content':'synthetic contract only'}],'stream':False,'provider':routing.route(policy['providers'][0]),'reasoning':{'effort':'none'}}
result=send_reserved(c,body=body,ticket={'provider_index':0,'remaining_seconds':5,'deadline':time.monotonic()+5},phase='routing_check',error_module=errors,request_encoder=provider_request)
assert result['status_code']==200 and c.calls==1 and len(seen)==1
rejected=[]
def reject(request):rejected.append(json.loads(request.content));return httpx.Response(429,json={'error':{'message':'synthetic limit'}})
c2=ExperimentClient(ROOT,out/'rejected',max_calls=4,max_repairs=0,provider_policy=DES/'nearai-only.json',transport=httpx.MockTransport(reject))
try:c2.chat_completions({k:v for k,v in body.items() if k!='provider'},phase='reject_check',timeout_seconds=5)
except ExperimentProviderError:pass
else:raise AssertionError('429 must stay failed')
assert c2.calls==1 and len(rejected)==1 and not c2.provider_switches
class Repo:
 db=sqlite3.connect(':memory:')
 def event(self,*args):raise AssertionError('No transition allowed')
r=Repo();r.db.execute('CREATE TABLE event(kind,payload_json,payload_hash,seq)')
assert routing.switch(r,policy,sha(DES/'nearai-only.json'),'binding','attempt',{'status_code':429,'acceptance':'KNOWN_REJECTED'}) is False
put(out/'result.json',{'native_single_send':True,'only_near_ai':True,'reasoning_none':True,'output_caps_absent':True,'client429_no_retry':True,'gateway429_no_switch':True,'physical_network_calls':0,'mock_sends':2})
print('NearAI singleton native send and429 no retry/switch: PASS, network0')
