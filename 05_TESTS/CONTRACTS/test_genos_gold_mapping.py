"""GENOS Gold selection, physical contracts, and request-bound read ports."""
import copy
import json
from pathlib import Path
import re
import time
from types import SimpleNamespace as NS

import pytest

from semantic_runtime.oracle_gold_mapping import GoldMapping
from semantic_runtime.oracle_development_mapping import DevelopmentMapping
from semantic_runtime.physical_mapping import MappingError
from semantic_runtime.oracle_dp_io import DPError, digest


def test_gold_uses_registered_r5_columns_and_separate_agent_records():
    m = GoldMapping.load(owner='APP_GOLD')
    assert len(m.tables) == 17 and m.profile == 'gold'
    assert sum(t['owner'] == 'APP_GOLD' for t in m.tables.values()) == 13
    assert m.names('document').table.startswith('(SELECT DTLS_HASH_VALU')
    assert 'APP_GOLD.IDD_B003_LGL_DOC_VER' in m.names('document').table
    assert 'RFRN_DATA_HASH_VALU AS ROW_SHA256' in m.names('query_row').table
    assert 'RGSN_ASTM AS CREATED_AT' in m.names('source_release').table
    assert 'CHAN_NO AS REVISION' in m.names('query_active').table
    assert m.tables['DOC_VER']['columns']['DOC_ID']['type'] == 'VARCHAR2(100 BYTE)'
    assert set(m.agent_tables.values()) == {'SIDDA.LGL_AGT_BODY_A_1', 'SIDDA.LGL_AGT_REC_A_1',
                                          'SIDDA.LGL_AGT_RUN_A_1', 'SIDDA.LGL_EXEC_ST_A_1'}
    assert m.names('query_state').table == 'SIDDA.LGL_EXEC_ST_A_1'
    with pytest.raises(TypeError):
        m.tables['DOC_VER']['owner'] = 'OTHER'


@pytest.mark.parametrize('owner', [None, '', ' ', 'lower', 'A.B', 'A;DROP', '"GOLD"', 'A'*31])
def test_missing_or_invalid_gold_owner_fails(owner):
    with pytest.raises(DPError, match='GENOS_ORACLE_GOLD_OWNER'):
        GoldMapping.load(owner=owner)


@pytest.mark.parametrize('mode,expected', [('gold','gold'), ('development_g19_1','development_g19_1'), ('mapped','dev_silver')])
def test_environment_selects_mapping_over_existing_ords(monkeypatch, mode, expected):
    from semantic_runtime import oracle_dp, oracle_ords
    calls = []
    monkeypatch.setattr(oracle_ords, 'create_client', lambda **kw: calls.append(kw) or NS())
    for k,v in {'DP':'oracle', 'GENOS_ORACLE_TABLE_MAPPING':mode, 'GENOS_ORACLE_GOLD_OWNER':'APP_GOLD',
                'ORACLE_ORDS_SCHEMA':'alias', 'ORACLE_ORDS_CLIENT_ID':'fixture-id',
                'ORACLE_ORDS_CLIENT_SECRET':'fixture-secret'}.items():
        monkeypatch.setenv(k,v)
    client = oracle_dp.client_from_environment()
    assert client.schema_map.profile == expected
    assert len(calls) == 1 and calls[0]['schema'] == 'alias'
    assert calls[0]['auth_key'] == ('fixture-id','fixture-secret')


def test_owner_changes_factory_and_dp_environment_bindings(monkeypatch):
    from semantic_runtime.oracle_query_service import environment_binding
    from semantic_runtime.oracle_dp import environment_binding as dp_binding
    monkeypatch.setenv('GENOS_ORACLE_GOLD_OWNER','A')
    first=(environment_binding(),dp_binding(),GoldMapping.load(owner='A').target_sha256)
    monkeypatch.setenv('GENOS_ORACLE_GOLD_OWNER','B')
    assert all(a != b for a,b in zip(first,(environment_binding(),dp_binding(),GoldMapping.load(owner='B').target_sha256)))


