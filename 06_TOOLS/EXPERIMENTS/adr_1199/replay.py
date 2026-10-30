"""Fresh native HTTP run with four stored1198 responses; no external calls.

Stop at the first new model decision, retaining the recovered investigation I/O.
This is a known-case control-flow diagnostic, not a new CM007 answer test.
"""
from common import *
import asyncio,os,resource,time,importlib
from copy import deepcopy
from types import SimpleNamespace
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
f=read(DES/'freeze-rev-001.json');baseline=read(DES/'baseline.json');C=ROOT/f['code_root']
for n,h in f['files'].items():assert sha(C/n)==h,n
pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
assert sha(pointer)==baseline['pointer_sha256']
base=ART/'saved1198-replay';base.mkdir(exist_ok=False);runtime=base/'runtime'
os.environ.update(GENOS_RUNTIME_DIR=str(runtime),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1',LAWRAG_WORKSPACE_ROOT=str(ROOT))
for n in ('TEAM_ID','AD_WORKSPACE'):os.environ.pop(n,None)
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(ROOT)]
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport
from semantic_runtime.legal_agent.workflow_tiers_policy import profile as check_profile
from semantic_runtime.legal_agent import gateway,law_navigation,investigation_supervisor as su,errors
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
from fastapi.testclient import TestClient
from lawrag.core import request_deadline
def forbidden_network(*a,**k):raise AssertionError('No network is permitted in saved-response replay')
request_deadline.post_json=forbidden_network
t=LocalQwen38Transport(C,ROOT)
profile=check_profile({**read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),'model_binding':t.binding,'max_output_tokens':t.policy['max_output_tokens']},require_model=True)
release=baseline['manifest'];case=next(c for c in read(DES/'cases.json') if c['id']=='cm-007')
binding={'mode':'isolated-replay','code_root':str(C),'data_path':release['data_path'],'candidate':f['candidate_revision']}
app=create_app(runtime,ROOT/release['data_path'],contracts_root=C,release=binding,provider=object(),vector=False,implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=t,workspace_root=ROOT,runtime_root=runtime)
from cm_authorization import install
auth=install(t,'semantic_runtime.legal_agent',{'inputs':{str((DES/n).relative_to(ROOT)):sha(DES/n) for n in ('authorization.json','corpus.json')}},case,baseline)
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1198-main117-live-cm007/artifacts/live/cm-007'
active={};frames=[];returned=[];recovered=[];mapping={}
old_decision=law_navigation.Investigation.request_decision
def decision(inv,data,actions,phase):
 active.update(inv=inv,data=data,actions=actions)
 return old_decision(inv,data,actions,phase)
law_navigation.Investigation.request_decision=decision
old_recover=su.recover_changed_route
def recover(*args,**kw):
 result=old_recover(*args,**kw)
 recovered.append({'authorized':result,'next_action':args[-1]['next_action'],'decision':deepcopy(args[-1]),'response_hash':su.digest(args[-3])})
 return result
su.recover_changed_route=recover
old_generate=gateway.ModelGateway.generate
class ReplayBoundary(BaseException):pass
def generate(self,phase,view,schema_name,**kw):
 n=len(frames)+1;stage=view.get('source_stage',phase)
 frames.append({'number':n,'stage':stage});active.update(number=n,view=view,stage=stage)
 if n>4:raise ReplayBoundary('First new decision after stored supervisor response')
 return old_generate(self,phase,view,schema_name,**kw)
gateway.ModelGateway.generate=generate
def send(*,body,ticket):
 n=active['number'];old=read(parent/'canonical'/f'{n:03d}.json.gz')
 assert active['stage']==old['view'].get('source_stage',old['phase']), (active['stage'],old['phase'])
 saved=read(parent/'canonical'/f'{n:03d}-output.json.gz')
 for before in old['view'].get('read_judgments',{}).get('current_originals',[]):
  matches=[r for r in active['view'].get('read_judgments',{}).get('current_originals',[]) if (r['source_id'],r['document_id'],r['material'])==(before['source_id'],before['document_id'],before['material'])]
  if len(matches)==1:mapping[before['id']]=matches[0]['id']
 refs=NavigationReferences(active['view']);restored=refs._map(saved,mapping)
 wire=refs.view(restored) if active['view'].get('input_projection')=='compact-selection-source-v3' else restored
 physical={1:1,2:3,3:4,4:5}[n]
 raw=read(parent/'raw'/f'call-{physical:03d}'/'response.json.gz')
 raw['choices'][0]['message']['content']=json.dumps(wire,ensure_ascii=False)
 returned.append({'number':n,'stage':active['stage'],'stored_output':bind(parent/'canonical'/f'{n:03d}-output.json.gz'),'native_output_hash':su.digest(restored)})
 return {'status_code':200,'body_json':raw,'acceptance':'ACCEPTED','body_text':None,'retry_after':None}
t.send_once=send
start=time.monotonic();boundary=False;failure=None
try:
 with TestClient(app) as client:
  assert client.get('/health').status_code==200
  async def service(_env,req):
   r=client.post('/v1/rag/ask',json=req['json']);return {'status':r.status_code,'body':r.json()}
  response=asyncio.run(auth(service,deepcopy(case['request'])))
  failure={'unexpected_http_return':response['status']}
except BaseException as exc:
 def contains(e):return isinstance(e,ReplayBoundary) or any(contains(c) for c in getattr(e,'exceptions',[]))
 boundary=contains(exc)
 if not boundary:failure={'type':type(exc).__name__,'message':str(exc)}
finally:
 state=active.get('inv').p if active.get('inv') else {}
 ref=write_raw_json(base/'final-state.json.gz',state)
 put(base/'result.json',{'boundary_reached':boundary,'failure':failure,'frames':frames,'stored_responses':returned,
     'recoveries':recovered,'new_model_calls':0,'network_calls':0,'seconds':time.monotonic()-start,
     'final_state':ref,'main117_unchanged':sha(pointer)==baseline['pointer_sha256'],
     'scope':'Saved response control-flow replay; stops before new model selection. Not a completed legal answer or proof that bylaw15 has been read.'})
 app.state.pipeline.store.close()
print(json.dumps({'boundary':boundary,'failure':failure,'returned':len(returned),'recovered':recovered,'next_stage':frames[-1] if frames else None},ensure_ascii=False))
assert boundary and failure is None and len(returned)==4 and len(recovered)==1 and recovered[0]['authorized']
assert recovered[0]['next_action']=='RESEARCH'
