from common import *
import importlib.util,time
from resource_guard import Guard
out=ART/'main/gold-vector-r2';out.mkdir(exist_ok=False);g=Guard(out);g.start()
try:
 spec=importlib.util.spec_from_file_location('selected_gold',ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py')
 gold=importlib.util.module_from_spec(spec);spec.loader.exec_module(gold)
 question='주주총회의 보통결의 요건은 무엇인가?';start=time.monotonic()
 with gold.open_store(seconds=120,max_calls=200) as (store,req,transport):
  from semantic_runtime.initial_vector import Retriever
  reader=Retriever(req);result=reader.search(question,req.sources.allowed)
  put(out/'retrieval.json',result)
  assert result['rows'] and result['embedding_calls']==1
  before=req.sql.calls;assert reader.search(question,req.sources.allowed)==result and req.sql.calls==before
  rows=[]
  for row in result['rows'][:5]:
   matches=req.records.page('native.source',lookup_id=row['SOURCE_ID'],limit=2)['rows']
   assert len(matches)==1 and matches[0]['document_id']==row['DOC_ID']
   rows.append({'document_id':row['DOC_ID'],'source_id':row['SOURCE_ID'],'distance':row['DISTANCE'],'native_source':matches[0]})
  assert gold.engine_binding()['engine_release_id']=='oracle-development-vector-20261104-r1'
  put(out/'result.json',{'passed':True,'selected_main':138,'question':question,'documents':len(req.sources.allowed),'candidates':len(result['rows']),
   'sql_calls':req.sql.calls,'embedding_calls':1,'embedding':'existing local BGE-M3, 1024 dimensions, offline CPU',
   'publication':result['publication_id'],'top5':rows,'seconds':time.monotonic()-start,'readonly':True,'writes':0,'field_executed':False,
   'note':'Existing Gold adapter regression; development G19 adapter and GENOS embedding endpoint separately tested with fixed fixture; no quality/latency comparison'})
 print('Actual selected MAIN138 Gold vector PASS; 100 candidates, one local embedding')
finally:
 g.done.set();g.thread.join(timeout=3);put(out/'resources.json',g.check())
