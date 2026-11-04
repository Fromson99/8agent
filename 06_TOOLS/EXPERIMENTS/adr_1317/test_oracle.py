"""Real local Oracle G19 SQL and actual service entry, isolated test owners.

Only the ORDS HTTP envelope and embedding endpoint are replaced. Source files
are removed before serving. The endpoint fixture is not a model quality test.
"""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time

import pytest

from test_oracle_dp_runtime import published
from test_compact_v2_rag import structured_generation
from test_vector import PROFILE, environment
from semantic_runtime.oracle_development_mapping import DevelopmentMapping, PORTS, LOGICAL
from semantic_runtime.oracle_dp_io import canonical, digest, file_sha, DPError
from semantic_runtime.oracle_agent_records import AgentRecords, RecordSQL
from semantic_runtime.oracle_query_request import open_request
from semantic_runtime.oracle_query_vector import PublishedEncoder, Retriever


@pytest.fixture
def oracle(tmp_path):
    import oracledb
    oracledb.defaults.fetch_lobs = False
    info = json.loads(subprocess.check_output(['docker', 'inspect', 'a8-legal-mapped-20261023']))[0]
    assert info['State']['Running'] and info['Config']['Labels']['a8.task'] == 'legal-mapped-20261023'
    ep = info['HostConfig']['PortBindings']['1521/tcp']
    assert len(ep) == 1 and ep[0]['HostIp'] == '127.0.0.1'
    dsn = '127.0.0.1:' + ep[0]['HostPort'] + '/FREEPDB1'
    pw = dict(x.split('=', 1) for x in info['Config']['Env'])['ORACLE_PASSWORD']
    admin = oracledb.connect(user='system', password=pw, dsn=dsn)
    admin.call_timeout = 15000
    names = {k: 'A8_V1317_' + k + '_' + secrets.token_hex(3).upper() for k in ('S', 'A')}
    password = secrets.token_hex(24)
    evidence = {'created': [], 'dropped': [], 'sql': [], 'field_executed': False}
    conn = None
    try:
        with admin.cursor() as cur:
            for name in names.values():
                cur.execute('CREATE USER ' + name + ' IDENTIFIED BY "' + password + '" DEFAULT TABLESPACE USERS QUOTA 64M ON USERS')
                evidence['created'].append(name)
                cur.execute('GRANT CREATE SESSION,CREATE TABLE TO ' + name)
        root = Path(os.environ['LOOP_TEST_CODE_ROOT'])
        data = json.loads((root/'00_SYSTEM/ORACLE/development_g19_1.json').read_text())
        for table in data['tables'].values():
            table['owner'] = names['A' if table['owner'] == 'SIDDA' else 'S']
            table['columns'] = dict(reversed(list(table['columns'].items())))
        mapping_path = tmp_path/'mapping.json'
        mapping_path.write_text(json.dumps(data))
        mapping = DevelopmentMapping.load(mapping_path)
        with admin.cursor() as cur:
            for i, (key, table) in enumerate(data['tables'].items()):
                fields = [c['name']+' '+c['type']+(' DEFAULT '+c['default'] if c['default'] else '')+
                          (' NOT NULL' if c['required'] else '') for c in table['columns'].values()]
                fields.append('CONSTRAINT P'+str(i)+' PRIMARY KEY ('+','.join(table['columns'][c]['name'] for c in table['primary_key'])+')')
                cur.execute('CREATE TABLE '+mapping.physical_table(key)+' ('+','.join(fields)+')')
                if table['owner'] != names['S']:
                    cur.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON '+mapping.physical_table(key)+' TO '+names['S'])
        conn = oracledb.connect(user=names['S'], password=password, dsn=dsn)
        conn.call_timeout = 15000

        class Bridge:
            SQL_PATH = '/isolated-oracle-contract'
            schema_map = mapping
            def request(self, method, path, json):
                assert method == 'POST' and path == self.SQL_PATH
                stmt = json['statementText']
                evidence['sql'].append(stmt)
                types = {'CLOB': oracledb.DB_TYPE_CLOB, 'VARCHAR2': oracledb.DB_TYPE_VARCHAR, 'NUMBER': oracledb.DB_TYPE_NUMBER}
                with conn.cursor() as cur:
                    cur.setinputsizes(**{b['name']:types[b['data_type']] for b in json.get('binds', [])})
                    cur.execute(stmt, {b['name']:b['value'] for b in json.get('binds', [])})
                    if cur.description is None:
                        return {'items':[{'result':cur.rowcount}]}
                    columns = [c[0] for c in cur.description]
                    rows = cur.fetchmany(json['limit']+1)
                    return {'items':[{'resultSet':{'offset':0, 'hasMore':len(rows)>json['limit'],
                        'items':[dict(zip(columns, row)) for row in rows[:json['limit']]]}}]}

        def insert(key, values):
            table = data['tables'][key]
            columns = list(values)
            with conn.cursor() as cur:
                cur.setinputsizes(**{'b'+str(i):oracledb.DB_TYPE_CLOB for i,k in enumerate(columns) if table['columns'][k]['type']=='CLOB'})
                slots = [('TO_VECTOR(:b'+str(i)+')') if key=='VCTR_ITEM' and k=='EMBD_VCTR_VALU' else ':b'+str(i) for i,k in enumerate(columns)]
                cur.execute('INSERT INTO '+mapping.physical_table(key)+' ('+','.join(table['columns'][k]['name'] for k in columns)+
                            ') VALUES ('+','.join(slots)+')', {'b'+str(i):values[k] for i,k in enumerate(columns)})
        evidence['oracle_version'] = conn.version
        yield Bridge(), insert, conn, evidence
    finally:
        if conn:
            conn.close()
        with admin.cursor() as cur:
            for owner in evidence['created']:
                cur.execute('DROP USER '+owner+' CASCADE')
                evidence['dropped'].append(owner)
        admin.close()
        (tmp_path/'actual-oracle.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2))


def test_actual_main_oracle_source_search_vector_and_records(oracle, published, tmp_path, monkeypatch):
    client, insert, conn, evidence = oracle
    remote, original, generation = published
    from lawrag.pipeline import oracle_query_publish as pub, oracle_query_navigation_publish
    from semantic_runtime import navigation_match, structure_navigation, inherited_navigation
    from semantic_runtime.oracle_dp_assets import inventory
    source = json.loads(remote.releases[original['release_id']]['body'])
    for kind, rows in remote.data.items():
        key, aliases = PORTS[kind]
        for row in rows.values():
            insert(key, {old:('Y' if row[a] == 1 else 'N' if row[a] == 0 else None) if a == 'JSON_TEXT_ELIDED' else row[a]
                         for a,old in zip(aliases.split(), LOGICAL[key].split())})
    insert('SRC_POST', {'DOC_POST_HASH_VALU':original['release_id'], 'MNFST_HASH_VALU':source['dataset_version'], 'DOC_POST_IFMN_CTNT':canonical(source)})
    manifest, assets, tables = pub.describe(generation, source)
    _, inventory_assets = inventory(generation)
    value = {'schema_version':pub.SCHEMA, 'status':'COMPLETE', 'source_release_id':original['release_id'],
             'dataset_version':source['dataset_version'], 'source_manifest':manifest,
             'search_selection':source.get('search_selection'), 'assets':assets, 'tables':tables,
             'projection':'sqlite-logical-rows-and-fts5-positions-v1', 'metadata':pub.asset_metadata(generation, inventory_assets),
             'selection_proof':pub.selection_proof(generation, manifest), 'publisher_sha256':file_sha(pub.__file__),
             'navigation_compilers':{m.__name__:file_sha(m.__file__) for m in (oracle_query_navigation_publish, navigation_match, structure_navigation, inherited_navigation)}}
    qid = digest(value)
    sources = []
    for relative in assets:
        for r in pub.projected_rows(generation/relative, relative, source):
            insert('SRCH_ROW', dict(zip(LOGICAL['SRCH_ROW'].split(), [qid,r['kind'],r['row_id'],r['document_id'],r['lookup_id'],r['owner_id'],r['target_id'],r['sha256'],canonical(r['value'])])))
            if r['kind'] == 'native.source':
                sources.append(r)
    insert('SRCH_POST', {'RFRN_POST_HASH_VALU':qid, 'RFRN_POST_IFMN_CTNT':canonical(value)})
    insert('SRCH_CHNL', {'RFRN_CHNL_NAME':'adr1317', 'RFRN_POST_HASH_VALU':qid, 'CHAN_NO':1})
    documents = manifest['scope']['document_version_ids']
    vector_manifest = {'schema_version':'gold-vector-manifest-preview-v1', 'query_id':qid,
        'source_release_id':original['release_id'], 'dataset_version':source['dataset_version'], 'documents':documents, 'profile':PROFILE}
    vid = digest(vector_manifest)
    assert sources
    for i, row in enumerate(sources):
        insert('VCTR_ITEM', {'VCTR_POST_ID':vid, 'VCTR_SEG_ID':digest(i), 'DOC_ID':row['document_id'],
            'SRC_UNIT_ID':row['lookup_id'], 'VCTR_META_CTNT':'{}', 'EMBD_VCTR_VALU':canonical([1.,0.,0.])})
    insert('VCTR_POST', {'VCTR_POST_ID':vid, 'VCTR_POST_IFMN_CTNT':canonical({'manifest':vector_manifest,
        'completion':{'status':'READY', 'count':len(sources), 'profile_sha256':digest(PROFILE)}})})
    insert('VCTR_HEAD', {'RFRN_POST_HASH_VALU':qid, 'VCTR_POST_ID':vid, 'CHAN_NO':1})
    conn.commit()
    generation.rename(tmp_path/'offline-generation')
    original_connect = sqlite3.connect
    sqlite_calls = []
    def memory_only(database, *args, **kwargs):
        sqlite_calls.append(str(database))
        assert str(database) == ':memory:', 'Serving opened a local source/state SQLite file: '+str(database)
        return original_connect(database, *args, **kwargs)
    monkeypatch.setattr(sqlite3, 'connect', memory_only)
    class RejectSqlglot:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == 'sqlglot' or fullname.startswith('sqlglot.'):
                raise AssertionError('runtime sqlglot import: '+fullname)
    assert not any(k == 'sqlglot' or k.startswith('sqlglot.') for k in sys.modules)
    blocker = RejectSqlglot()
    monkeypatch.setattr(sys, 'meta_path', [blocker, *sys.meta_path])
    for key, val in environment().items():
        monkeypatch.setenv(key, val)
    monkeypatch.setenv('DP', 'oracle')
    monkeypatch.setenv('DP_QUERY_CHANNEL', 'adr1317')
    monkeypatch.setenv('GENOS_ORACLE_TABLE_MAPPING', 'development_g19_1')
    monkeypatch.setenv('GENOS_RAG_INITIAL_SEARCH', 'vector')
    monkeypatch.setenv('GENOS_RAG_IMPLEMENTATION', 'legal-agent-unified-v6')
    monkeypatch.setenv('GENOS_RUNTIME_DIR', '/oracle-runtime/adr1317')
    from semantic_runtime import oracle_query_service as serving, oracle_dp
    monkeypatch.setattr(serving, 'client_from_environment', lambda:client)
    monkeypatch.setattr(serving.Factory, 'start_recovery', lambda self:None)
    monkeypatch.setattr(oracle_dp, 'prepare', lambda *a,**k:pytest.fail('source corpus download'))
    root = Path(os.environ['LOOP_TEST_CODE_ROOT'])
    spec = importlib.util.spec_from_file_location('adr1317_actual_service', root/'service.py')
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    monkeypatch.setattr(entry, '_local_release', lambda:pytest.fail('local source release fallback'))
    monkeypatch.setattr(entry, '_provider', lambda *a:object())
    monkeypatch.setattr(entry, '_genos_v5_environment_binding', lambda profile:None)
    health = asyncio.run(entry.service({}, {'API_TYPE':'HEALTH'}))
    assert health['status'] == 200, health
    assert entry._BINDING['mode'] == 'oracle-query'
    section = asyncio.run(entry.service({}, {'op':'call','method':'GET','path':'/v1/rag/section','params':{'doc_id':'d','node':'0'}}))
    assert section['status'] == 200 and '승인' in json.dumps(section, ensure_ascii=False), section
    search = asyncio.run(entry.service({}, {'API_TYPE':'RAG_SEARCH','q':'모의승인규정 제1조','doc_id':'d'}))
    assert search['status'] == 200, search
    from types import SimpleNamespace
    embedding_calls = []
    def post(session, url, **kw):
        embedding_calls.append({'url':url, 'model':kw['json']['model']})
        return SimpleNamespace(status_code=200, json=lambda:{'data':[{'index':0,'embedding':[1.,0.,0.]}]})
    import requests
    monkeypatch.setattr(requests.Session, 'post', post)
    from semantic_runtime.document_agent import ServingDocumentAgent
    with serving.request_context():
        app = entry._APP.application()
        agent = ServingDocumentAgent(app.state.pipeline, app.state.pipeline.term_agent.config)
        with agent.resources(['d']) as (_, tools, glossary, matcher):
            assert isinstance(matcher.initial_vector, Retriever)
            assert matcher.validate_structure(['d']) > 0
            result = matcher.initial_vector.search('이사회 승인', {'d'})
            assert result['rows'] and all(r['DOC_ID']=='d' for r in result['rows'])
            assert len(embedding_calls) == 1
            sid = result['rows'][0]['SOURCE_ID']
            assert tools.sources[sid]['document_id'] == 'd'
            assert matcher.initial_vector.search('이사회 승인', {'d'}) == result and len(embedding_calls) == 1
            with pytest.raises(Exception, match='cannot widen'):
                matcher.initial_vector.search('승인', {'other'})
            records = entry._APP.record_provider()
            body = canonical({'answer':'Oracle 실행기록'}).encode()
            owner, key, bh = digest('owner'), digest('key'), hashlib.sha256(body).hexdigest()
            assert records.commit(owner, 0, {'status':'saved'}, [{'key':key,'kind':'TEST','order':1,'lookup':None,'body':bh,'deleted':0}], bodies=[body]) == 1
            fresh = AgentRecords(RecordSQL(client, binding='fresh', deadline=time.monotonic()+60), namespace='genos-rag')
            assert fresh.body(bh) == body and fresh.exact(owner, 'TEST', key)['BODY_HASH_VAL'] == bh
    evidence.update(source_files_offline=True, sqlite_open_calls=sqlite_calls, runtime_sqlglot_loaded=False,
        checks=['17_table_preflight','actual_service_health','actual_service_source','actual_service_search',
                'same_service_vector_reader','Oracle_VECTOR_DISTANCE','source_coordinate','ACL','request_reuse','Oracle_record_commit_fresh_read'],
        embedding_fixture_calls=len(embedding_calls), real_embedding_calls=0, model_calls=0)
    entry.request_report._FINALIZER_QUEUE.join()
