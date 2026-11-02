"""Real local Oracle source+record SQL through the actual frozen service entry.

Only authenticated host identity and model/network responses are fixtures.
Source publication lives in a temporary NO AUTHENTICATION Oracle owner, and
Agent records use their own unique scope in the existing SIDDA tables.
"""
from pathlib import Path
import asyncio
import importlib.util
import json
import os
import sys
import re
import sqlite3
import time
import uuid

import pytest
import yaml

from test_records import LocalOracle,ROOT
from test_oracle_dp_runtime import published
from test_compact_v2_rag import structured_generation
from semantic_runtime import oracle_dp_io as io,oracle_query_catalog as catalogue
from semantic_runtime.physical_mapping import SchemaMap
from lawrag.pipeline.oracle_query_publish import publish

CODE=Path(os.environ['WORKFLOW_TEST_CODE_ROOT'])

@pytest.fixture
def native_oracle(published,tmp_path,monkeypatch):
    remote,original,generation=published
    sp=importlib.util.spec_from_file_location('oracle_service_admin',ROOT/'06_TOOLS/maintenance/agent_record_oracle_r2.py')
    admin=importlib.util.module_from_spec(sp);sp.loader.exec_module(admin)
    db=admin.connection();client=LocalOracle(db)
    owner='A8_AREC_'+uuid.uuid4().hex[:12].upper();channel='agent-'+uuid.uuid4().hex[:12]
    namespace='service-'+uuid.uuid4().hex
    value=yaml.safe_load((CODE/'00_SYSTEM/ORACLE/physical_mapping.yaml').read_text())
    for role in value['profiles']['dev_silver']['owner_by_role']:
        value['profiles']['dev_silver']['owner_by_role'][role]='SIDDA' if role=='agent' else owner
    mapping_file=tmp_path/'fixture-physical-map.yaml';mapping_file.write_text(yaml.safe_dump(value,allow_unicode=True,sort_keys=False))
    client.schema_map=SchemaMap.load(mapping_file)
    try:
        with db.cursor() as c:
            c.execute('CREATE USER '+owner+' NO AUTHENTICATION DEFAULT TABLESPACE USERS QUOTA 64M ON USERS')
            for kind,key,name,sql in client.schema_map.ddl():
                if key!='query_state':c.execute(sql)
        sql=io.SQL(client,journal=tmp_path/'source-preparation.jsonl',binding='local-source-records')
        client.schema_map.preflight(sql)
        for kind,items in remote.data.items():
            values=list(items.values())
            for start in range(0,len(values),20):
                statement,binds=io.insert_statement(kind,values[start:start+20],sql=sql)
                sql.request(statement,binds,write=True)
        n=client.schema_map.names('source_release');old=remote.releases[original['release_id']]
        sql.request(f"BEGIN INSERT INTO {n.table}({n.c('RELEASE_ID')},{n.c('DATASET_VERSION')},{n.c('RELEASE_JSON')}) "
            'VALUES(:r,:v,:body); COMMIT; END;',
            [('r',original['release_id'],'VARCHAR2'),('v',old['v'],'VARCHAR2'),('body',old['body'],'CLOB')],write=True)
        result=publish(client,generation=generation,source_release_id=original['release_id'],target_binding='local-source-records',directory=tmp_path/'query-publication')
        catalogue.activate(sql,channel,result['release_id'],expected_revision=0)
        generation.rename(tmp_path/'dataiku-preparation-offline')
        monkeypatch.setenv('DP','oracle');monkeypatch.setenv('DP_QUERY_CHANNEL',channel)
        monkeypatch.setenv('GENOS_RAG_IMPLEMENTATION','legal-agent-unified-v6')
        monkeypatch.setenv('GENOS_ORACLE_AGENT_NAMESPACE',namespace)
        monkeypatch.delenv('GENOS_RUNTIME_DIR',raising=False)
        monkeypatch.setenv('GENOS_RUNTIME_LIMIT_MIB','250');monkeypatch.setenv('GENOS_RUNTIME_RESERVE_MIB','4')
        for key in ('GENOS_SHARED_LOG_DIR','GENOS_STATE_DIR','DP_QUERY_RELEASE_ID','GENOS_RAG_INITIAL_SEARCH'):
            monkeypatch.delenv(key,raising=False)
        yield client,generation,namespace
    finally:
        db.rollback()
        scope=io.digest({'format':'oracle-agent-namespace-v1','namespace':namespace})
        with db.cursor() as c:
            for table in ('LGL_AGT_REC_A','LGL_AGT_RUN_A','LGL_EXEC_ST_A','LGL_AGT_BODY_A'):
                c.execute('DELETE FROM SIDDA.'+table+' WHERE SCOPE_HASH_VAL=:scope',scope=scope)
            db.commit()
            c.execute('SELECT AUTHENTICATION_TYPE FROM DBA_USERS WHERE USERNAME=:owner',owner=owner)
            found=c.fetchone()
            if found:
                assert found==('NONE',) and re.fullmatch('A8_AREC_[0-9A-F]{12}',owner)
                c.execute('DROP USER '+owner+' CASCADE')
        db.close()

