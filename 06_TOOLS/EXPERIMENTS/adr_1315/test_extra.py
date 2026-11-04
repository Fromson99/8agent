import sqlite3,json,pytest
from copy import deepcopy
from types import SimpleNamespace as NS
from semantic_runtime.multi_entry_navigation import freeze
from semantic_runtime import folder_navigation as folder
from semantic_runtime.oracle_query_catalog import Records,record,ROW
from semantic_runtime.oracle_dp_io import digest,DPError


def test_freeze_preserves_shared_fields_without_mutability():
 shared={'span':[1,3],'child':[{'x':1}]};raw={'raw':shared,'span':shared['span'],'child':shared['child']};out=freeze(raw)
 assert out==raw and out['span'] is out['raw']['span'] and out['child'] is out['raw']['child']
 with pytest.raises(TypeError):out['span'].append(3)
 copy=deepcopy(out);copy['span'].append(4);assert out['span']==[1,3]
 assert freeze(raw) is not out

def test_freeze_rejects_cycles():
 v=[];v.append(v)
 with pytest.raises(ValueError,match='cyclic'):freeze(v)

@pytest.mark.parametrize('has_hash',[False,True])
def test_sqlite_catalogue_matches_sqlite_json_projection_and_artifact_guards(has_hash):
 db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;db.execute('CREATE TABLE document(document_id TEXT,name TEXT,json TEXT'+(',source_artifact_sha256 TEXT' if has_hash else '')+')')
 values=[{}, {'document_category':'internal','document_metadata':{'relative_path':'internal/a.txt','source_category':'internal'}}, {'document_category':None,'document_kind':'external_statute','origin':{'document_id':'2','status':'verified','raw_relative_path':'external/law/a.txt','source_artifact_sha256':'h'}}, {'origin':'{"document_id":"3","status":"unverified"}','document_metadata':None}]
 for i,v in enumerate(values):db.execute('INSERT INTO document VALUES('+','.join('?' for _ in range(4 if has_hash else 3))+')',(str(i),'title'+str(i),json.dumps(v),*(['h'] if has_hash else [])))
 store=NS(db=db,manifest={'generation_id':'g','store_sha256':'s'});columns={r[1] for r in db.execute('PRAGMA table_info(document)')}
 old=list(db.execute("SELECT document_id,name,json_extract(json,'$.document_category') category,json_extract(json,'$.document_kind') kind,json_extract(json,'$.origin') origin,json_extract(json,'$.document_metadata') metadata FROM document"));new=list(folder._catalogue_rows(store,columns))
 for a,b in zip(old,new):
  for k in a.keys():
   if k in ('origin','metadata') and a[k] is not None:assert json.loads(a[k])==json.loads(b[k])
   else:assert a[k]==b[k]
 trace=[];db.set_trace_callback(trace.append);matcher=NS();folder.bind_catalogue(matcher,store);assert len(matcher.document_catalogue)==4
 assert not any('SELECT source_artifact_sha256' in q for q in trace)
 if has_hash:
  bad=NS(db=db,manifest={'generation_id':'g2','store_sha256':'s'});projection={'generation_id':'g2','store_sha256':'s','documents':{'0':{'status':'verified','raw_relative_path':'external/law/a.txt','source_artifact_sha256':'wrong'}}}
  with pytest.raises(ValueError,match='artifact'):folder.bind_catalogue(NS(),bad,projection)
 db.close()

def request(use_mapping=True,alter=None):
 manifest={'tables':{'native.unit':{}},'extension':{'schema_version':'r12-packed-extension-v1'}}
 row=record('native.unit',{'a':1},key='k',document_id='d',lookup_id='id');value=json.dumps(row['value'],ensure_ascii=False);sqlrow={'ROW_ID':row['row_id'],'ROW_SHA256':row['sha256'],'DOCUMENT_ID':'d','LOOKUP_ID':'id','OWNER_ID':None,'TARGET_ID':None,'VALUE':value,'N':len(value.encode('utf-16-le'))//2}
 if alter:sqlrow.update(alter)
 calls=[];maps=[]
 def query(statement,binds,limit):calls.append((statement,binds));return [sqlrow]
 def names(k,only_kind):maps.append((k,only_kind));return NS(table="(SELECT * FROM bounded_native_units)")
 sql=NS(query=query)
 if use_mapping:sql.gold_config=NS(manifest=manifest,names=names)
 return Records(sql,digest(manifest),manifest,document_ids={'d'}),calls,maps

@pytest.mark.parametrize('mapping',[True,False])
def test_packed_page_uses_declared_kind_and_keeps_outer_acl_hash(mapping):
 r,c,m=request(mapping);assert r.page('native.unit',document_id='d',lookup_id='id')['rows']==[{'a':1}]
 stmt,binds=c[0];assert ('bounded_native_units' in stmt)==mapping
 assert 'RELEASE_ID=:release' in stmt and 'KIND=:kind' in stmt and ':authorized_documents' in stmt
 assert m==([('query_row','native.unit')] if mapping else [])

@pytest.mark.parametrize('bad,match',[({'DOCUMENT_ID':'foreign'},'QUERY_SCOPE'),({'ROW_SHA256':'0'*64},'QUERY_ROW_HASH'),({'LOOKUP_ID':'other'},'QUERY_ROW_HASH')])
def test_packed_page_rejects_unauthorized_changed_rows(bad,match):
 r,_,_=request(alter=bad)
 with pytest.raises(DPError,match=match):r.page('native.unit',document_id='d',lookup_id='id')

def test_packed_page_unknown_kind_and_scope_fail_before_sql():
 r,c,m=request()
 with pytest.raises(DPError,match='QUERY_KIND'):r.page('native.wrong')
 with pytest.raises(DPError,match='QUERY_SCOPE'):r.page('native.unit',document_id='foreign')
 assert c==m==[]
