import importlib.util,json,os,sys,copy
from pathlib import Path
import httpx,pytest
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1190-parasail-primary-routing';D=A/'artifacts/design'
C=Path(os.environ['WORKFLOW_TEST_CODE_ROOT']);path=R/'02_BACKEND/lawrag/research/experiment_client.py'
spec=importlib.util.spec_from_file_location('provider_candidate',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
BODY={'model':'qwen/qwen3.8-27b','messages':[{'role':'user','content':'synthetic test'}],'stream':False,'max_tokens':100}
SCHEMA={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}
def policy(tmp_path):
 p=tmp_path/'policy.json';p.write_text((C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json').read_text());return p

def make(tmp_path,monkeypatch,handler,**kwargs):
 monkeypatch.setenv('OPEN_ROUTER','synthetic-test-key')
 return mod.ExperimentClient(R,tmp_path/'raw',transport=httpx.MockTransport(handler),provider_policy=policy(tmp_path),max_calls=kwargs.get('max_calls',4),max_repairs=0)

def answer(provider='Parasail',model=BODY['model'],reasoning=0,content='{"ok":true}'):
 return httpx.Response(200,json={'model':model,'provider':provider,'choices':[{'finish_reason':'stop','message':{'content':content}}],'usage':{'prompt_tokens':1,'completion_tokens':1,'completion_tokens_details':{'reasoning_tokens':reasoning}}})

def test_known429_switches_once_and_retains_budget_and_payload(tmp_path,monkeypatch):
 seen=[]
 def handler(req):
  d=json.loads(req.content);seen.append(d)
  return httpx.Response(429,json={'error':{'code':429}}) if len(seen)==1 else answer('Near AI')
 c=make(tmp_path,monkeypatch,handler);raw=c.chat_completions(BODY)
 assert raw['status_code']==200 and c.calls==2
 assert [v['provider']['only'] for v in seen]==[['parasail/fp8'],['near-ai/fp8']]
 assert all(v['model']==BODY['model'] and v['messages']==BODY['messages'] and v['reasoning']=={'effort':'none'} and 'max_tokens' not in v and v['provider']['allow_fallbacks'] is False for v in seen)
 c.chat_completions(BODY);assert c.calls==3 and len(c.provider_switches)==1

@pytest.mark.parametrize('status',[400,401,403,408,500,502,503])
def test_other_http_no_switch(tmp_path,monkeypatch,status):
 c=make(tmp_path,monkeypatch,lambda r:httpx.Response(status,json={'error':{'code':status}}))
 with pytest.raises(mod.ExperimentProviderError):c.chat_completions(BODY)
 assert c.calls==1 and not c.provider_switches

def test_unknown_timeout_no_switch(tmp_path,monkeypatch):
 def h(req):raise httpx.ReadTimeout('synthetic',request=req)
 c=make(tmp_path,monkeypatch,h)
 with pytest.raises(mod.ExperimentTransportError) as e:c.chat_completions(BODY)
 assert e.value.unknown and c.calls==1 and not c.provider_switches

@pytest.mark.parametrize('damage',['provider','model','thinking','format'])
def test_response_violation_no_switch(tmp_path,monkeypatch,damage):
 kw={'provider':'Chutes'} if damage=='provider' else {'model':'other-model'} if damage=='model' else {'reasoning':1} if damage=='thinking' else {'content':'bad'}
 c=make(tmp_path,monkeypatch,lambda r:answer(**kw))
 with pytest.raises(mod.ExperimentCallError):c.generate('synthetic',{},SCHEMA)
 assert c.calls==1 and not c.provider_switches

def test_no_reset_when_provider_budget_exhausted(tmp_path,monkeypatch):
 c=make(tmp_path,monkeypatch,lambda r:httpx.Response(429,json={'error':{'code':429}}),max_calls=1)
 with pytest.raises(mod.ExperimentProviderError):c.chat_completions(BODY)
 assert c.calls==1 and not c.provider_switches

def test_second429_no_third_provider_or_retry(tmp_path,monkeypatch):
 c=make(tmp_path,monkeypatch,lambda r:httpx.Response(429,json={'error':{'code':429}}))
 with pytest.raises(mod.ExperimentProviderError):c.chat_completions(BODY)
 assert c.calls==2 and len(c.provider_switches)==1

@pytest.mark.parametrize('damage',['model','fp4','auth','status','switches','duplicate'])
def test_invalid_scope_rejected_before_request(tmp_path,monkeypatch,damage):
 monkeypatch.setenv('OPEN_ROUTER','test-credential-never-in-content');p=policy(tmp_path);d=json.loads(p.read_text())
 if damage=='model':d['model']='wrong'
 if damage=='fp4':d['providers'][0]['tag']='chutes/fp4'
 if damage=='auth':d['authorization']['text']=''
 if damage=='status':d['switch_http_status']=[500]
 if damage=='switches':d['max_provider_switches']=10
 if damage=='duplicate':d['providers'][1]=d['providers'][0]
 p.write_text(json.dumps(d))
 with pytest.raises(ValueError):mod.ExperimentClient(R,tmp_path/'raw',provider_policy=p)

def test_policy_mutation_rejected_before_request(tmp_path,monkeypatch):
 c=make(tmp_path,monkeypatch,lambda r:answer());c.provider_policy_path.write_text('{}')
 with pytest.raises(mod.ExperimentCallError):c.chat_completions(BODY)
 assert c.calls==0

def test_generate_uses_same429_route(tmp_path,monkeypatch):
 seen=[]
 def h(req):
  seen.append(req);return httpx.Response(429,json={'error':{'code':429}}) if len(seen)==1 else answer('Near AI')
 c=make(tmp_path,monkeypatch,h);assert c.generate('synthetic',{},SCHEMA)=={'ok':True};assert c.calls==2

def test_no_override_keeps_original_policy(tmp_path,monkeypatch):
 monkeypatch.setenv('OPEN_ROUTER','test-credential-never-in-content');root=tmp_path/'workspace';(root/'00_SYSTEM').mkdir(parents=True);(root/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').write_text((R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').read_text());c=mod.ExperimentClient(root,tmp_path/'raw',transport=httpx.MockTransport(lambda r:answer('Parasail')))
 assert c.provider_policy is None
 c.chat_completions(BODY);assert c.calls==1 and c.proxy['provider_routing']['only']==['parasail/fp8']


def test_workspace_default_loads_verified_provider_policy(tmp_path,monkeypatch):
 monkeypatch.setenv('OPEN_ROUTER','test-credential-never-in-content')
 root=tmp_path/'workspace';(root/'00_SYSTEM').mkdir(parents=True)
 (root/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').write_text((R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').read_text())
 (root/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json').write_text((C/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json').read_text())
 c=mod.ExperimentClient(root,tmp_path/'raw',transport=httpx.MockTransport(lambda r:answer('Parasail')))
 c.chat_completions(BODY);assert c.calls==1 and c.proxy['provider_routing']['only']==['parasail/fp8']
