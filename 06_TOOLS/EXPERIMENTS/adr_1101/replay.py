"""One literal native replay per predeclared arm; no SQL trace or stack sampler."""
from pathlib import Path
from copy import deepcopy
from contextlib import contextmanager
from functools import wraps
from collections import Counter
import gzip,hashlib,json,os,re,resource,shutil,socket,sqlite3,sys,time,traceback
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1101-bounded-preparation-pins'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
arm=sys.argv[1];assert arm in ('baseline','optimized')
f=read(ADR/'artifacts/design/freeze.json');old=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1093-nonmodel-residual-profile/artifacts/design/freeze.json')
plan=read(ADR/'artifacts/design/replay.json');assert sha(__file__)==plan['runner_sha256']
C=ROOT/(old['code_root'] if arm=='baseline' else f['code_root'])
files=old['code_files'] if arm=='baseline' else f['files']
assert all(sha(C/n)==h for n,h in files.items())
OUT=ADR/'artifacts/run-001'/arm;assert not OUT.exists();OUT.mkdir(parents=True)
def load(ref):
    p=ROOT/ref['path'];assert sha(p)==ref['sha256']
    if p.suffix=='.gz':
        with gzip.open(p,'rt') as s:return json.load(s)
    return read(p)
binding=load(old['source_binding']);request=load(old['request']);expected_response=load(old['response'])
tape=[(load(r['wire']),load(r['response'])) for r in old['calls']]
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,)*2)
def resources():
    m={r.split(':')[0]:int(r.split()[1])*1024 for r in Path('/proc/meminfo').read_text().splitlines() if r.startswith(('MemAvailable:','SwapTotal:','SwapFree:'))}
    rss=next(int(r.split()[1])*1024 for r in Path('/proc/self/status').read_text().splitlines() if r.startswith('VmRSS:'))
    return {'rss':rss,'available':m['MemAvailable'],'swap':m['SwapTotal']-m['SwapFree'],'disk':shutil.disk_usage(ROOT).free}
def guard():
    r=resources();assert r['rss']<4*1024**3 and r['available']>3*1024**3 and r['swap']<512*1024**2 and r['disk']>20*1024**3,r
    assert sha(ROOT/old['active_pointer']['path'])==old['active_pointer']['sha256']
guard()
for key in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_IMPLEMENTATION','LEGAL_AGENT_PROFILE','TEAM_ID','AD_WORKSPACE'):assert not os.environ.get(key),key
os.environ.update(GENOS_RUNTIME_DIR=str(OUT/'runtime'),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1',LAWRAG_WORKSPACE_ROOT=str(ROOT),OPEN_ROUTER='OFFLINE_NO_NETWORK')
original_connect=socket.socket.connect
def no_network(self,address):
    if self.family in (socket.AF_INET,socket.AF_INET6):raise AssertionError('network forbidden')
    return original_connect(self,address)
socket.socket.connect=no_network
counts=Counter();raw_connect=sqlite3.connect;factories={}
def execute(self,sql,*args,**kwargs):
    counts['connection_execute']+=1
    if sql.startswith('SELECT * FROM source_block WHERE document_id=? AND block_id=?'):counts['source_point_select']+=1
    if sql.startswith('SELECT * FROM source_block') and ' IN (' in sql:counts['source_batch_select']+=1
    if 'FROM source_block' in sql and 'LENGTH(' in sql:counts['source_length_select']+=1
    if 'SELECT u.key,u.document_id,u.source_id,unit_fts.rank' in sql:counts['fts_projection']+=1
    if 'FROM unit_fts' in sql:counts['fts_select']+=1
    return super(type(self),self).execute(sql,*args,**kwargs)
def counted_connect(*args,**kwargs):
    base=kwargs.get('factory',sqlite3.Connection)
    if base not in factories:factories[base]=type('Counted'+base.__name__,(base,),{'execute':execute})
    kwargs['factory']=factories[base];return raw_connect(*args,**kwargs)
sqlite3.connect=counted_connect
spans=[]
@contextmanager
def span(name):
    start=time.perf_counter()
    try:yield
    finally:spans.append({'name':name,'start':start,'end':time.perf_counter()})
def timed(owner,name,label):
    previous=getattr(owner,name)
    @wraps(previous)
    def run(*args,**kwargs):
        with span(label):return previous(*args,**kwargs)
    setattr(owner,name,run)
sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT)]
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport
from semantic_runtime.legal_agent import law_navigation,bounded_source_session
from semantic_runtime import navigation_agent,document_agent,task_harness_agent,legal_navigation
from fastapi.testclient import TestClient
for owner in (navigation_agent,document_agent,task_harness_agent,legal_navigation):timed(owner,'glossary_assets','glossary.load')
timed(law_navigation.Investigation,'view','navigation.view')
timed(bounded_source_session.BoundedSourceSession,'prepare_navigation_context','resources.prepare')
t=LocalQwen38Transport(C,ROOT);assert t.binding==binding['profile']['model_binding']
actual_binding=deepcopy(binding['binding']);actual_binding.update(code_root=str(C),parent_release='MAIN106')
if arm=='optimized':actual_binding['candidate']=f['binding']
with span('application.prepare'):
    app=create_app(OUT/'runtime',ROOT/binding['data_path'],contracts_root=C,release=actual_binding,provider=object(),vector=False,implementation='legal-agent-unified-v6',legal_agent_profile=deepcopy(binding['profile']),legal_agent_transport=t,workspace_root=ROOT,runtime_root=OUT/'runtime')