def metadata(m):
    rows={}
    for table in m.tables.values():
        result=[]
        for c in table['columns'].values():
            typ=c['type']
            row={'COLUMN_NAME':c['name'], 'DATA_TYPE':typ.split('(')[0], 'DATA_LENGTH':0,
                 'CHAR_USED':None, 'DATA_PRECISION':None, 'DATA_SCALE':None,
                 'NULLABLE':'N' if c['required'] else 'Y'}
            if typ.startswith(('VARCHAR2','CHAR')):
                row.update(DATA_LENGTH=int(re.search(r'\((\d+)',typ)[1]),CHAR_USED='B')
            elif typ.startswith('NUMBER'):
                row.update(DATA_PRECISION=int(re.search(r'\((\d+)',typ)[1]),DATA_SCALE=0)
            elif typ.startswith('TIMESTAMP'):
                row.update(DATA_TYPE='TIMESTAMP(6) WITH TIME ZONE',DATA_SCALE=6)
            result.append(row)
        rows[(table['owner'],table['name'])]=result
    calls=[]
    def query(statement,binds,*,limit):
        assert statement.startswith('SELECT ') and 'ALL_TAB_COLUMNS' in statement and limit==100
        target=tuple(v for _,v,_ in binds);calls.append(target)
        return rows[target]
    return rows,NS(query=query),calls


def test_preflight_checks_all_gold_and_agent_tables_without_writes():
    m=GoldMapping.load(owner='APP_GOLD');rows,sql,calls=metadata(m)
    assert m.preflight(sql)['tables']==17 and len(calls)==17
    assert sum(owner=='APP_GOLD' for owner,_ in calls)==13


@pytest.mark.parametrize('change', ['empty','missing','extra','type','length','nullable'])
def test_schema_or_visibility_failure_remains_a_failure(change):
    m=GoldMapping.load(owner='APP_GOLD');rows,sql,calls=metadata(m)
    key=('APP_GOLD','IDD_B003_LGL_DOC_VER');data=rows[key]
    if change=='empty':data.clear()
    elif change=='missing':data.pop()
    elif change=='extra':data.append({**data[0],'COLUMN_NAME':'UNEXPECTED'})
    elif change=='type':data[0]['DATA_TYPE']='CLOB'
    elif change=='length':data[0]['DATA_LENGTH']+=1
    else:data[0]['NULLABLE']='Y'
    with pytest.raises(MappingError,match='GOLD_B003_SCHEMA_'):
        m.preflight(sql)
    assert len(calls)==1


@pytest.mark.parametrize('change',['table','column','variant','duplicate','missing_table','type'])
def test_malformed_mapping_is_rejected(tmp_path,change):
    source=Path(__file__).resolve().parents[2]/'00_SYSTEM/ORACLE/gold_b003_r5.json'
    data=json.loads(source.read_text())
    if change=='table':data['tables']['DOC_VER']['name']='LGL_G19_DOC_VER_S_1'
    elif change=='column':data['tables']['DOC_VER']['columns']['DOC_ID']['name']='A;DROP'
    elif change=='variant':data['variant']='B03'
    elif change=='missing_table':data['tables'].pop('VCTR_HEAD')
    elif change=='type':data['tables']['DOC_VER']['columns']['DOC_ID']['type']='VARCHAR2(100 BYTE);DROP'
    raw=json.dumps(data)
    if change=='duplicate':raw=raw.replace('"variant": "B003"','"variant": "B003", "variant": "B003"')
    path=tmp_path/'map.json';path.write_text(raw)
    with pytest.raises(MappingError):GoldMapping.load(path,owner='APP_GOLD')


def test_native_source_rewrite_uses_gold_and_preserves_predicates():
    from semantic_runtime.oracle_silver_reads import rewrite
    m=GoldMapping.load(owner='APP_GOLD')
    sql=rewrite('SELECT r.DOCUMENT_ID FROM SIDDA.LEGAL_SRC_DOCUMENT_A r WHERE r.DATASET_VERSION=:v AND r.DOCUMENT_ID=:d',m)
    assert 'APP_GOLD.IDD_B003_LGL_DOC_VER' in sql and 'SIDDS' not in sql
    assert sql.endswith('WHERE r.DATASET_VERSION=:v AND r.DOCUMENT_ID=:d')


