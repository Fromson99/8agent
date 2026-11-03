from common import *
import asyncio,importlib,importlib.util,os,time,traceback
mode=sys.argv[1];out=ART/'checks'/(sys.argv[2] if len(sys.argv)>2 else mode);out.mkdir(parents=True,exist_ok=False)
start=time.monotonic();b=read(DES/'baseline.json');C=selected()
os.environ.update(GENOS_RUNTIME_DIR=str(out/'runtime'),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT),OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2')
for n in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_ONTOLOGY_ENABLED','GENOS_RAG_ONTOLOGY_CONFIG','TEAM_ID','AD_WORKSPACE'):os.environ.pop(n,None)
if mode=='real-api':
 os.environ['OPEN_ROUTER']='synthetic-disabled-no-model'
 sys.path[:0]=[str(ROOT),str(ROOT/'02_BACKEND')]
 import service
 app=service.application();p=app.state.pipeline
 checks=[]
 def record(ident,good,detail):
  checks.append({'id':ident,'passed':bool(good),'detail':detail});put(out/'checks.json',checks);print(ident,'PASS' if good else 'FAIL',flush=True)
 try:
  from fastapi.testclient import TestClient
  with TestClient(app,raise_server_exceptions=False) as api:
   health=api.get('/health');record('HEALTH',health.status_code==200 and Path(p.contracts.root)==C,{'http':health.status_code,'code_root':str(p.contracts.root),'data':str(p.store.path)})
   for category,ident in [('internal','IT-01'),('external','IT-02')]:
    r=api.get('/v1/rag/documents',params={'category':category,'limit':500});v=r.json();put(out/(ident+'.json'),v)
    record(ident,r.status_code==200 and v.get('total',0)>0 and all(x['category']==category for x in v.get('documents',[])),{'http':r.status_code,'total':v.get('total'),'model_calls':0})
   ext=read(out/'IT-02.json')['documents'];chosen=next((d for d in ext if d['name']=='상법'),ext[0]);did=chosen['id']
   r=api.get('/v1/rag/documents',params={'title_query':chosen['name']});v=r.json();record('IT-03',r.status_code==200 and did in [d['id'] for d in v.get('documents',[])],{'query':chosen['name'],'total':v.get('total')})
   folder=chosen.get('navigation_folder')
   r=api.get('/v1/rag/documents',params={'folder':folder or '__missing_folder__'});v=r.json();record('IT-04',bool(folder) and r.status_code==200 and did in [d['id'] for d in v.get('documents',[])],{'folder':folder,'total':v.get('total')})
   r=api.get('/v1/rag/document/outline',params={'doc_id':did,'limit':500});v=r.json();put(out/'outline.json',v)
   record('IT-05',r.status_code==200 and bool(v.get('nodes')),{'http':r.status_code,'doc_id':did,'nodes':v.get('total')})
   node=next(n for n in v['nodes'] if isinstance(n.get('span'),list) and n['span'][1]>n['span'][0])
   r=api.get('/v1/rag/document/read',params={'doc_id':did,'unit_id':node['id']});v=r.json();put(out/'selected-original.json',v)
   exact=all(p.store.db.execute('SELECT text FROM source_block WHERE document_id=? AND block_id=?',(did,x['block_id'])).fetchone()[0]==x['text'] for x in v.get('blocks',[]))
   record('IT-06',r.status_code==200 and bool(v.get('text')) and exact,{'http':r.status_code,'doc_id':did,'unit_id':node['id'],'blocks':len(v.get('blocks',[])),'exact':exact})
   a=api.get('/v1/rag/document/read',params={'doc_id':did,'limit':2}).json();c=api.get('/v1/rag/document/read',params={'doc_id':did,'limit':2,'offset':a['next_offset']}).json()
   combined=[x['block_id'] for x in a['blocks']+c['blocks']];expect=[r[0] for r in p.store.db.execute('SELECT block_id FROM source_block WHERE document_id=? ORDER BY CAST(block_id AS INTEGER),block_id LIMIT 4',(did,))]
   record('IT-07',combined==expect and len(set(combined))==4,{'block_ids':combined,'next_offset':c['next_offset']})
   r=api.get('/v1/rag/search',params={'q':'의결권','doc_id':did,'limit':5});v=r.json();put(out/'search.json',v)
   record('IT-08',r.status_code==200,{'http':r.status_code,'keys':list(v),'query':'의결권','doc_id':did,'content_success_to_be_inspected':True})
   for marker,ident in [('내규','IT-09-scope'),('외규','IT-10-scope')]:
    r=api.post('/v1/rag/ask',json={'question':marker+': 전체 문서 목록','use_llm':False});v=r.json();put(out/(ident+'.json'),v)
    record(ident,r.status_code==200 and bool(v.get('answer',{}).get('text')),{'http':r.status_code,'scope_only_not_model_answer':True})
   query=p.plan('상법 의결권',[did]);record('IT-11-scope',query['scope']['document_version_ids']==[did],{'document_ids':query['scope']['document_version_ids'],'scope_only_not_model_answer':True})
   record('RAG-UI',api.get('/rag/').status_code==200 and api.get('/rag/source-tiers.js').status_code==200,{'page':'/rag/'})
 except Exception as e:
  put(out/'failure.json',{'error':str(e),'type':type(e).__name__,'traceback':traceback.format_exc()});raise
 finally:
  p.store.close();put(out/'result.json',{'checks':checks,'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks),'seconds':time.monotonic()-start,'model_calls':0,'data':'actual selected local corpus','active_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']})
elif mode=='contracts':
 os.environ.update(WORKFLOW_TEST_CODE_ROOT=str(C),LOOP_TEST_CODE_ROOT=str(C),OPEN_ROUTER='synthetic-disabled-no-model')
 sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(ROOT),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
 import lawrag
 lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
 for name in ('pipeline','core'):
  pkg=importlib.import_module('lawrag.'+name);pkg.__path__.append(str(ROOT/'02_BACKEND/lawrag'/name))
 import conftest,pytest
 sys.path[:0]=[str(C/'02_BACKEND'),str(C)]
 names=['test_source_prefix_routing.py','test_document_focus.py','test_genos_source_accordion.py','test_main_workflow_display.py',
  'test_review_explanation_actions.py::test_native_review_view_is_model_free_and_replay_bound',
  'test_review_explanation_actions.py::test_genos_review_contract_render_and_action_passthrough',
  'test_truncated_review_source_reply.py','test_internal_concept_comparison.py','test_comparison_investigation_dedup.py']
 reports=[]
 class Results:
  def pytest_collection_modifyitems(self,session,config,items):
   for module in list(sys.modules.values()):
    if module and str(getattr(module,'__name__','')).startswith(('test_','concept_general_fixture')):
     for attr in ('ROOT','R','CODE'):
      if getattr(module,attr,None)==ROOT:setattr(module,attr,C)
  def pytest_runtest_logreport(self,report):
   r=report
   if r.when=='call' or r.failed or r.skipped:reports.append({'test':r.nodeid,'when':r.when,'outcome':r.outcome,'error':r.longreprtext if r.failed else None})
 status=pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','--rootdir='+str(ROOT),'-p','no:cacheprovider','--basetemp='+str(out/'pytest'),*[str(ROOT/'05_TESTS/CONTRACTS'/n) for n in names]],plugins=[conftest,Results()])
 origins={n:str(Path(m.__file__).resolve()) for n,m in sys.modules.items() if n.startswith(('semantic_runtime','workflow.')) and getattr(m,'__file__',None)}
 result={'exit_code':int(status),'reports':reports,'passed':sum(r['outcome']=='passed' for r in reports),'failed':sum(r['outcome']=='failed' for r in reports),'skipped':sum(r['outcome']=='skipped' for r in reports),'origins':origins,'all_selected':all(Path(p).is_relative_to(C) for p in origins.values()),'seconds':time.monotonic()-start,'model_calls':0,'source':'synthetic fixtures'}
 put(out/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('reports','origins')},ensure_ascii=False));raise SystemExit(int(status))
elif mode=='oracle-readonly':
 import logging;logging.disable(logging.CRITICAL)
 path=ROOT/'06_TOOLS/maintenance/publish_gold_ontology_samples.py'
 spec=importlib.util.spec_from_file_location('readonly_publication_verifier',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 def write(name,v):
  if name=='verification.json':put(out/'result.json',{**v,'seconds':time.monotonic()-start,'model_calls':0,'data_writes':0,'verifier_sha256':sha(path)})
  else:put(out/(name+'.summary.json'),{'items':len(v),'sha256':hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False).encode()).hexdigest()})
 module.write=write;module.verify()
else:raise ValueError(mode)
