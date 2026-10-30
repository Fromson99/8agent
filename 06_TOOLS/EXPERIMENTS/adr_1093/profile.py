"""Offline literal native replay with bounded low-frequency stack sampling."""
from common import *
import gzip,sys,os,time,threading,socket,sqlite3,traceback,resource,shutil,re,importlib
from contextlib import contextmanager
from copy import deepcopy
from collections import Counter
from functools import wraps
sys.dont_write_bytecode=True
f=read(DES/'freeze.json');C=ROOT/f['code_root'];OUT=ART/'run-001'
assert not OUT.exists();OUT.mkdir(parents=True)
for n,h in f['scripts'].items():assert sha(ROOT/n)==h,n
for n,h in f['code_files'].items():assert sha(C/n)==h,n
def load(ref):
 p=ROOT/ref['path'];assert sha(p)==ref['sha256'],ref['path']
 if p.suffix=='.gz':
  with gzip.open(p,'rt',encoding='utf8') as stream:return json.load(stream)
 return read(p)
binding=load(f['source_binding']);expected_response=load(f['response']);request=load(f['request']);tape=[(load(x['wire']),load(x['response'])) for x in f['calls']]
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,)*2)
def resources():
 mem={r.split(':')[0]:int(r.split()[1])*1024 for r in Path('/proc/meminfo').read_text().splitlines() if r.startswith(('MemAvailable:','SwapTotal:','SwapFree:'))}
 rss=next(int(r.split()[1])*1024 for r in Path('/proc/self/status').read_text().splitlines() if r.startswith('VmRSS:'))
 return {'rss':rss,'available':mem['MemAvailable'],'swap':mem['SwapTotal']-mem['SwapFree'],'disk':shutil.disk_usage(ROOT).free}
def guard():
 r=resources();assert r['rss']<=4*1024**3 and r['available']>=3*1024**3 and r['swap']<=512*1024**2 and r['disk']>=20*1024**3,r
 assert sha(ROOT/f['active_pointer']['path'])==f['active_pointer']['sha256']
 return r
for k in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_IMPLEMENTATION','LEGAL_AGENT_PROFILE','TEAM_ID','AD_WORKSPACE'):
 assert not os.environ.get(k),k
os.environ.update(GENOS_RUNTIME_DIR=str(OUT/'runtime'),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1',LAWRAG_WORKSPACE_ROOT=str(ROOT),OPEN_ROUTER='OFFLINE_NO_NETWORK')
original_connect=socket.socket.connect
def no_network(self,address):
 if self.family in (socket.AF_INET,socket.AF_INET6):raise AssertionError('network forbidden')
 return original_connect(self,address)
socket.socket.connect=no_network

spans=[];stacks={};sample_stacks=Counter();sample_categories=Counter();worker=None;sampling_stop=threading.Event();guard_error=None;query_counts=Counter();current_query={};initial=resources();sample_total=0;sample_time=0.0
@contextmanager
def span(name):
 tid=threading.get_ident();stack=stacks.setdefault(tid,[]);started=time.perf_counter();cpu=time.thread_time();parent=stack[-1][0] if stack else None;row=[name,started];stack.append(row)
 try:yield
 finally:
  ended=time.perf_counter();stack.pop();spans.append({'name':name,'start':started,'end':ended,'seconds':ended-started,'cpu_seconds':time.thread_time()-cpu,'parent':parent,'thread':tid})
def timed(owner,name,label=None):
 original=getattr(owner,name)
 @wraps(original)
 def call(*args,**kwargs):
  with span(label or name):return original(*args,**kwargs)
 setattr(owner,name,call)

raw_connect=sqlite3.connect
def traced_connect(*args,**kwargs):
 connection=raw_connect(*args,**kwargs);location=str(args[0] if args else kwargs.get('database',''));location='journal' if 'journal.sqlite' in location else 'case' if 'runtime' in location else Path(location).name
 def trace(sql):
  if len(sql)>6000:shape=sql[:80]+' [large statement]'
  else:shape=re.sub(r'\b\d+\b','?',re.sub(r"'(?:[^']|'')*'",'?',sql))
  query_counts[(location,shape)]+=1;current_query[threading.get_ident()]=(location,shape)
 connection.set_trace_callback(trace);return connection
sqlite3.connect=traced_connect

sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT)]
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport
from fastapi.testclient import TestClient
from semantic_runtime.legal_agent import unified_runtime,unified_rag,law_navigation,bounded_source_session,source_recall,definition_entry,decision_projection,repository,read_judgment
from semantic_runtime.legal_agent import completion_execution,read_judgment_final
t=LocalQwen38Transport(C,ROOT);assert t.binding==binding['profile']['model_binding']
with span('application.prepare'):
 app=create_app(OUT/'runtime',ROOT/binding['data_path'],contracts_root=C,release=deepcopy(binding['binding']),provider=object(),vector=False,implementation='legal-agent-unified-v6',legal_agent_profile=deepcopy(binding['profile']),legal_agent_transport=t,workspace_root=ROOT,runtime_root=OUT/'runtime')
pipeline=app.state.pipeline
root_run=unified_runtime.run
@wraps(root_run)
def run(*args,**kwargs):
 global worker
 worker=threading.get_ident()
 with span('request.native'):return root_run(*args,**kwargs)
unified_runtime.run=run
original_stage=unified_rag.UnifiedExecution.stage
@wraps(original_stage)
def stage(self,stage,*args,**kwargs):
 with span('stage.'+stage):return original_stage(self,stage,*args,**kwargs)
unified_rag.UnifiedExecution.stage=stage
for name in ('view','save','execute','validate','request_decision','bounded_result','read_records'):
 timed(law_navigation.Investigation,name,'navigation.'+name)
