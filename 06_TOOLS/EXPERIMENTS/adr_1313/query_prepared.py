from common import *
import os,time,traceback,importlib.util,resource
from types import SimpleNamespace as NS
from copy import deepcopy
os.environ.update(PYTHONDONTWRITEBYTECODE='1',AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1')
for n in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_ONTOLOGY_CONFIG','GENOS_RAG_ONTOLOGY_ENABLED','GENOS_STATE_DIR','GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR'):os.environ.pop(n,None)
arm=sys.argv[1];assert arm=='oracle';assert sha(Path(__file__))==read(DES/'observer-repair.json')['runner_sha256'];desc=read(DES/('candidate-'+arm+'.json'));C=ROOT/desc['code_root'];assert all(sha(C/n)==h for n,h in desc['selected_files'].items())
for n,h in read(DES/'freeze.json')['files'].items():assert sha(ROOT/n)==h,n
base=ART/'actual'/(arm+'-prepared');base.mkdir(parents=True,exist_ok=False);runtime=base/'runtime';os.environ['GENOS_RUNTIME_DIR']=str(runtime)
from resource_guard import Guard
guard=Guard(base);guard.start();cases=read(DES/'query-cases.json');did=cases['document_id'];scope=[did];events=[];rows=[];phase='prepare';begin=time.monotonic();oracle_queries=[];oracle_sql_shapes={};ctx=opened=None;app=None;observer=None
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(ROOT)]
# Research-only driver observer; credentials remain in memory and only SELECT is allowed.
if arm=='oracle':
 import oracledb
 realconnect=oracledb.connect
 class Cursor:
  def __init__(self,c):self.c=c;self.event=None
  def __getattr__(self,k):return getattr(self.c,k)
  def __enter__(self):return self
  def __exit__(self,*a):return self.c.__exit__(*a)
  def __iter__(self):return self
  def __next__(self):
   row=self.fetchone()
   if row is None:raise StopIteration
   return row
  def execute(self,statement,*a,**k):
   guard.check();assert statement.lstrip().upper().startswith(('SELECT','WITH')),'NON_READ_STATEMENT_REFUSED'
   started=time.monotonic();qid=hashlib.sha256(statement.encode()).hexdigest();oracle_sql_shapes[qid]=statement
   row={'phase':phase,'sql_sha256':qid,'seconds':0,'fetch_seconds':0,'rows':0,'status':'started'};oracle_queries.append(row);self.event=row
   try:out=self.c.execute(statement,*a,**k);row['status']='OK';return self if out is self.c else out
   except Exception as e:row.update(status='ERROR',type=type(e).__name__,error=str(e));raise
   finally:row['seconds']=time.monotonic()-started
  def fetch(self,name,*a,**k):
   started=time.monotonic()
   try:
    out=getattr(self.c,name)(*a,**k)
    if self.event:self.event['rows']+=int(out is not None) if name=='fetchone' else len(out)
    return out
   finally:
    if self.event:self.event['fetch_seconds']+=time.monotonic()-started
  def fetchone(self,*a,**k):return self.fetch('fetchone',*a,**k)
  def fetchmany(self,*a,**k):return self.fetch('fetchmany',*a,**k)
  def fetchall(self,*a,**k):return self.fetch('fetchall',*a,**k)
 class Connection:
  def __init__(self,c):object.__setattr__(self,'c',c)
  def __getattr__(self,k):return getattr(self.c,k)
  def __setattr__(self,k,v):setattr(self.c,k,v)
  def __enter__(self):return self
  def __exit__(self,*a):return self.c.__exit__(*a)
  def cursor(self,*a,**k):return Cursor(self.c.cursor(*a,**k))
 def connect(**kw):
  assert kw.get('dsn','').startswith('127.0.0.1:'),'Only the existing local readonly database is allowed'
  c=realconnect(**kw);put(base/'oracle-version.json',{'version':c.version,'local_loopback':True,'readonly_credentials':True});return Connection(c)
 oracledb.connect=connect
else:
 from sql_observer import Observer
 observer=Observer(ROOT/read(DES/'baseline.json')['release']['data_path'],runtime);observer.install()
def count():
 if arm=='oracle':return len(oracle_queries)
 return sum(r['trace_statements'] for r in observer.report()['rows'] if r['database']=='corpus' and r['operation'] in ('trace_SELECT','trace_WITH'))
