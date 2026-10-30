import copy
import io
import json
from pathlib import Path
import sys
import types
import zipfile

import pytest
from vector_silver.runtime import Checkpoint,completion
from vector_silver.schema import COLUMNS,statements
from semantic_runtime.initial_vector import VectorError

class Folder:
    def __init__(self,values=None):self.values=dict(values or {});self.writes=[]
    def list_paths_in_partition(self):return list(self.values)
    def get_download_stream(self,p):return io.BytesIO(self.values[p])
    def upload_stream(self,p,b):
        self.values[p]=b.read() if hasattr(b,'read') else b
        self.writes.append(p)

def receipt(q='a'):
    return {'status':'COMPLETE','oracle_written':True,'target':'SIDDS.*_S',
            'query_release_id':q*64,'source_release_id':'b'*64}

def test_exact_completed_upstream_and_no_latest_guess():
    f=Folder({'jobs/a/complete.json':json.dumps(receipt()).encode()})
    assert completion(f,{})[0]=='jobs/a/complete.json'
    f.values['jobs/z/complete.json']=json.dumps(receipt('c')).encode()
    with pytest.raises(VectorError,match='exactly one'):completion(f,{})
    assert completion(f,{'LEGAL_VECTOR_LOAD_RECEIPT':'/jobs/a/complete.json'})[1]==receipt()
    assert completion(f,{'LEGAL_VECTOR_QUERY_RELEASE':'c'*64})[1]==receipt('c')

@pytest.mark.parametrize('patch',[{'status':'FAILED'},{'oracle_written':False},{'target':'SIDDA'},{'query_release_id':'bad'}])
def test_invalid_or_incomplete_upstream_blocked(patch):
    f=Folder({'jobs/a/complete.json':json.dumps({**receipt(),**patch}).encode()})
    with pytest.raises(VectorError):completion(f,{})

def test_reservations_survive_crash_without_per_sql_upload():
    f=Folder();state=Checkpoint(f,'state',{})
    for n in range(1,258):
        state.sql('STARTED',n);state.sql('ACKNOWLEDGED',n)
    assert len(f.writes)==3
    saved=json.loads(f.values['state'])
    assert saved['sql_reserved']==384 and saved['sql_calls']==257
    resumed=Checkpoint(f,'state',saved)
    resumed.sql('STARTED',saved['sql_reserved']+1)
    assert resumed.value['sql_reserved']==512

def test_schema_and_workbook_counts():
    assert [len(COLUMNS[k]) for k in ('release','segment')]==[2,4]
    ddl='\n'.join(statements())
    assert 'DROP ' not in ddl and 'TRUNCATE ' not in ddl
    assert 'VECTOR(*,FLOAT32)' in ddl and 'VARCHAR2(64 BYTE)' in ddl
    from openpyxl import load_workbook
    book=load_workbook(Path(__file__).resolve().parents[1]/'TABLE_COLUMNS_GOLD_DRAFT.xlsx',read_only=True)
    assert book['전체컬럼정의'].max_row==53
    assert book['벡터컬럼6'].max_row==7

def test_sealed_package_hashes_and_no_data_or_credentials():
    import hashlib
    here=Path(__file__).resolve().parents[1]
    with zipfile.ZipFile(here/'VECTOR_SILVER_CODE_20261029_R3.zip') as z:
        m=json.loads(z.read('CODE_MANIFEST.json'))
        assert set(z.namelist())==set(m['files'])|{'CODE_MANIFEST.json'}
        assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in m['files'].items())
        assert not any(n.endswith(('.sqlite','.db','.npz','.env')) for n in z.namelist())
        assert m['base_generation']==117

# Public Dataiku SDK; HTTP backend in memory. No DSS connection.
from dataikuapi.dss.project import DSSProject
from vector_silver.install import install,RECIPE,RESULT

