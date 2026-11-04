from common import *
import importlib.util,time
GOLD=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';OUT=ART/'main';resource_dir=ART/'selected-gold-resource';resource_dir.mkdir()
from resource_guard import Guard
g=Guard(resource_dir);g.start()
spec=importlib.util.spec_from_file_location('selected_gold_read',GOLD/'connect.py');gold=importlib.util.module_from_spec(spec);spec.loader.exec_module(gold)
case=read(DES/'query-cases.json');did=case['document_id'];checks=[];start=time.monotonic()
with gold.open_store(documents=[did],ontology_settings=DES/'ontology-off.json',seconds=120,max_calls=1000) as (store,req,transport):
 from semantic_runtime.oracle_query_matcher import Units
 expected=read(ART/'actual/oracle-after/result.json')['rows'][0]['value']
 assert [store.source(did,v['block_id']) for v in expected]==[v['row'] for v in expected];checks.append('six_original_sources_exact')
 units=Units(req);roots=list(units.children_for(did,None));assert len(units._root_document[1])==3946;checks.append('selected_packed_root3946')
 before=req.sql.calls;assert units[(did,'1420')];list(units.children_for(did,'1420'));assert req.sql.calls==before;checks.append('root_reused_without_SQL')
 assert gold.engine_binding()['engine_release_id']=='query-latency-native-20261104-r1';checks.append('actual_main137_binding')
 calls=req.sql.calls
put(OUT/'selected-gold-read.json',{'passed':True,'checks':checks,'seconds':time.monotonic()-start,'sql_calls':calls,'new_models':0,'writes':0,'selected_actual_connector':True});g.done.set();g.thread.join(timeout=2);put(resource_dir/'resource-final.json',g.check());print('Selected Gold original/root',len(checks),'checks PASS',calls,'SQL')