def run_case(name,fn,check=None):
 global phase
 guard.check();phase=name
 if observer:observer.phase=name
 start=time.monotonic();n=count()
 try:
  value=fn()
  if check:check(value)
  row={'id':name,'status':'PASS','seconds':time.monotonic()-start,'sql_selects':count()-n,'value':value}
 except Exception as e:row={'id':name,'status':'FAIL','seconds':time.monotonic()-start,'sql_selects':count()-n,'error':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()}
 rows.append(row);put(base/'progress.json',rows);print('CASE',arm,name,row['status'],round(row['seconds'],3),row['sql_selects'],flush=True)
 if row.get('error') in ('BudgetPause','AbsoluteDeadlineExceeded'):raise RuntimeError('Bounded actual DB request stopped')
 return row
try:
 data=ROOT/read(DES/'baseline.json')['release']['data_path'];store=None
 if arm=='oracle':
  gp=ART/'gold-connector';spec=importlib.util.spec_from_file_location('frozen_gold',gp/'connect.py');gold=importlib.util.module_from_spec(spec);spec.loader.exec_module(gold);gold.ROOT=ROOT;gold.ACTIVE_POINTER=gp/'active-pointer.json';original_binding=gold.engine_binding
  def binding():
   b=original_binding();assert b['engine_files']==read(DES/'baseline.json')['release']['files']
   assert all(sha(C/n)==h for n,h in desc['selected_files'].items())
   return {**b,'engine_root':str(C.relative_to(ROOT)),'engine_files':desc['selected_files']}
  gold.engine_binding=binding;ctx=gold.open_store(documents=scope,ontology_settings=DES/'ontology-off.json',seconds=cases['global_deadline_seconds'],max_calls=cases['oracle_max_queries']);store,request,transport=ctx.__enter__();data=None
 from semantic_runtime.app import create_app
 from semantic_runtime.provider import Haiku
 from semantic_runtime.document_agent import ServingDocumentAgent
 from semantic_runtime.legal_agent import structure_selection as ss,query_scope as qs
 from semantic_runtime.legal_agent.errors import ContractError
 from semantic_runtime.legal_agent.gateway import ModelGateway
 ModelGateway.generate=lambda *a,**k:(_ for _ in ()).throw(AssertionError('NO_MODEL_IN_DB_VALIDATION'))
 profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');assert not profile['candidate_navigation']['ontology_enabled']
 app=create_app(runtime,data,contracts_root=C,data_store=store,provider=Haiku(C,runtime/'provider',False,backend='source-only',trust_zone='internal'),implementation='legal-agent-unified-v6',legal_agent_profile=profile,workspace_root=ROOT,runtime_root=runtime,memory_identity=lambda req:{'user_id':'adr1313','team_id':'risk_team','document_ids':scope})
 store=app.state.pipeline.store;agent=ServingDocumentAgent(app.state.pipeline,app.state.pipeline.term_agent.config)
 phase='resources';n=count();start=time.monotonic();opened=agent.resources(scope);index,tools,glossary,matcher=opened.__enter__();events.append({'phase':'resources','seconds':time.monotonic()-start,'sql_selects':count()-n})
 assert store.manifest['store_sha256']==read(ROOT/read(DES/'baseline.json')['release']['data_path']/'manifest.json')['store_sha256']
 put(base/'binding.json',{'source_manifest':store.manifest,'code_root':str(C.relative_to(ROOT)),'code_files':len(desc['selected_files']),'oracle':arm=='oracle','query_release_id':request.release_id if arm=='oracle' else None,'scope':scope,'prepare_seconds':time.monotonic()-begin,'unit_index_manifest':matcher.unit_fulltext.manifest})
 # Corpus originals and SQL guards precede root traversal, so a root-size pause
 # cannot erase evidence about safe bounded reads.
 def original_blocks():
  out=[]
  for bid in cases['source_blocks']:
   n=count();value=store.source(did,bid);first=count()-n;n=count();again=store.source(did,bid);repeat=count()-n;assert value==again
   out.append({'block_id':bid,'row':value,'first_sql':first,'repeat_sql':repeat})
  return out
 run_case('original-blocks',original_blocks)
 saved={}
 for case in cases['selections']:
  def selection(case=case):
   try:value=ss.resolve(case['selection'],matcher,did,scope)
   except ss.SelectionError as e:
    assert case.get('expected_error')==e.code,(case['id'],e.code);return {'expected_error':e.code}
   assert 'expected_error' not in case and value['unit_ids']==case['expected'],(case['id'],value['unit_ids']);saved[case['id']]=value
   first=count();ss.verify(value,matcher,scope);repeat=ss.resolve(case['selection'],matcher,did,scope);assert repeat==value
   return {'record':value,'verify_and_repeat_sql':count()-first}
  # Root selection is last, after FTS and ACL probes below.
  if case['id']!='root-article-set':run_case(case['id'],selection)
 session=NS(scope=scope,tools=tools,matcher=matcher,direct_search_scope={'targets':[{'document_id':did,'unit_id':None}]})
 def search_scope():
  n=count();allowed=qs.search_sources(session);first=count()-n;n=count();again=qs.search_sources(session);repeat=count()-n
  assert set(getattr(allowed,'document_ids',scope))==set(scope)
  return {'type':type(allowed).__name__,'first_sql':first,'repeat_sql':repeat,'source_json_loaded':len(getattr(tools.sources,'cache',{}))}
 run_case('document-source-scope',search_scope);allowed=qs.search_sources(session)
 for case in cases['fts']:
  def search(case=case):
   idx=matcher.unit_fulltext;db=matcher.unit_fulltext_db
   first=idx.rank_page(db,case['terms'],allowed,limit=5);n=count();again=idx.rank_page(db,case['terms'],allowed,limit=5);assert first==again;repeat=count()-n
   second=idx.rank_page(db,case['terms'],allowed,cursor=first['next_cursor'],limit=5) if first['next_cursor'] else None
   return {'page1':first,'page2':second,'repeat_sql':repeat}
  run_case('fts-'+case['id'],search)
 def rejects():
  checks=[]
  try:ss.resolve(cases['selections'][0]['selection'],matcher,did,[])
  except ContractError:checks.append('unauthorized-selection-rejected')
  if saved:
   bad=deepcopy(next(iter(saved.values())));bad['unit_ids'].clear()
   try:ss.verify(bad,matcher,scope)
   except ContractError:checks.append('tampered-selection-rejected')
  assert len(checks)==2
  if arm=='oracle':
   try:request.restrict(['not-authorized'])
   except Exception as e:
    assert 'widen' in str(e).lower();checks.append('oracle-scope-widening-rejected')
  return checks
 run_case('acl-hash-guards',rejects)
 case=cases['selections'][-1]
 def root_selection():
  value=ss.resolve(case['selection'],matcher,did,scope);assert value['unit_ids']==case['expected'];n=count();ss.verify(value,matcher,scope);assert ss.resolve(case['selection'],matcher,did,scope)==value
  return {'record':value,'verify_and_repeat_sql':count()-n}
 run_case(case['id'],root_selection)
 if arm=='oracle':
  def expired():
   original=request.sql.deadline;request.sql.deadline=time.monotonic()-1
   try:
    from semantic_runtime.oracle_query_cache import for_request
    try:for_request(request)
    except Exception as e:
     assert type(e).__name__=='BudgetPause';return {'deadline_rejected':True}
    raise AssertionError('expired cache was accepted')
   finally:request.sql.deadline=original
  run_case('oracle-cached-deadline',expired)
