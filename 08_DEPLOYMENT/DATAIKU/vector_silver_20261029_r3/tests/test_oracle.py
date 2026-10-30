"""Real local Oracle VECTOR; generated embeddings are deterministic fixtures."""
import hashlib
import json
import math
import secrets
import subprocess
import time
from types import SimpleNamespace as N

import oracledb
import pytest
from lawrag.pipeline.oracle_query_dataiku import render
from semantic_runtime.initial_vector import Repository,VectorError,VectorUnavailable
from semantic_runtime.oracle_dp_io import digest
from vector_silver.publisher import Publisher
from vector_silver.schema import ensure,validate

@pytest.fixture(scope='module')
def database():
    info=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
    assert info['Config']['Labels']['a8.task']=='legal-mapped-20261023'
    secret=dict(x.split('=',1) for x in info['Config']['Env'])['ORACLE_PASSWORD']
    admin=oracledb.connect(dsn='127.0.0.1:11524/FREEPDB1',user='system',password=secret)
    user='A8_VS_'+secrets.token_hex(5).upper();pw=secrets.token_hex(24)
    with admin.cursor() as c:
        c.execute('CREATE USER '+user+' IDENTIFIED BY "'+pw+'" DEFAULT TABLESPACE USERS QUOTA 64M ON USERS')
        c.execute('GRANT CREATE SESSION,CREATE TABLE TO '+user)
    conn=oracledb.connect(dsn='127.0.0.1:11524/FREEPDB1',user=user,password=pw)
    class SQL:
        deadline=time.monotonic()+600;calls=0
        def __init__(self):self.history=[]
        def query(self,q,binds=(),limit=100):
            self.calls+=1;self.history.append(('query',q))
            with conn.cursor() as c:
                c.execute(render(q,binds));names=[x[0] for x in c.description]
                rows=[{n:v.read() if hasattr(v,'read') else v for n,v in zip(names,row)} for row in c.fetchall()]
            assert len(rows)<=limit
            return rows
        def request(self,q,binds=(),write=False,limit=100):
            self.calls+=1
            compiled=render(q,binds,write=write);self.history.append(('request',compiled))
            with conn.cursor() as c:c.execute(compiled)
    sql=SQL()
    sql.new_connection=lambda:oracledb.connect(dsn="127.0.0.1:11524/FREEPDB1",user=user,password=pw)
    try:yield sql,user,conn
    finally:
        conn.close()
        with admin.cursor() as c:c.execute('DROP USER '+user+' CASCADE')
        admin.close()

def config(revision='fixture'):
    return {'schema_version':'legal-vector-profile-v1','model':'fixture','revision':revision,'dimensions':1024,
            'endpoint_sha256':hashlib.sha256(b'https://example.invalid/embedding').hexdigest(),
            'chunk_chars':800,'overlap_chars':100,'normalization':'l2','metric':'COSINE'}

class Encoder:
    calls=0
    def encode(self,texts):
        self.calls+=1
        return [[1.0]+[0.0]*1023 for _ in texts]