@pytest.mark.parametrize('capture',[False,True],ids=['case-v3','shortcut-v4'])
def test_actual_service_uses_only_oracle_without_a_runtime_mount(native_oracle,tmp_path,monkeypatch,capture):
    client,generation,namespace=native_oracle
    from semantic_runtime import detailed_log_storage as details,request_report
    logs=tmp_path/'synthetic-nfs-logs';monkeypatch.setenv('GENOS_SHARED_LOG_DIR',str(logs))
    if capture:
        def unavailable(path):raise OSError('synthetic unavailable NFS')
        monkeypatch.setattr(details,'require_nfs',unavailable)
    else:monkeypatch.setattr(details,'require_nfs',lambda p:Path(p).resolve())
    import test_unified_legal_agent as cases
    from test_bounded_source_main import settings
    from semantic_runtime import oracle_query_service as serving,app as application
    if os.environ.get('ADR1244_ROOT_ENTRY')=='1':
        sys.path.insert(0,str(ROOT))
        import service as entry
        assert importlib.import_module('service.service') is entry
        assert Path(entry.__file__).resolve()==ROOT/'service.py'
        monkeypatch.setattr(entry,'_APP',None);monkeypatch.setattr(entry,'_BINDING',None)
    else:
        sp=importlib.util.spec_from_file_location('oracle_only_native_service_'+uuid.uuid4().hex,CODE/'service.py')
        entry=importlib.util.module_from_spec(sp);sp.loader.exec_module(entry)
    monkeypatch.setattr(entry,'_provider',lambda *args:object())
    gateway=entry._ad_control
    class ScopedGateway:
        def __init__(self,real):self.real=real
        def __getattr__(self,name):return getattr(self.real,name)
        def intercept(self,data,runtime,*args):
            assert str(runtime)=='/__oracle_agent__/runtime','Administration runtime diverged from the Oracle Factory'
            return self.real.intercept(data,runtime,*args)
        def start_worker(self,runtime,*args):
            assert str(runtime)=='/__oracle_agent__/runtime','Worker runtime diverged from the Oracle Factory'
            return self.real.start_worker(runtime,*args)
    monkeypatch.setattr(entry,'_ad_control',lambda:ScopedGateway(gateway()))
    transport=cases.ScriptedTransport()
    monkeypatch.setattr(entry,'_genos_v5_environment_binding',lambda *args:({**settings(),'max_model_attempts':40},transport))
    monkeypatch.setattr(serving,'client_from_environment',lambda:client)
    monkeypatch.setattr(serving.Factory,'start_recovery',lambda self:None)
    create=application.create_app
    def with_identity(*args,**kwargs):
        kwargs['memory_identity']=lambda request:{'user_id':'u','team_id':'risk_team','document_ids':['d']}
        app=create(*args,**kwargs)
        app.state.pipeline.contracts.pipeline['shortcut_v4']['features']['capture']=capture
        return app
    monkeypatch.setattr(application,'create_app',with_identity)
    monkeypatch.setattr(entry,'_local_release',lambda:pytest.fail('Oracle fell back to a local/NFS generation'))
    connect=sqlite3.connect
    def only_memory(database,*args,**kwargs):
        assert str(database)==':memory:' or 'mode=memory' in str(database),'serving attempted a persistent SQLite database: '+str(database)
        return connect(database,*args,**kwargs)
    monkeypatch.setattr(sqlite3,'connect',only_memory)
    runtime='/__oracle_agent__/runtime'
    original_open=os.open
    def no_runtime_fd(path,*args,**kwargs):
        if not isinstance(path,int):assert not str(path).startswith(runtime),'runtime filesystem FD escaped the Oracle adapter'
        return original_open(path,*args,**kwargs)
    monkeypatch.setattr(os,'open',no_runtime_fd)
    with serving.request_context():entry.application()
    def call(value):return asyncio.run(entry.service({},value))
    health=call({'API_TYPE':'HEALTH'})
    assert health['status']==200,health
    assert entry._BINDING['state_storage']=='oracle' and entry._BINDING['persistent_sqlite'] is False
    section=call({'op':'call','method':'GET','path':'/v1/rag/section','params':{'doc_id':'d','node':'0'}})
    assert section['status']==200,section
    response=call({'op':'call','method':'POST','path':'/v1/rag/ask','json':{
        'question':'모의승인규정 제1조의 승인 대상은?','session_id':'s','request_id':'oracle-main-r1','use_llm':True}})
    assert response['status']==200,response
    assert response['body'].get('answer') or response['body'].get('text'),response
    phases=list(transport.phases)
    retry=call({'op':'call','method':'POST','path':'/v1/rag/ask','json':{
        'question':'모의승인규정 제1조의 승인 대상은?','session_id':'s','request_id':'oracle-main-r1','use_llm':True}})
    assert retry['status']==200 and retry['body']['answer']==response['body']['answer'],retry
    assert transport.phases==phases,'A committed request was dispatched to the model twice'
    run_id=response['body']['run_id']
    def source_page(path,params):
        import httpx
        with serving.request_context():
            app=entry.application()
            async def read():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://oracle-contract') as http:
                    return await http.get(path,params=params)
            return asyncio.run(read())
    candidates=source_page('/v1/rag/source-candidates',{'run_id':run_id})
    assert candidates.status_code==200,candidates.text
    assert response['body']['retrieval']['candidates'],'The published v6 answer lost its acquired original sources'
    from semantic_runtime import request_journals,runtime_sqlite,oracle_runtime_paths as paths
    with serving.request_context():
        factory=entry._oracle_factory();factory.request()
        journals=request_journals.paths(runtime,run_id);assert len(journals)==1
        db=runtime_sqlite.connect(journals[0],isolation_level=None)
        assert request_journals.scope(db,run_id)[0]==frozenset(['d'])
        assert db.execute('SELECT status FROM publication').fetchone()[0]=='PUBLISHED'
        for attempt in db.execute('SELECT request_json,response_json FROM model_attempt'):
            assert details.is_reference(json.loads(attempt[0]))
            assert 'stream_events' not in json.loads(attempt[1]) if attempt[1] else True
        authority=db.execute('SELECT case_db FROM case_commit').fetchone()[0]
        db.close()
        from semantic_runtime.legal_agent import journal_storage
        case=journal_storage.connect(authority,isolation_level=None)
        raw=case.execute("SELECT payload FROM node WHERE stage='READ' ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert json.loads(raw)['originals'],'Oracle case READ lost its acquired original sources'
        case.close()
        if capture:assert list(paths.Path(runtime).glob('case-memory/wikis/**/CURRENT.json')),'The derived wiki pointer was not persisted to Oracle'
    assert not Path(runtime).exists(),'Oracle mode created its logical runtime on disk'
    scope=io.digest({'format':'oracle-agent-namespace-v1','namespace':namespace})
    with client.db.cursor() as c:
        c.execute('SELECT COUNT(*) FROM SIDDA.LGL_AGT_RUN_A WHERE SCOPE_HASH_VAL=:scope',scope=scope)
        assert c.fetchone()[0]>0
        c.execute('SELECT COUNT(*) FROM SIDDA.LGL_AGT_REC_A WHERE SCOPE_HASH_VAL=:scope AND REC_KIND_CD LIKE \'SQLROW:%\'',scope=scope)
        assert c.fetchone()[0]>0
    assert not client.errors,client.errors
    assert details.drain(timeout=15)
    until=time.monotonic()+45
    while request_report._FINALIZER_QUEUE.unfinished_tasks and time.monotonic()<until:time.sleep(.01)
    assert request_report._FINALIZER_QUEUE.unfinished_tasks==0,'Detailed report worker did not finish'
    if not capture:assert list(logs.rglob('*.json.gz')) and list(logs.rglob('*.trace.txt'))
    else:assert not logs.exists(),'Unavailable NFS silently became a local directory'