def vector_fixture():
    from semantic_runtime.oracle_query_vector import Retriever
    profile={'model':'fixture','revision':'r1','dimensions':3,'metric':'COSINE','normalization':'l2','transport':'fixture'}
    manifest={'profile':profile,'query_id':'q','source_release_id':'s','dataset_version':'v','documents':['public','private']}
    envelope={'manifest':manifest,'completion':{'status':'READY','count':2,'profile_sha256':digest(profile)}}
    head={'VCTR_POST_ID':digest(manifest),'CHAN_NO':1};calls=[];encodes=[]
    def query(stmt,binds,*,limit):
        calls.append((stmt,binds))
        if 'IDD_B003_LGL_VCTR_HEAD' in stmt:return [head]
        if 'IDD_B003_LGL_VCTR_POST' in stmt:return [{'VCTR_POST_IFMN_CTNT':json.dumps(envelope)}]
        assert 'APP_GOLD.IDD_B003_LGL_VCTR_ITEM' in stmt
        return [{'DOC_ID':'public','SOURCE_ID':'article:1','DISTANCE':0.0}]
    req=NS(sql=NS(client=NS(schema_map=GoldMapping.load(owner='APP_GOLD')),query=query,deadline=time.monotonic()+60),
           release_id='q',sources=NS(allowed={'public'}),snapshot=NS(release_id='s',dataset_version='v'),
           records=NS(manifest={'source_manifest':{'scope':{'document_version_ids':['public','private']}}}))
    class Encoder:
        def __init__(self,config,*,deadline):self.calls=0
        def encode(self,texts):encodes.append(texts);self.calls+=1;return [[1.,0.,0.]]
    return Retriever(req,encoder_factory=Encoder),envelope,head,calls,encodes


def test_gold_vector_same_publication_scope_and_no_duplicate_embedding():
    reader,env,head,calls,encodes=vector_fixture()
    result=reader.search('승인',{'public'})
    assert reader.search('승인',{'public'})==result and len(encodes)==1 and len(calls)==3
    assert 'CHAN_ORD' not in calls[0][0] and 'CHAN_NO' in calls[0][0]
    assert 'EMBD_VCTR AS EMBD_VCTR_VALU' in calls[-1][0]
    assert dict((k,v) for k,v,_ in calls[-1][1])['docs']=='["public"]'
    with pytest.raises(Exception,match='cannot widen'):reader.search('승인',{'private'})
    assert len(encodes)==1


def test_gold_vector_bad_publication_stops_before_embedding():
    reader,env,head,calls,encodes=vector_fixture()
    env['manifest']['source_release_id']='wrong';head['VCTR_POST_ID']=digest(env['manifest'])
    with pytest.raises(Exception,match='VECTOR_PUBLICATION'):reader.search('승인',{'public'})
    assert not encodes


def test_gold_ontology_scope_revocation_and_read_only_share_sql_budget():
    from semantic_runtime.legal_agent.errors import ContractError
    m=GoldMapping.load(owner='APP_GOLD');calls=[];active=[['p','bundle','h','public']]
    def query(stmt,binds,*,limit):
        calls.append((stmt,binds,limit))
        assert all('APP_GOLD.IDD_B003_LGL_'+k in stmt for k in ('ONTL_POST','ONTL_HEAD','ONTL_ANC'))
        assert limit==1 and 'FETCH FIRST 1025 ROWS ONLY' in stmt
        return [{'ROWS_JSON':json.dumps(active)}]
    req=NS(sql=NS(query=query),sources=NS(allowed={'public'}),snapshot=NS(dataset_version='v'))
    repo=m.ontology_repository(req,None)
    ref={'publication_id':'p','bundle_id':'bundle','package_sha256':'h'}
    assert repo.current_publications([ref],{'public'})=={'p':True}
    active.clear()
    assert repo.current_publications([ref],{'public'})=={'p':False} and len(calls)==2
    with pytest.raises(ContractError,match='cannot widen'):repo.current_publications([ref],{'private'})
    with pytest.raises(DPError,match='READ_ONLY'):
        with repo.session(write=True):pass
    with pytest.raises(DPError,match='PRECREATED'):repo.initialize()
    assert repo.lookup({'document_id':'private'}, {'public'})==[] and len(calls)==2