def rows():
    out=[]
    for i in range(33):
        meta={'document_id':'d' if i<32 else 'secret','source_id':'root'+str(i//2),'unit_id':'2','block_id':str(i),
              'start':0,'end':20,'source_sha256':digest('source'),'block_sha256':digest('body'),'input_sha256':digest(str(i))}
        out.append({'id':digest(['segment',i]),'meta':meta,'text':'원문'+str(i)})
    return out

def request(sql):return N(sql=sql,release_id='a'*64,snapshot=N(release_id='b'*64,dataset_version='c'*64),sources=N(allowed={'d','secret'}))

def test_native_schema_idempotent_and_metadata(database):
    sql,user,conn=database
    assert ensure(sql,user)=={'tables':2,'columns':6,'native_vector':True}
    assert ensure(sql,user)['columns']==6
    assert len(sql.query('SELECT COLUMN_NAME FROM ALL_COL_COMMENTS WHERE OWNER=:o AND COMMENTS IS NOT NULL', [('o',user,'VARCHAR2')],limit=100))==6

def test_native_publish_search_resume_failure_and_conflict(database):
    sql,user,conn=database
    ensure(sql,user)
    enc=Encoder();p=Publisher(request(sql),config(),encoder=enc,owner=user)
    result=p.build(items=rows())
    assert result['count']==33 and enc.calls==3 and result['active']
    repo=Repository(sql,user)
    found=repo.search(p.pub,[1.0]+[0.0]*1023,{'d'},limit=100)
    assert len(found)==16 and all(r['DOC_ID']=='d' for r in found)
    enc2=Encoder();again=Publisher(request(sql),config(),encoder=enc2,owner=user).build(items=rows())
    assert again['reused']==33 and enc2.calls==0
    class Fail(Encoder):
        def encode(self,t):
            if self.calls==1:raise VectorUnavailable('fixture failure')
            return super().encode(t)
    broken=Publisher(request(sql),config('next'),encoder=Fail(),owner=user)
    with pytest.raises(VectorUnavailable):broken.build(items=rows())
    assert repo.read(broken.pub)['STATUS']=='BUILDING' and repo.active('a'*64)['PUB_ID']==p.pub
    resumed=Publisher(request(sql),config('next'),encoder=Encoder(),owner=user).build(items=rows())
    assert resumed['reused']==16 and resumed['embedding_calls']==2
    assert repo.active('a'*64)['REVISION']==2
    altered=rows();altered[0]['meta']['input_sha256']='f'*64
    with pytest.raises(VectorError,match='mismatch'):
        Publisher(request(sql),config('next'),encoder=Encoder(),owner=user).build(items=altered)
    # Bound INSERT blocks after rendering; no scalar existence lookup per segment.
    inserts=[q for kind,q in sql.history if kind=='request' and 'INSERT INTO '+repo.s in q]
    assert inserts and all(len(q.encode())<=60000 for q in inserts)
    assert any(q.count('INSERT INTO '+repo.s)>1 for q in inserts)
    assert all('SEG_ID IN (' in q for kind,q in sql.history if kind=='query' and 'SELECT SEG_ID,DOC_ID' in q)

def test_native_wrong_schema_is_rejected_without_recreation(database):
    sql,user,conn=database
    with conn.cursor() as c:c.execute('ALTER TABLE '+user+'.LGL_VCTR_ITEM_S ADD EXTRA_FIELD NUMBER')
    try:
        with pytest.raises(VectorError,match='COLUMNS'):validate(sql,user)
    finally:
        with conn.cursor() as c:c.execute('ALTER TABLE '+user+'.LGL_VCTR_ITEM_S DROP COLUMN EXTRA_FIELD')
    assert validate(sql,user)['columns']==6

def test_native_dense_vectors_split_bounded_transactions(database):
    sql,user,conn=database
    class Dense(Encoder):
        def encode(self,texts):
            self.calls+=1
            return [[math.sin(i+1) for i in range(1024)] for _ in texts]
    before=len(sql.history)
    p=Publisher(request(sql),config('dense'),encoder=Dense(),owner=user)
    result=p.build(items=rows()[:16],activate=False)
    inserts=[q for kind,q in sql.history[before:] if kind=='request' and 'INSERT INTO '+p.repo.s in q]
    assert result['count']==16 and 1<len(inserts)<16
    assert all(len(q.encode())<=60000 for q in inserts)
    assert len(Repository(sql,user).search(p.pub,[math.sin(i+1) for i in range(1024)],{'d'},limit=20))==8

def test_native_loss_of_lease_rolls_back_entire_batch(database):
    sql,user,conn=database
    ensure(sql,user)
    p=Publisher(request(sql),config('atomic'),encoder=Encoder(),owner=user)
    p.execute(f"INSERT INTO {p.repo.r}(PUB_ID,PAYLOAD_JSON) VALUES(:p,:m);",
              [('p',p.pub,'VARCHAR2'),('m',json.dumps({'manifest':p.manifest,'status':'BUILDING','lease':p.lease}),'CLOB')])
    # The second duplicate PK fails after first INSERT in the same PL/SQL block.
    duplicate=[rows()[0],rows()[0]]
    with pytest.raises(oracledb.DatabaseError):p.insert_many(duplicate,Encoder().encode(['one','two']))
    assert sql.query(f'SELECT COUNT(*) AS N FROM {p.repo.s} WHERE PUB_ID=:p',[('p',p.pub,'VARCHAR2')],limit=1)[0]['N']==0

def test_recipe_entrypoint_check_build_resume_with_native_db(database,monkeypatch):
    import sys
    import types
    import pandas as pd
    from test_contracts import Folder,receipt
    import vector_silver.runtime as runtime
    sql,user,conn=database
    ensure(sql,user)
    profile=config('runtime')
    profile['endpoint_sha256']=hashlib.sha256(b'https://example.invalid/api/gateway/rep/serving/3').hexdigest()
    variables={'LEGAL_VECTOR_PROFILE':profile,'GENOS_BASE_URL':'https://example.invalid',
               'GENOS_EMBED_SERVING_ID':'3','GENOS_EMBED_KEY':'fixture'}
    upstream=Folder({'jobs/a/complete.json':json.dumps(receipt()).encode()});output=Folder()
    class Executor:
        def query_to_df(self,q,pre_queries=(),post_queries=(),**kw):
            with conn.cursor() as c:
                for s in pre_queries:c.execute(s)
                c.execute(q);names=[x[0] for x in c.description]
                values=[[v.read() if hasattr(v,'read') else v for v in row] for row in c.fetchall()]
                for s in post_queries:c.execute(s)
            return pd.DataFrame(values,columns=names)
    fake=types.ModuleType('dataiku')
    fake.get_custom_variables=lambda:variables
    fake.SQLExecutor2=lambda **kw:Executor()
    fake.default_project_key=lambda:'LEGAL_RAG'
    fake.Folder=lambda id:{'load':upstream,'out':output}[id]
    monkeypatch.setitem(sys.modules,'dataiku',fake)
    snapshot=N(release_id='b'*64,dataset_version='c'*64,excluded=set(),manifest={'scope':{'document_version_ids':['d']},'navigation':{'path':'navigation'}})
    manifest={'source_release_id':'b'*64,'dataset_version':'c'*64,'source_manifest':snapshot.manifest,'tables':{'source.integrity':{}}}
    monkeypatch.setattr(runtime,'select_release',lambda *a,**k:{'release_id':'a'*64,'revision':None,'manifest':manifest})
    monkeypatch.setattr(runtime,'Snapshot',N(open=lambda *a:snapshot))
    source={'document_id':'d','id':'runtime-source','unit_id':'1','document_name':'검증문서','heading':'제1조','blocks':[{'block_id':'1'}]}
    def source_request(s,q,rev,snap,m,docs):
        return N(sql=s,release_id=q,snapshot=snap,sources=N(allowed=docs,sources=lambda *a:[{'block_id':'1','text':'가'*1901}]),
                 records=N(page=lambda *a,**k:{'rows':[{'json':json.dumps(source)}],'next':None}))
    monkeypatch.setattr(runtime,'_request',source_request)
    monkeypatch.setattr(runtime,'validate',lambda s:validate(s,user))
    class RuntimeEncoder(Encoder):
        def __init__(self,*a,**k):self.calls=0
    monkeypatch.setattr(runtime,'Encoder',RuntimeEncoder)
    monkeypatch.setattr(runtime,'Publisher',lambda *a,**k:Publisher(*a,owner=user,**k))
    cfg={'load':'load','output':'out'}
    checked=runtime.run(cfg,action='check')
    assert checked['embedding_calls']==0 and not any('build-state' in p for p in output.values)
    result=runtime.run(cfg,action='build')
    assert result['status']=='READY' and result['count']==3 and result['embedding_calls']==1
    again=runtime.run(cfg,action='build')
    assert again['reused']==3 and again['embedding_calls']==1
    state=[json.loads(v) for p,v in output.values.items() if 'build-state' in p][0]
    assert state['sql_reserved']>=state['sql_calls'] and state['status']=='READY'
    assert any('timing-' in p for p in output.values)
    from semantic_runtime.oracle_query import QuerySQL
    from semantic_runtime.initial_vector import Retriever
    from semantic_runtime.physical_mapping import SchemaMap
    from pathlib import Path
    mapping=SchemaMap.load(Path(__file__).resolve().parents[1]/'payload/00_SYSTEM/ORACLE/physical_mapping.yaml')
    client=runtime.DataikuClient(Executor(),'AIDP','LEGAL_RAG',schema_map=mapping)
    serving=QuerySQL(client,binding='fixture',deadline=time.monotonic()+60)
    selected=source_request(serving,'a'*64,None,snapshot,manifest,{'d'})
    retriever=Retriever(selected,encoder_factory=RuntimeEncoder,owner=user)
    found=retriever.search('질문',{'d'})
    assert len(found['rows'])==1 and found['rows'][0]['SOURCE_ID']=='runtime-source'
    before=serving.calls
    assert retriever.search('질문',{'d'})==found and serving.calls==before
    with pytest.raises(VectorError,match='cannot widen'):retriever.search('질문',{'secret'})


def test_core_publisher_also_uses_six_columns(database):
    from semantic_runtime.vector_publish import Publisher as CorePublisher
    sql,user,conn=database
    p=CorePublisher(request(sql),config('core-six'),encoder=Encoder(),owner=user)
    result=p.build(items=rows(),activate=False)
    assert result['count']==33
    assert Repository(sql,user).read(p.pub)['PROFILE_JSON']==config('core-six')

def test_previous_schema_preserved(database):
    sql,user,conn=database
    with conn.cursor() as c:
        c.execute('CREATE TABLE '+user+'.LGL_VCTR_PBLS_S (MARKER VARCHAR2(10))')
        c.execute("INSERT INTO "+user+".LGL_VCTR_PBLS_S VALUES('keep')")
        conn.commit()
    assert ensure(sql,user)['columns']==6
    assert sql.query('SELECT MARKER FROM '+user+'.LGL_VCTR_PBLS_S',limit=1)==[{'MARKER':'keep'}]


def test_partial_hidden_busy_lease_and_stale_activation(database):
    from semantic_runtime.initial_vector import LEASE,STATUS
    sql,user,conn=database
    q=request(sql);q.release_id='e'*64
    p=Publisher(q,config('concurrent-a'),encoder=Encoder(),owner=user)
    p.execute(f"INSERT INTO {p.repo.r}(PUB_ID,PAYLOAD_JSON) VALUES(:p,:m);",
              [('p',p.pub,'VARCHAR2'),('m',json.dumps({'manifest':p.manifest,'status':'BUILDING','lease':'other'}),'CLOB')])
    with pytest.raises(oracledb.DatabaseError,match='VECTOR_BUILD_BUSY'):p.build(items=rows())
    assert Repository(sql,user).active(q.release_id) is None and p.encoder.calls==0
    with pytest.raises(VectorError,match='not READY'):p.repo.search(p.pub,[1]+[0]*1023,{'d'})
    assert p.repo.read(p.pub)['LEASE_ID']=='other'
    p.execute(f"UPDATE {p.repo.r} SET PAYLOAD_JSON=JSON_MERGEPATCH(PAYLOAD_JSON,'{{\"lease\":null}}' RETURNING CLOB) WHERE PUB_ID=:p;",[('p',p.pub,'VARCHAR2')])
    p.build(items=rows())
    old=p.repo.active(q.release_id)
    p2=Publisher(q,config('concurrent-b'),encoder=Encoder(),owner=user)
    p2.build(items=rows())
    with pytest.raises(oracledb.DatabaseError,match='VECTOR_ACTIVE_CONFLICT'):p.activate(old)
    assert p.repo.active(q.release_id)['PUB_ID']==p2.pub
    p.activate(p.repo.active(q.release_id))
    assert p.repo.active(q.release_id)['PUB_ID']==p.pub and p.repo.active(q.release_id)['REVISION']==3
    with pytest.raises(oracledb.DatabaseError,match='VECTOR_ACTIVE_CONFLICT'):p2.activate(old)
    assert p.repo.active(q.release_id)['REVISION']==3


def test_json_acl_escaping_scope_and_invalid_metadata(database):
    sql,user,conn=database
    q=request(sql);q.release_id='f'*64;q.sources.allowed={"문서' OR 1=1 --",'secret'}
    item=rows()[0];item['meta']['document_id']="문서' OR 1=1 --";item['meta']['source_id']="source'한글"
    p=Publisher(q,config('escaped'),encoder=Encoder(),owner=user)
    p.build(items=[item,rows()[-1]])
    assert len(p.repo.search(p.pub,[1]+[0]*1023,{"문서' OR 1=1 --"},["source'한글"]))==1
    assert p.repo.search(p.pub,[1]+[0]*1023,{'missing'})==[]
    assert p.repo.search(p.pub,[1]+[0]*1023,{'secret'},[])==[]
    bad=Publisher(q,config('bad-scope'),encoder=Encoder(),owner=user)
    with pytest.raises(VectorError,match='BUILD_SCOPE'):bad.build(items=rows()[:1])
    assert bad.encoder.calls==0 and bad.repo.read(bad.pub)['STATUS']=='BUILDING'


def test_real_transaction_lock_conflict_is_bounded(database):
    sql,user,conn=database
    q=request(sql);q.release_id='d'*64
    p=Publisher(q,config('lock'),encoder=Encoder(),owner=user)
    p.build(items=rows(),activate=False)
    second=sql.new_connection()
    try:
        with second.cursor() as c:c.execute('LOCK TABLE '+p.repo.r+' IN EXCLUSIVE MODE NOWAIT')
        with pytest.raises(oracledb.DatabaseError,match='ORA-00054'):p.activate(None)
        assert p.repo.active(q.release_id) is None
    finally:second.rollback();second.close()
    p.activate(None)
    assert p.repo.active(q.release_id)['PUB_ID']==p.pub


def test_misnamed_json_index_rejected(database):
    from semantic_runtime.initial_vector import ddl
    sql,user,conn=database
    with conn.cursor() as c:
        c.execute('DROP INDEX '+user+'.LGL_VCTR_ITEM_IX_S')
        c.execute('CREATE INDEX '+user+'.LGL_VCTR_ITEM_IX_S ON '+user+".LGL_VCTR_ITEM_S(PUB_ID,JSON_VALUE(META_JSON,'$.wrong'))")
    try:
        with pytest.raises(VectorError,match='INDEX_EXPRESSION'):validate(sql,user)
    finally:
        with conn.cursor() as c:
            c.execute('DROP INDEX '+user+'.LGL_VCTR_ITEM_IX_S')
            c.execute(next(s for s in ddl(user) if 'CREATE INDEX' in s))
    assert validate(sql,user)['columns']==6
