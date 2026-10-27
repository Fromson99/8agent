"""Tiny native-versus-audit incomplete response check; no service/data/network."""
from pathlib import Path
from types import SimpleNamespace
import ast,copy,gzip,json,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[3]
CODE=ROOT/'08_DEPLOYMENT/RELEASES/navigation-validation-20261027-r1/code'
sys.dont_write_bytecode=True;sys.path.insert(0,str(CODE/'02_BACKEND'))
from semantic_runtime.legal_agent import local_gemma as local,errors
from semantic_runtime.legal_agent.model_contract import structured_content
import httpx,jsonschema
# Import the common client after binding the selected native modules.
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentFormatError,ExperimentProviderError,ExperimentTransportError
source=ast.parse(Path(__file__).with_name('live.py').read_text())
node=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='send_once')
model='qwen/qwen3.8-27b';profile=json.loads((CODE/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').read_text())
transport=local.LocalGemmaTransport.__new__(local.LocalGemmaTransport);transport.binding={'model':model};transport.policy=profile;transport._key='synthetic-no-network'
body={'model':model,'stream':False,'messages':[{'role':'user','content':'contract fixture'}],
      'response_format':{'type':'json_schema','json_schema':{'name':'check','strict':True,'schema':{'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}}}}
class FixtureClient:
 calls=0
 def __init__(self,data):self.data=data
 def chat_completions(self,*a,**kw):
  raise ExperimentFormatError('fixture incomplete',response={'status_code':200,'body_json':self.data,'body_text':None,'body_sha256':'fixture'})
def outcome(call):
 try:call();return {'type':'success'}
 except Exception as e:
  return {'type':type(e).__name__,'message':str(e),'code':getattr(e,'code',None),'can_increase_output':getattr(e,'can_increase_output',None)}
base={'model':model,'provider':'Parasail','choices':[{'finish_reason':'length','message':{'content':'{'}}],'usage':{'completion_tokens_details':{'reasoning_tokens':0}}}
cases=[]
for finish in ['length','content_filter','refusal','other']:
 value=copy.deepcopy(base);value['choices'][0]['finish_reason']=finish;cases.append((finish,value))
value=copy.deepcopy(base);value['choices']=[];cases.append(('no-choice',value))
value=copy.deepcopy(base);value['choices']*=2;cases.append(('multiple-choices',value))
real_client=httpx.Client;results=[]
with tempfile.TemporaryDirectory(prefix='adr1075-transport-') as temporary:
 for label,data in cases:
  local.httpx.Client=lambda **kw:real_client(**kw,transport=httpx.MockTransport(lambda request:httpx.Response(200,json=data)))
  try:native=outcome(lambda:transport.send_once(body=body,ticket={'remaining_seconds':1}))
  finally:local.httpx.Client=real_client
  current={'client':FixtureClient(data),'out':Path(temporary),'active':[],'calls':[],'case':{'id':'synthetic'}}
  env={'check_resources':lambda:None,'t':transport,'errors':errors,'sha':lambda p:'fixture','pointer':None,'f':{'pointer_sha256':'fixture'},'current':current,'json':json,'local':local,'jsonschema':jsonschema,'put':lambda *a:None,'gz':lambda *a:None,'find_stage':lambda x:None,'time':time,'structured_content':structured_content,'ExperimentFormatError':ExperimentFormatError,'ExperimentProviderError':ExperimentProviderError,'ExperimentTransportError':ExperimentTransportError}
  exec(compile(ast.Module(body=[node],type_ignores=[]),str(Path(__file__)),'exec'),env)
  audited=outcome(lambda:env['send_once'](body=body,ticket={'remaining_seconds':1}))
  assert native==audited,(label,native,audited)
  results.append({'fixture':label,'native':native,'audited':audited,'equal':True})
print(json.dumps({'passed':all(r['equal'] for r in results),'fixtures':results,'real_model_calls':0,'network_calls':0,'selected_output_cap':profile['max_output_tokens']},ensure_ascii=False,indent=2))