class Backend:
    def get_project(self,key):return DSSProject(self,key)
    def __init__(self):
        self.items={'managedfolders':{
          'ehA8dpVm':{'id':'ehA8dpVm','name':'landing','type':'S3','params':{'connection':'OBS_DP_PUBLIC','bucket':'fixture','path':'/landing'}},
          'load':{'id':'load','name':'LEGAL_LGL_LOAD_RESULT_R1','type':'S3','params':{'connection':'OBS_DP_PUBLIC','bucket':'fixture','path':'/load'}}},
          'recipes':{'LEGAL_03_LOAD_SILVER_R1':{'recipe':{'name':'LEGAL_03_LOAD_SILVER_R1','type':'python','inputs':{},
             'outputs':{'main':{'items':[{'ref':'load'}]}},'params':{'envSelection':{'envMode':'INHERIT'}}},'payload':'# existing 03'}},
          'variables':{'standard':{},'local':{}}}
        self.calls=[]
    def _perform_json(self,method,path,body=None,**kwargs):
        self.calls.append((method,path))
        parts=path.strip('/').split('/');assert parts[:2]==['projects','LEGAL_RAG']
        kind=parts[2]
        if kind=='variables':
            if method=='GET':return copy.deepcopy(self.items[kind])
            self.items[kind]=copy.deepcopy(body);return {}
        values=self.items[kind]
        if len(parts)==3:
            if method=='GET':return copy.deepcopy([v['recipe'] if kind=='recipes' else v for v in values.values()])
            if kind=='recipes':
                proto=copy.deepcopy(body['recipePrototype']);proto.setdefault('params',{'envSelection':{'envMode':'INHERIT'}})
                name=proto['name'];values[name]={'recipe':proto,'payload':body['creationSettings']['script']};return {'name':name}
            value=copy.deepcopy(body);name='f'+str(len(values));value['id']=name;values[name]=value;return {'id':name}
        name=parts[3]
        if method=='GET':return copy.deepcopy(values[name])
        values[name]=copy.deepcopy(body);return {}
    _perform_empty=_perform_json

def test_public_sdk_flow_connected_idempotent_no_upstream_change():
    b=Backend();p=DSSProject(b,'LEGAL_RAG');before=copy.deepcopy(b.items['recipes']['LEGAL_03_LOAD_SILVER_R1'])
    cfg=install(p,'# code\n')
    r=b.items['recipes'][RECIPE]['recipe']
    assert {v['ref'] for v in r['inputs']['main']['items']}=={'ehA8dpVm','load'}
    assert r['outputs']['main']['items'][0]['appendMode'] is True
    assert b.items['recipes']['LEGAL_03_LOAD_SILVER_R1']==before
    snapshot=copy.deepcopy(b.items);b.calls=[]
    assert install(p,'# code\n')==cfg and b.items==snapshot
    assert all(method=='GET' for method,_ in b.calls)
    with pytest.raises(ValueError,match='CONFLICT'):install(p,'# changed')
    assert b.items==snapshot

def test_install_refuses_missing_03_without_mutating():
    b=Backend();b.items['recipes']={};before=copy.deepcopy(b.items)
    with pytest.raises(ValueError,match='03_OUTPUT'):install(DSSProject(b,'LEGAL_RAG'),'# code')
    assert b.items==before

def test_legacy_state_folder_is_read_dependency():
    b=Backend();b.items['managedfolders']['legacy']={'id':'legacy','name':'LEGAL_VECTOR_RESULT_R1','type':'S3','params':{}}
    cfg=install(DSSProject(b,'LEGAL_RAG'),'# code')
    assert cfg['legacy']=='legacy'
    assert 'legacy' in {x['ref'] for x in b.items['recipes'][RECIPE]['recipe']['inputs']['main']['items']}


def test_native_json_sql_bypasses_only_legacy_projection():
    from semantic_runtime.oracle_silver_reads import rewrite
    from semantic_runtime.physical_mapping import SchemaMap
    from semantic_runtime.initial_vector import REVISION
    mapping=SchemaMap.load(Path(__file__).resolve().parents[1]/'payload/00_SYSTEM/ORACLE/physical_mapping.yaml')
    sql=f'SELECT {REVISION} FROM SIDDS.LGL_VCTR_SET_S'
    assert rewrite(sql,mapping)==sql
    for legacy in ('SIDDA.LEGAL_SRC_DOCUMENT_A','"SIDDA"."LEGAL_SRC_DOCUMENT_A"'):
        mapped=rewrite('SELECT DOCUMENT_ID FROM '+legacy,mapping)
        assert 'SIDDS.LGL_DOC_VER_S' in mapped and 'DOC_ID AS DOCUMENT_ID' in mapped
    literal="SELECT 'LEGAL_SRC_DOCUMENT_A' AS TEXT FROM DUAL"
    assert rewrite(literal,mapping)==literal