put(OUT/'binding.json',{'actual':actual_binding,'code_files':files,'data_path':binding['data_path'],'profile_sha256':binding['profile_sha256']})
def comparable(body):
    value=deepcopy(body);user=json.loads(value['messages'][1]['content']);v=user['view']
    if re.fullmatch(r'V[0-9a-f]{32}',str(v.get('view_id',''))):v.pop('view_id')
    value['messages'][1]['content']=user;return value
def differences(a,b,path=''):
    if type(a)!=type(b):return [path+' TYPE']
    if isinstance(a,dict):
        return [p for k in sorted(set(a)|set(b)) for p in ([path+'/'+k+' missing'] if k not in a or k not in b else differences(a[k],b[k],path+'/'+k))]
    if isinstance(a,list):
        if len(a)!=len(b):return [path+' length']
        return [p for i,(x,y) in enumerate(zip(a,b)) for p in differences(x,y,path+'/'+str(i))]
    return [] if a==b else [path]
calls=[]
def send_once(*,body,ticket):
    with span('transport.recorded'):
        guard();index=len(calls);assert index<len(tape),'extra model request'
        expected,response=tape[index];a,b=comparable(expected),comparable(body);diff=differences(a,b)
        calls.append({'number':index+1,'protected_exact':not diff,'differences':diff[:40]})
        if diff:
            put(OUT/'expected.json',a);put(OUT/'actual.json',b);raise AssertionError('protected request mismatch '+str(diff[:10]))
        print(arm,'RESPONSE',index+1,flush=True)
        return {'status_code':200,'body_json':deepcopy(response),'acceptance':'ACCEPTED'}
t.send_once=send_once
result={'arm':arm,'completed':False,'new_model_calls':0,'quality_certified':False,'trace_callback':False,'source_checks_enabled':True}
started=None
try:
    with TestClient(app) as client:
        assert client.get('/health').status_code==200
        counts.clear();started=time.perf_counter()
        response=client.post('/v1/rag/ask',json=request['json']);ended=time.perf_counter();body=response.json()
        result.update(http_status=response.status_code,request_seconds=ended-started);put(OUT/'response.json',{'status':response.status_code,'body':body})
        assert response.status_code==200
        def answer(v):
            a=deepcopy(v['answer']);assert a['id']=='answer:'+v['run_id'] and a['query_id']==v['query']['id'];a.pop('id');a.pop('query_id');return a
        result['answer_exact']=answer(body)==answer(expected_response['body']);assert result['answer_exact']
        assert len(calls)==9 and all(x['protected_exact'] for x in calls)
        result['completed']=True
except BaseException as exc:
    result.update(error_type=type(exc).__name__,error=str(exc));(OUT/'error.txt').write_text(traceback.format_exc())
finally:
    ended=time.perf_counter() if started is None or 'request_seconds' not in result else started+result['request_seconds']
    def union(names):
        ranges=sorted((max(r['start'],started),min(r['end'],ended)) for r in spans if started is not None and r['name'] in names and r['end']>started and r['start']<ended)
        total=0;last=0
        for lo,hi in ranges:total+=max(0,hi-max(last,lo));last=max(last,hi)
        return total
    if started is not None:
        result.setdefault('request_seconds',ended-started)
        result['recorded_transport_seconds']=union({'transport.recorded'});result['glossary_loading_seconds']=union({'glossary.load'})
        result['nonmodel_excluding_glossary_seconds']=result['request_seconds']-union({'transport.recorded','glossary.load'})
        result['one_second_target_achieved']=result['completed'] and result['nonmodel_excluding_glossary_seconds']<=1
    result.update(calls=calls,sql_counts=dict(counts),peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,resources=resources(),active_pointer_unchanged=sha(ROOT/old['active_pointer']['path'])==old['active_pointer']['sha256'])
    put(OUT/'spans.json',spans);put(OUT/'result.json',result);app.state.pipeline.store.close()
    print('DONE',json.dumps({k:v for k,v in result.items() if k!='calls'},ensure_ascii=False),flush=True)
sys.stdout.flush();sys.stderr.flush();os._exit(0 if result['completed'] else 1)