for name in ('prepare_navigation_context','prepare_source_recall','structured'):
 timed(bounded_source_session.BoundedSourceSession,name,'session.'+name)
timed(source_recall.SourceRecall,'prepare','recall.prepare')
for name in ('matches','verified','acquire_initial'):timed(definition_entry,name,'definitions.'+name)
for name in ('event','save_view','evidence','put','head'):timed(repository.WorkRepository,name,'journal.'+name)
for name in ('normalize_review','validate_review','context'):timed(read_judgment,name,'judgment.'+name)
timed(decision_projection,'choose_read','decision.choose_read')

def sample():
 global sample_total,sample_time,guard_error
 last=time.perf_counter();guard_at=last
 while not sampling_stop.wait(.01):
  now=time.perf_counter();elapsed=now-last;last=now
  frame=sys._current_frames().get(worker)
  if frame is None:continue
  names=[x[0] for x in stacks.get(worker,[])];chain=[]
  while frame:
   code=frame.f_code;chain.append(f'{code.co_filename}:{code.co_firstlineno}:{code.co_name}');frame=frame.f_back
  category='VIEW' if 'navigation.view' in names else 'OFFLINE_TRANSPORT' if 'transport.recorded' in names else next((n for n in reversed(names) if n.startswith('stage.')),'REQUEST_OTHER')
  sample_stacks[(category,tuple(chain))]+=elapsed;sample_categories[category]+=elapsed;sample_total+=1;sample_time+=elapsed
  if now-guard_at>1:
   guard_at=now
   try:guard()
   except BaseException as exc:guard_error=str(exc)

def comparable(body):
 value=deepcopy(body);user=json.loads(value['messages'][1]['content']);v=user['view']
 if re.fullmatch(r'V[0-9a-f]{32}',str(v.get('view_id',''))):v.pop('view_id')
 value['messages'][1]['content']=user;return value
def differences(a,b,path=''):
 if type(a)!=type(b):return [path+' TYPE']
 if isinstance(a,dict):
  result=[]
  for k in sorted(set(a)|set(b)):
   if k not in a or k not in b:result.append(path+'/'+k+' missing')
   else:result+=differences(a[k],b[k],path+'/'+k)
  return result
 if isinstance(a,list):
  if len(a)!=len(b):return [path+' length']
  return [p for i,(x,y) in enumerate(zip(a,b)) for p in differences(x,y,path+'/'+str(i))]
 return [] if a==b else [path]
calls=[]
def send_once(*,body,ticket):
 with span('transport.recorded'):
  guard();assert not guard_error,guard_error
  index=len(calls);assert index<len(tape),'extra model request'
  expected,response=tape[index];a,b=comparable(expected),comparable(body);diff=differences(a,b)
  calls.append({'number':index+1,'protected_exact':not diff,'differences':diff[:40]})
  if diff:
   put(OUT/'mismatch-expected.json',a);put(OUT/'mismatch-actual.json',b);raise AssertionError('protected request mismatch '+str(diff[:8]))
  print('RECORDED_RESPONSE',index+1,flush=True)
  return {'status_code':200,'body_json':deepcopy(response),'acceptance':'ACCEPTED'}
t.send_once=send_once
started=None;result={'completed':False,'known_in_sample':True,'new_model_calls':0,'new_tokens':0,'quality_certified':False,'product_code_changed':False,'network_allowed':False};thread=threading.Thread(target=sample,daemon=True)
try:
 guard();thread.start()
 with TestClient(app) as client:
  assert client.get('/health').status_code==200
  started=time.perf_counter()
  with span('request.http'):
   response=client.post('/v1/rag/ask',json=request['json']);body=response.json()
  result['request_seconds']=time.perf_counter()-started;put(OUT/'response.json',{'status':response.status_code,'body':body})
  assert response.status_code==200
  def answer(v):
   a=deepcopy(v['answer']);assert a['id']=='answer:'+v['run_id'] and a['query_id']==v['query']['id'];a.pop('id');a.pop('query_id');return a
  result['answer_exact']=answer(body)==answer(expected_response['body']);assert result['answer_exact']
  assert len(calls)==9 and all(x['protected_exact'] for x in calls)
  assert len([s for s in spans if s['name']=='navigation.view'])==4
  result['completed']=True
except BaseException as exc:
 result.update(error_type=type(exc).__name__,error=str(exc));(OUT/'error.txt').write_text(traceback.format_exc())
finally:
 sampling_stop.set();thread.join(timeout=3)
 result.update(recorded_responses_used=len(calls),calls=calls,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,resources=resources(),active_pointer_unchanged=sha(ROOT/f['active_pointer']['path'])==f['active_pointer']['sha256'],samples=sample_total,sampled_seconds=sample_time,guard_error=guard_error)
 if started is not None:result.setdefault('request_seconds',time.perf_counter()-started)
 put(OUT/'spans.json',spans);put(OUT/'sql-counts.json',[{'database':db,'sql':sql,'count':n} for (db,sql),n in query_counts.most_common()])
 with gzip.open(OUT/'samples.jsonl.gz','wt',encoding='utf8') as out:
  for (category,stack),seconds in sample_stacks.items():out.write(json.dumps({'category':category,'stack':stack,'seconds':seconds},ensure_ascii=False)+'\n')
 put(OUT/'result.json',result);pipeline.store.close()
 print('PROFILE_DONE',json.dumps({k:v for k,v in result.items() if k not in ('calls',)},ensure_ascii=False),flush=True)
sys.stdout.flush();sys.stderr.flush();os._exit(0 if result['completed'] else 1)
