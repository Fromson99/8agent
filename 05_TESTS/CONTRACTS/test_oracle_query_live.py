"""Opt-in Oracle Free SQL contracts; only the labelled local disposable DB.

No GENOS/production connection settings are read. Ordinary CI skips this file.
Run with A8_ORACLE_QUERY_LIVE=1 after starting the task's isolated container.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import pytest

from test_oracle_dp_runtime import published
from test_compact_v2_rag import structured_generation
from test_genos_compact_service_boot import entry
from semantic_runtime import oracle_dp_io as io
from semantic_runtime import oracle_query_catalog as q
from semantic_runtime.oracle_query_request import open_request
from lawrag.pipeline.oracle_query_publish import publish, schema


pytestmark = pytest.mark.skipif(os.environ.get('A8_ORACLE_QUERY_LIVE')!='1',reason='explicit local Oracle SQL contract run only')


class LocalOracleORDS:
    """Execute exact maintained SQL; only the HTTP envelope is replaced."""
    SQL_PATH = '/local-contract-sql'

    def __init__(self, connection, driver):
        self.connection, self.driver = connection, driver
        self.errors = []
        self.truncate_lob = False

    def request(self, method, path, json):
        assert (method,path)==('POST',self.SQL_PATH)
        types={'CLOB':self.driver.DB_TYPE_CLOB,'VARCHAR2':self.driver.DB_TYPE_VARCHAR,'NUMBER':self.driver.DB_TYPE_NUMBER}
        binds=json.get('binds',[])
        try:
            with self.connection.cursor() as cursor:
                cursor.setinputsizes(**{b['name']:types[b['data_type']] for b in binds})
                cursor.execute(json['statementText'],{b['name']:b['value'] for b in binds})
                if cursor.description is None:
                    return {'items':[{'result':cursor.rowcount}]}
                names=[c[0] for c in cursor.description]
                rows=cursor.fetchmany(json['limit']+1)
                def value(v):
                    if isinstance(v,self.driver.LOB):
                        text=v.read()
                        return text[:100] if self.truncate_lob else text
                    return v
                return {'items':[{'resultSet':{'offset':0,'hasMore':len(rows)>json['limit'],
                    'items':[{k:value(v) for k,v in zip(names,row)} for row in rows[:json['limit']]]}}]}
        except self.driver.DatabaseError as exc:
            error=exc.args[0]
            self.errors.append({'code':error.code,'message':error.message})
            return {'items':[{'errorCode':error.code}]}


@pytest.fixture
def live_oracle():
    driver=pytest.importorskip('oracledb')
    container='a8-oracle-query-contract-20261019'
    inspected=subprocess.run(['docker','inspect',container],capture_output=True,text=True,check=True)
    details=json.loads(inspected.stdout)[0]
    assert details['Config']['Labels']['a8.task']=='oracle-query-contract-20261019'
    endpoint=details['NetworkSettings']['Ports']['1521/tcp']
    assert len(endpoint)==1 and endpoint[0]['HostIp']=='127.0.0.1'
    connection=driver.connect(user='SIDDA',password=Path('/tmp/a8-oracle-query-docker-config/test-db-password').read_text(),
        dsn='127.0.0.1:'+endpoint[0]['HostPort']+'/FREEPDB1')
    client=LocalOracleORDS(connection,driver)
    try:
        yield client
    finally:
        connection.close()
        assert not client.errors,client.errors


def test_live_publish_pin_scope_unicode_state_and_pointer(live_oracle,published,tmp_path,monkeypatch,entry):
    remote,original,generation=published
    sql=io.SQL(live_oracle,journal=tmp_path/'dataiku-live.jsonl',binding='local-disposable')
    assert schema(sql,create=True)['status']=='READY'
    assert schema(sql)['status']=='READY'
    with live_oracle.connection.cursor() as cursor:
        for kind,table in io.TABLES.items():
            cursor.execute("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME=:name",name=table)
            if cursor.fetchone()[0]:
                continue
            fields=[]
            for col in io.COLUMNS[kind]:
                typ='CLOB' if col in io.CLOBS else 'NUMBER' if col=='JSON_TEXT_ELIDED' else 'VARCHAR2(64 BYTE)' if col in ('DATASET_VERSION','SOURCE_ARTIFACT_SHA256') else 'VARCHAR2(512 BYTE)'
                fields.append(col+' '+typ+(' NOT NULL' if col in io.KEYS[kind] else ''))
            cursor.execute('CREATE TABLE SIDDA.'+table+'('+','.join(fields)+',PRIMARY KEY('+','.join(io.KEYS[kind])+'))')
        cursor.execute("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME='LEGAL_RAG_RELEASE_A'")
        if not cursor.fetchone()[0]:
            cursor.execute('CREATE TABLE SIDDA.LEGAL_RAG_RELEASE_A(RELEASE_ID VARCHAR2(64 BYTE) PRIMARY KEY,DATASET_VERSION VARCHAR2(64 BYTE),RELEASE_JSON CLOB)')
    for kind,rows in remote.data.items():
        values=list(rows.values())
        for start in range(0,len(values),20):
            statement,binds=io.insert_statement(kind,values[start:start+20])
            sql.request(statement,binds,write=True)
    old=remote.releases[original['release_id']]
    sql.request('BEGIN INSERT INTO SIDDA.LEGAL_RAG_RELEASE_A(RELEASE_ID,DATASET_VERSION,RELEASE_JSON) '
        'SELECT :r,:v,:body FROM DUAL WHERE NOT EXISTS(SELECT 1 FROM SIDDA.LEGAL_RAG_RELEASE_A WHERE RELEASE_ID=:r); COMMIT; END;',
        [('r',original['release_id'],'VARCHAR2'),('v',old['v'],'VARCHAR2'),('body',old['body'],'CLOB')],write=True)
    result=publish(live_oracle,generation=generation,source_release_id=original['release_id'],target_binding='local-disposable',directory=tmp_path/'query-live')
    release_id=result['release_id']
    channel='contract-'+uuid.uuid4().hex[:16]
    q.activate(sql,channel,release_id,expected_revision=0)
    request=open_request(live_oracle,connection_binding='local-disposable',document_ids=['d'],
        deadline=time.monotonic()+60,channel=channel)
    from semantic_runtime.oracle_query_fulltext import UnitIndex
    from semantic_runtime.unit_fulltext import UnitFulltextIndex
    navigation=json.loads((generation/'navigation/manifest.json').read_text())
    sqlite_index=UnitFulltextIndex(generation/'fulltext',navigation)
    oracle_index=UnitIndex(request)
    from semantic_runtime.oracle_query_store import Store as OracleStore
    oracle_store=OracleStore(request)
    assert oracle_store.db.execute('SELECT name FROM document WHERE document_id=?',('d',)).fetchone()[0]
    assert oracle_store.db.execute("SELECT document_id,json_extract(json,'$.document_metadata') FROM document").fetchall()
    assert oracle_store.source('d','0')['text']==request.sources.source('d','0')['text']
    assert request.restrict(['d']).sql is request.sql
    with pytest.raises(io.DPError,match='cannot widen'):
        request.restrict(['unauthorized'])
    from semantic_runtime.oracle_query_db import Connection
    import sqlite3
    with sqlite3.connect(generation/'navigation/navigation.sqlite') as local:
        port=Connection(request,'navigation/navigation.sqlite')
        for statement,parameters in [
            ('SELECT id,document_id,json FROM source WHERE document_id=? ORDER BY id',('d',)),
            ('SELECT COUNT(*) FROM source WHERE document_id=?',('d',)),
            ("SELECT id FROM source WHERE document_id IN (SELECT value FROM json_each(?)) ORDER BY id",('["d"]',)),
            ("SELECT json_extract(json,'$.heading') AS heading FROM source WHERE document_id=? ORDER BY id",('d',)),
        ]:
            expected=local.execute(statement,parameters).fetchall()
            assert [tuple(r) for r in port.execute(statement,parameters)]==expected
        assert port.execute('SELECT COUNT(*) FROM source').fetchone()[0]==local.execute("SELECT COUNT(*) FROM source WHERE document_id='d'").fetchone()[0]
        from semantic_runtime.oracle_query_index import Sources,SQLMap
        sources=Sources(request,port)
        scoped=sources.ids_for_documents(['d'])
        assert set(scoped)=={r[0] for r in local.execute("SELECT id FROM source WHERE document_id='d'")}
        for sid in scoped:
            assert sid in scoped
            assert sources[sid]==json.loads(local.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()[0])
        terms=SQLMap(port,'term')
        assert dict(terms.items())=={r[0]:json.loads(r[1]) for r in local.execute('SELECT id,json FROM term')}
    # Translator boundary: Oracle treats empty text as NULL, while existing
    # SQLite consumers distinguish them. Exercise both predicates and output,
    # plus CLOB text, against the real database rather than a SQL string mock.
    from types import SimpleNamespace
    from lawrag.pipeline.oracle_query_publish import _column_shapes
    shape={'asset':'contract','table':'sample','columns':{key:{'type':'null','max_bytes':0,
        'has_null':False,'has_empty':False} for key in ('id','label','body')}}
    values=[{'id':'a','label':'','body':'긴 원문 😀 '*1000},
            {'id':'b','label':None,'body':None},{'id':'c','label':'값','body':'짧은 원문'}]
    for value in values: _column_shapes(shape,value)
    sample_release=io.digest({'relational-test':uuid.uuid4().hex})
    q.insert_records(sql,sample_release,[q.record('contract.relational',value,key=value['id'],
        lookup_id=value['id'],document_id='d') for value in values])
    port=Connection(SimpleNamespace(sql=request.sql,release_id=sample_release,sources=request.sources,
        records=SimpleNamespace(manifest={'tables':{'contract.relational':shape}})),'contract')
    with sqlite3.connect(':memory:') as local:
        local.execute('CREATE TABLE sample(id TEXT,label TEXT,body TEXT)')
        local.executemany('INSERT INTO sample VALUES(?,?,?)',[(v['id'],v['label'],v['body']) for v in values])
        for statement,parameters in [
            ('SELECT id,label,body FROM sample ORDER BY id',()),
            ('SELECT id FROM sample WHERE label IS NULL ORDER BY id',()),
            ('SELECT id FROM sample WHERE label IS NOT NULL ORDER BY id',()),
            ('SELECT id FROM sample WHERE label=? ORDER BY id',('',)),
            ('SELECT id FROM sample WHERE label<>? ORDER BY id',('',)),
        ]:
            assert [tuple(row) for row in port.execute(statement,parameters)]==local.execute(statement,parameters).fetchall()
    with sqlite_index.connect() as sqlite_db:
        for terms in (['승인'],['이사회','승인'],['이사회 승인'],['없는 검색어']):
            expected=sqlite_index.rank_units(sqlite_db,terms)
            expected=[v for v in expected if v['document_id']=='d']
            actual=oracle_index.rank_units(oracle_index,terms)
            assert [r['key'] for r in actual]==[r['key'] for r in expected]
            assert [r['score'] for r in actual]==pytest.approx([r['score'] for r in expected],rel=1e-12,abs=1e-15)
            allowed={v['source_id'] for v in expected}
            assert oracle_index.law_groups_page(oracle_index,terms)==sqlite_index.law_groups_page(sqlite_db,terms,allowed)
    # Data-serving reads cannot accidentally open a source file or SQLite.
    with monkeypatch.context() as m:
        import sqlite3
        m.setattr(sqlite3,'connect',lambda *a,**k:pytest.fail('serving opened SQLite'))
        m.setattr(Path,'open',lambda *a,**k:pytest.fail('serving opened a local file'))
        source=request.sources.source('d','0')
        assert '승인' in source['text']
        assert request.sources.source_scope('d','0')['document_id']=='d'
        first=request.records.page('source.integrity',document_id='d',limit=1)
        second=request.records.page('source.integrity',document_id='d',limit=1,after=first['next'])
        assert first['rows'] != second['rows']
        first=request.sources.blocks('d',limit=1)
        request.sources.blocks('d',limit=1,after=first['next_after'])
        state=request.state(io.digest({'channel':channel}))
        assert state.put('test',{'text':'한글 😀','status':'RUNNING'},expected_revision=0)['revision']==1
        assert state.read('test')['value']['text']=='한글 😀'
        live_oracle.truncate_lob=True
        long_text='완전한 한글과 😀 원문 공백  \n'*1000
        state.put('test',{'text':long_text,'status':'COMPLETE'},expected_revision=1)
        assert state.read('test')['value']['text']==long_text
        live_oracle.truncate_lob=False
    assert request.pointer_revision==1
    assert q.activate(sql,channel,release_id,expected_revision=1,expected_release_id=release_id)['revision']==2
    assert request.pointer_revision==1
    generation.rename(tmp_path/'dataiku-source-offline')
    from semantic_runtime.app import create_app
    from fastapi.testclient import TestClient
    from semantic_runtime.document_agent import ServingDocumentAgent
    repository=Path(__file__).resolve().parents[2]
    from test_bounded_source_main import settings
    from test_unified_legal_agent import ScriptedTransport
    app=create_app(tmp_path/'runtime',None,contracts_root=repository,data_store=oracle_store,
                   implementation='legal-agent-unified-v6',vector=False,runtime_root=tmp_path/'runtime',
                   legal_agent_profile={**settings(),'max_model_attempts':40},legal_agent_transport=ScriptedTransport(),
                   memory_identity=lambda req:{'user_id':'u','team_id':'risk_team','document_ids':['d']})
    app.state.pipeline.contracts.pipeline['shortcut_v4']['features']['capture']=False
    client=TestClient(app)
    response=client.get('/health')
    assert response.status_code==200,response.text
    response=client.get('/v1/rag/documents')
    assert response.status_code==200,response.text
    agent=ServingDocumentAgent(app.state.pipeline,app.state.pipeline.term_agent.config)
    with agent.resources(['d']) as (_,tools,glossary,matcher):
        assert matcher.validate_structure(['d'])>0
        assert matcher.starts('모의승인규정 제1조', ['d'])['documents']
        assert tools.sources[next(iter(tools.sources))]['document_id']=='d'
        assert glossary.lookup('승인')['total']>=0
    response=client.post('/v1/rag/ask',json={'question':'모의승인규정 제1조의 승인 대상은?','session_id':'s','request_id':'oracle-live-r1'})
    assert response.status_code==200,response.text
    assert response.json()['status']=='READY',response.text
    assert response.json()['answer']['claims'],response.text
    # Exercise the actual JSON service entry. This local test substitutes only
    # the mount proof (no external NFS exists on CI), not the Oracle SQL port.
    import asyncio
    from semantic_runtime import oracle_query_service as serving,oracle_dp
    monkeypatch.setenv('DP','oracle')
    monkeypatch.setenv('DP_QUERY_CHANNEL',channel)
    monkeypatch.setenv('GENOS_RAG_IMPLEMENTATION','legal-agent-unified-v6')
    monkeypatch.setenv('AD_WORKER_ENABLED','0')
    monkeypatch.setattr(serving,'external_runtime',lambda:tmp_path/'service-state')
    monkeypatch.setattr(serving,'client_from_environment',lambda:live_oracle)
    monkeypatch.setattr(serving.Factory,'start_recovery',lambda self:None)
    monkeypatch.setattr(oracle_dp,'prepare',lambda *a,**k:pytest.fail('service restored Oracle data locally'))
    monkeypatch.setattr(entry,'_local_release',lambda:pytest.fail('Oracle fell back to local release'))
    health=asyncio.run(entry.service({}, {'API_TYPE':'HEALTH'}))
    assert health['status']==200,health
    assert entry._BINDING['mode']=='oracle-query'
    warm=entry._warm_resources()
    # Nothing is downloaded; published rows may be reused in process memory (shared-row cache, 2026-11-06).
    assert warm['source_downloaded'] is False
    assert warm['serving_data_cache'] == ('process-memory' if 'shared_rows' in warm else False)
    section=asyncio.run(entry.service({}, {'op':'call','method':'GET','path':'/v1/rag/section','params':{'doc_id':'d','node':'0'}}))
    assert section['status']==200 and '승인' in json.dumps(section,ensure_ascii=False),section
    search=asyncio.run(entry.service({}, {'API_TYPE':'RAG_SEARCH','q':'모의승인규정 제1조','doc_id':'d'}))
    assert search['status']==200,search
    assert not list((tmp_path/'service-state').rglob('store.sqlite'))
