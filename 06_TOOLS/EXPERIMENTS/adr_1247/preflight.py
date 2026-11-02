from common import *
import os,importlib,asyncio,sqlite3,time
baseline=read(DES/'baseline.json');C=ROOT/baseline['release']['code_root'];data=ROOT/baseline['release']['data_path']
for key in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_ONTOLOGY_ENABLED','GENOS_RAG_ONTOLOGY_CONFIG'):
 assert not os.environ.get(key),'Unexpected '+key
os.environ.update(GENOS_RUNTIME_DIR=str(ART/'preflight-runtime'),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',LAWRAG_WORKSPACE_ROOT=str(ROOT),OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2')
for key in ('GENOS_STATE_DIR','GENOS_DETAIL_LOG_DIR','GENOS_SHARED_LOG_DIR','GENOS_SYSTEM_LOG_DIR'):os.environ.pop(key,None)
sys.path[:0]=[str(ROOT),str(ROOT/'02_BACKEND')]
import service
actual=importlib.import_module('service.service');start=time.monotonic();app=actual.application();p=app.state.pipeline;t=p.term_agent.transport
assert Path(p.contracts.root)==C
assert set(read(DES/'cases.json')[0]['request']['json']['document_ids'])<=set(t.public_scope)
assert set(t.public_scope)==set(read(DES/'corpus.json')['document_ids'])
assert p.term_agent.profile['candidate_navigation']['ontology_enabled'] is False
assert asyncio.run(actual.service({}, {'API_TYPE':'HEALTH'}))['status']==200
with sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True) as db:
 count=db.execute('SELECT COUNT(*) FROM source_block WHERE document_id=?',('7bbe815ff43b6635',)).fetchone()[0];assert count>0
put(DES/'preflight.json',{'passed':True,'generation':128,'code_files':len(baseline['release']['files']),'source_backend':'SQLite','state_backend':'SQLite','source_document':'7bbe815ff43b6635','source_blocks':count,'ontology_enabled':False,'initial_search':p.term_agent.profile['candidate_navigation'].get('initial_search'),'prepare_seconds':time.monotonic()-start,'new_model_calls':0,'data_path':str(data.relative_to(ROOT)),'public_documents':len(t.public_scope)})
p.store.close();print('SQLite source/state and MAIN128 service preflight PASS; ontology OFF; no model calls')
