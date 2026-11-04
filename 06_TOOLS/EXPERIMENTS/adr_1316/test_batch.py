import time,pytest
from copy import deepcopy
from types import SimpleNamespace as NS
from semantic_runtime.oracle_dp_io import DPError,BudgetPause,digest
from semantic_runtime.oracle_query_matcher import Units
from semantic_runtime.oracle_query import SourceReader

def fixture(count=205,bad=None):
 rows=[{'document_id':'d','unit_id':str(i),'unit':{'parent':None if i==0 else '0','span':[i,i]},'coordinate':None} for i in range(count)]
 ids=sorted(r['unit_id'] for r in rows);calls=[]
 def idpage(did,after=None,limit=100):
  calls.append(('ids',after,limit));r=[v for v in ids if after is None or v>after][:limit]
  if bad=='missing_id' and after is None:r=r[:-1]
  if bad=='duplicate_id' and r:r[-1]=r[0]
  if bad=='deadline':req.sql.deadline=time.monotonic()-1
  return {'rows':r,'next':r[-1] if len(r)==limit else None}
 def page(kind,**kw):
  calls.append((kind,kw))
  if kind=='native.structure_proof':return {'rows':[] if bad=='no_proof' else [{'document_id':'d','unit_count':count}], 'next':None}
  selected=rows
  if 'lookup_ids' in kw:
   selected=[r for r in rows if digest(['d',r['unit_id']]) in kw['lookup_ids']]
   if bad=='missing_row':selected=selected[:-1]
   if bad=='wrong_doc':selected=[{**r,'document_id':'foreign'} for r in selected]
   if bad=='duplicate_row' and selected:selected=[selected[0]]*len(selected)
  return {'rows':deepcopy(sorted(selected,key=lambda r:digest(['d',r['unit_id']]))),'next':None}
 req=NS(release_id='r',snapshot=NS(binding_hash='s'),sources=NS(allowed={'d'},unit_ids=idpage),records=NS(manifest={'extension':{'schema_version':'r12-packed-extension-v1','packed_kinds':['native.unit']}},page=page),sql=NS(deadline=time.monotonic()+100))
 return Units(req),calls,rows

def test_batch_matches_full_rows_global_order_and_reuses_root():
 u,c,rows=fixture();assert list(u._document_rows('d'))==sorted(rows,key=lambda r:digest(['d',r['unit_id']]))
 assert all(len(x[1]['lookup_ids'])<=99 for x in c if x[0]=='native.unit')
 assert len([x for x in c if x[0]=='native.unit'])==3
 assert len(list(u.children_for('d',None)))==1;n=len(c)
 assert len(list(u.children_for('d','0')))==204 and u[('d','204')]==rows[204]['unit'];assert len(c)==n

@pytest.mark.parametrize('bad',['missing_id','duplicate_id','no_proof','missing_row','wrong_doc','duplicate_row','deadline'])
def test_bad_batches_never_yield_or_cache_root(bad):
 u,c,_=fixture(bad=bad)
 with pytest.raises((DPError,BudgetPause)):list(u.children_for('d',None))
 assert getattr(u,'_root_document',None) is None

def test_large_document_uses_original_path_without_id_enumeration():
 u,c,r=fixture(5);u.ROOT_MAX_UNITS=4;assert len(list(u.children_for('d',None)))==1
 assert not any(x[0]=='ids' for x in c) and getattr(u,'_root_document',None) is None
 assert 'lookup_ids' not in next(x[1] for x in c if x[0]=='native.unit')

def test_source_id_projection_binds_acl_version_and_has_no_json():
 calls=[]
 def query(sql,binds,limit):calls.append((sql,binds,limit));return [{'DATASET_VERSION':'v','DOCUMENT_ID':'d','UNIT_ID':'1'},{'DATASET_VERSION':'v','DOCUMENT_ID':'d','UNIT_ID':'2'}]
 reader=SourceReader(NS(client=NS(),query=query),NS(dataset_version='v'),{'d'})
 assert reader.unit_ids('d',limit=2)=={'rows':['1','2'],'next':'2'}
 sql,b,l=calls[0];assert 'SOURCE_JSON' not in sql and 'DATASET_VERSION=:version' in sql and 'DOCUMENT_ID=:document' in sql and 'FETCH FIRST 2' in sql
 reader.unit_ids('d',after='0');assert ('after_unit','0','VARCHAR2') in calls[-1][1]
 with pytest.raises(DPError,match='QUERY_SCOPE'):reader.unit_ids('foreign')
 with pytest.raises(DPError,match='QUERY_PAGE'):reader.unit_ids('d',limit=101)

@pytest.mark.parametrize('rows,match',[([{'DATASET_VERSION':'x','DOCUMENT_ID':'d','UNIT_ID':'1'}],'ROW_BINDING'),([{'DATASET_VERSION':'v','DOCUMENT_ID':'f','UNIT_ID':'1'}],'ROW_BINDING'),([{'DATASET_VERSION':'v','DOCUMENT_ID':'d','UNIT_ID':'1'}]*2,'PAGE_ORDER')])
def test_source_id_wrong_scope_version_duplicate_rejected(rows,match):
 reader=SourceReader(NS(client=NS(),query=lambda *a,**k:rows),NS(dataset_version='v'),{'d'})
 with pytest.raises(DPError,match=match):reader.unit_ids('d')

def test_optional_development_mapping_config_serves_from_frozen_root(monkeypatch):
 from semantic_runtime import oracle_dp,oracle_ords
 for k,v in {'DP':'oracle','ORACLE_ORDS_SCHEMA':'fixture','ORACLE_ORDS_CLIENT_ID':'fixture','ORACLE_ORDS_CLIENT_SECRET':'fixture','GENOS_ORACLE_TABLE_MAPPING':'development_g19_1'}.items():monkeypatch.setenv(k,v)
 monkeypatch.setattr(oracle_ords,'create_client',lambda **kw:NS())
 client=oracle_dp.client_from_environment();assert client.schema_map.profile=='development_g19_1'
 assert len(client.schema_map.tables)==17 and len(client.schema_map.agent_tables)==4
