from common import *
T=Path(__file__).parent
# Reuse native app/grant/bootstrap, not any research transport or nested retry.
s=(T/'replay.py').read_text();a=s.index("candidate=read(ROOT/read(DES/'candidate.json')");b=s.index("baseline=read(DES/'baseline.json')",a);s=s[:a]+s[b:]
s=s[:s.index('# Replay exact stored wire outputs')]
s=s.replace("repeat=int(sys.argv[-1]);base=ART/'baseline-replay-v5'/(case_id+'-r'+str(repeat))", "base=ART/'live'/case_id\nif (base/'dispatch.json').exists():raise RuntimeError('Live case already dispatched; no automatic repeat')")
s=s.replace("# Baseline code frozen; replay runner recorded separately.", "for name,h in f['scripts'].items():assert sha(ROOT/name)==h,name\nassert read(ART/('check-'+f['candidate_revision']['revision_id']+'.json'))['failed']==0")
s+='''
from resource_guard import Guard
guard=Guard(base);guard.start()
import httpx
original_client=httpx.Client
calls=[];generations=[];active=[];spans=[]
started=time.monotonic()
def gz(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with gzip.open(p,'wt',encoding='utf8') as output:json.dump(v,output,ensure_ascii=False,separators=(',',':'))
class RecordedClient(original_client):
 def post(self,url,**kwargs):
  guard.check()
  if not str(url).startswith(t.policy['endpoint']+'/chat/completions'):raise RuntimeError('Unexpected external endpoint')
  n=len(calls)+1;out=base/'raw'/f'call-{n:03d}';out.mkdir(parents=True,exist_ok=False)
  payload=kwargs['json'];assert payload['model']=='qwen/qwen3.8-27b'
  assert not any(k in payload for k in ('max_tokens','max_completion_tokens','max_output_tokens'))
  row={'number':n,'stage':active[-1] if active else None,'provider':payload['provider'],'status':'started'};calls.append(row)
  put(out/'request.json',payload);put(base/'calls.json',calls)
  print('MODEL',case_id,n,row['stage'],payload['provider']['only'],flush=True);begin=time.monotonic()
  try:
   response=super().post(url,**kwargs)
   try:raw=response.json()
   except ValueError:raw={'non_json_body':response.text}
   put(out/'response.json',raw);row.update(status='responded',http_status=response.status_code,usage=raw.get('usage'),actual_provider=raw.get('provider'))
   return response
  except httpx.HTTPError as exc:row.update(status='unknown',error_type=type(exc).__name__);raise
  finally:row['seconds']=time.monotonic()-begin;put(base/'calls.json',calls)
httpx.Client=RecordedClient
original_generate=gateway.ModelGateway.generate
from semantic_runtime.legal_agent import law_navigation
old_decision=law_navigation.Investigation.request_decision
def decision(inv,data,actions,phase):
 try:return old_decision(inv,data,actions,phase)
 finally:put(base/'investigation-state.json',inv.p)
law_navigation.Investigation.request_decision=decision
def generate(self,phase,view,schema_name,**kwargs):
 number=len(generations)+1;stage=view.get('source_stage',phase);row={'number':number,'stage':stage};generations.append(row);active.append(stage)
 gz(base/'canonical'/f'{number:03d}.json.gz',{'phase':phase,'view':view,'schema':self.protocol.schema(schema_name)})
 try:
  value=original_generate(self,phase,view,schema_name,**kwargs);gz(base/'canonical'/f'{number:03d}-output.json.gz',value);row['status']='accepted';return value
 except Exception as exc:row.update(status='rejected',error_type=type(exc).__name__,error=str(exc));raise
 finally:active.pop();put(base/'generations.json',generations)
gateway.ModelGateway.generate=generate
put(base/'dispatch.json',{'case_id':case_id,'code':f['candidate_revision'],'physical_limit':40,'same_case_retry':False,'provider_policy_sha256':t.routing_hash,'new_model_calls_before_dispatch':0})
put(base/'request.json',frozen_case['request'])
result={'case_id':case_id,'quality_certified':False,'environment':'isolated same-code native serving transport and API','stronger_model_comparison':False}
try:
 response=asyncio.run(cm_context(actual.service,deepcopy(frozen_case['request'])));put(base/'response.json',response)
 body=response.get('body') or {};result.update(http_status=response['status'],status=body.get('status'),run_id=body.get('run_id'))
 answer=body.get('answer',{});(base/'answer.txt').write_text(answer.get('text','') if isinstance(answer,dict) else str(answer))
 # Persist the actual API follow-up endpoints only when the API supplies them.
except Exception as exc:
 result.update(error_type=type(exc).__name__,error=str(exc));(base/'error.txt').write_text(traceback.format_exc())
finally:
 result.update(model_calls=len(calls),seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
  journals=[str(p.relative_to(ROOT)) for p in runtime.rglob('journal.sqlite')],active_pointer_unchanged=sha(pointer)==f['pointer_sha256'])
 put(base/'result.json',result);print('LIVE_DONE',case_id,result,flush=True)
pipeline.store.close();sys.stdout.flush();os._exit(0)
'''
(T/'live.py').write_text(s)
(T/'resource_guard.py').write_text((ROOT/'06_TOOLS/EXPERIMENTS/adr_1171/resource_guard.py').read_text())
print('native audited live runner prepared, no calls')