except BaseException as e:put(base/'failure.json',{'type':type(e).__name__,'error':str(e),'traceback':traceback.format_exc(),'completed_cases':len(rows)});print('ACTUAL_FAILURE',type(e).__name__,str(e),flush=True)
finally:
 phase='cleanup'
 if opened:
  try:opened.__exit__(None,None,None)
  except Exception as e:events.append({'cleanup_error':str(e)})
 if ctx:
  try:ctx.__exit__(None,None,None)
  except Exception as e:events.append({'cleanup_error':str(e)})
 elif app:app.state.pipeline.store.close()
 if arm=='oracle':
  put(base/'oracle-query-observation.json',{'queries':oracle_queries,'selects':len(oracle_queries),'scope':'Actual readonly driver execute/fetch wall; not pure DB CPU; includes mappingpreflight','writes':0});write_raw_json(base/'oracle-sql-shapes.json.gz',oracle_sql_shapes)
 if observer:put(base/'sqlite-observation.json',observer.report());observer.uninstall()
 result={'arm':arm,'passed':sum(x['status']=='PASS' for x in rows),'failed':sum(x['status']=='FAIL' for x in rows),'total_cases':len(rows),'completed':not(base/'failure.json').exists(),'seconds':time.monotonic()-begin,'rows':rows,'events':events,'model_calls':0,'oracle_writes':0,'DDL':0,'selected_main_unchanged':True,'code_unchanged':all(sha(C/n)==h for n,h in desc['selected_files'].items())};put(base/'result.json',result)
 guard.done.set();guard.thread.join(timeout=2);put(base/'resource-final.json',{'peak_rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'sample':guard.check()})
 print('ACTUAL_RESULT',arm,result['passed'],result['failed'],result['completed'],round(result['seconds'],3),flush=True)
