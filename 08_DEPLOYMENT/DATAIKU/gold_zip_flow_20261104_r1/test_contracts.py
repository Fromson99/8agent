"""Schema/identity/failure contracts; no Oracle or external embedding calls."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
PACKAGE=HERE/'package'
sys.path[:0]=[str(PACKAGE),str(PACKAGE/'engine'),str(PACKAGE/'engine/vendor'),str(PACKAGE/'engine/vendor/02_BACKEND')]
import zip_config
import zip_pipeline
import vector_stage
from structure_segments import units_for
from gold_io import Stop


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def params():return {'TARGET_MODE':'GOLD','GOLD_OWNER':'EXPLICIT_OWNER'}


@pytest.fixture
def contract(tmp_path):
    path=tmp_path/'contract.json';path.write_text(json.dumps(zip_config.target(params())))
    return zip_pipeline.Contract(path)


def test_registration_and_runtime_mapping_are_the_same_tables():
    path=REPO/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
    m=module('gold_map_r5_contract',path/'physical_mapping.py')
    mapping=m.GoldMapping.load(path/'mapping_registration_b003_r5.json',owner='EXPLICIT_OWNER')
    registered=zip_config.target(params())
    assert mapping.variant=='B003' and len(mapping.tables)==13
    for key,table in mapping.tables.items():
        assert table['name']==registered['tables'][key]['name']
        for name,col in table['columns'].items():assert dict(col)==registered['tables'][key]['columns'][name]
    with pytest.raises(m.MappingError,match='IDENTIFIER'):
        m.GoldMapping.load(path/'mapping_registration_b003_r5.json')


def test_target_keeps_logical_keys_with_all_latest_physical_names(contract):
    columns=contract.tables
    assert contract.col('SRC_POST','RGSN_AITM')=='RGSN_ASTM'
    assert contract.col('SRCH_ROW','SRCH_DATA_HASH_VALU')=='RFRN_DATA_HASH_VALU'
    assert contract.col('SRCH_ROW','SRCH_DATA_CTNT')=='RFRN_DATA_CTNT'
    assert all(contract.col(k,'CHAN_NO')=='CHAN_NO' for k in ('SRCH_CHNL','ONTL_HEAD','VCTR_HEAD'))
    assert [t['columns']['DOC_ID']['type'] for t in columns.values() if 'DOC_ID' in t['columns']]==['VARCHAR2(100 BYTE)']*6


@pytest.mark.parametrize('did',['x'*100,'한'*33])
def test_vector_sql_uses_registered_byte_width(contract,did):
    row={'VCTR_POST_ID':'p','VCTR_SEG_ID':'s','DOC_ID':did,'SRC_UNIT_ID':'u','VCTR_META_CTNT':'{}','EMBD_VCTR_VALU':'[1,0]'}
    sql,binds=vector_stage.vector_sql(contract,[row],2)
    assert "d VARCHAR2(100 BYTE) PATH '$.DOC_ID'" in sql
    assert 'RGLT_DOC_ID' in sql and 'VCTR_SCTN_ID' in sql and 'BODY_UNIT_ID' in sql
    assert json.loads(binds[0][1])[0]['DOC_ID']==did


@pytest.mark.parametrize('did',['x'*101,'한'*34,'','x\0y'])
def test_vector_invalid_document_stops_before_write(contract,did):
    row={'VCTR_POST_ID':'p','VCTR_SEG_ID':'s','DOC_ID':did,'SRC_UNIT_ID':'u','VCTR_META_CTNT':'{}','EMBD_VCTR_VALU':'[1,0]'}
    with pytest.raises(Stop,match='COORDINATE'):
        vector_stage.vector_sql(contract,[row],2)


def test_structure_uses_stored_coordinates_and_rejects_conflicting_json():
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE source_unit(document_id,unit_id,parent_id,json)')
        db.executemany('INSERT INTO source_unit VALUES(?,?,?,?)',[('d','root',None,'{}'),('d','child','root','{}')])
        assert units_for(db,'d',{'child'})['child']['parent']=='root'
        db.execute('UPDATE source_unit SET json=? WHERE unit_id=?', ('{"id":"wrong"}','child'))
        with pytest.raises(Stop,match='ID_OR_PARENT'):units_for(db,'d',{'child'})


def test_unknown_embedding_is_not_automatically_called_again(tmp_path,contract):
    job=vector_stage.VectorJob(None,contract,tmp_path,{'fixture':True},SimpleNamespace())
    job.guard=lambda:None
    items=[{'text':'synthetic'}]
    job.state['embedding_pending']={'batch':0,'input':zip_pipeline.digest(items)}
    with pytest.raises(Stop,match='UNKNOWN_NO_AUTOMATIC_RETRY'):
        job.embed(0,items,None,{})


def test_resume_rejects_changed_target_before_any_sql(tmp_path,contract):
    binding={'contract':contract.sha256,'target':'A'}
    zip_pipeline.Job(None,contract,tmp_path,binding,None)
    with pytest.raises(Stop,match='BINDING_CHANGED'):
        zip_pipeline.Job(None,contract,tmp_path,dict(binding,target='B'),None)


def test_missing_local_mapping_stops_without_legacy_fallback(monkeypatch):
    path=REPO/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py'
    entry=module('gold_entry_missing_pointer',path)
    monkeypatch.setattr(entry,'load_runtime',lambda:(SimpleNamespace(),{}))
    monkeypatch.setattr(entry,'active_mapping',lambda:(None,None))
    with pytest.raises(ValueError,match='Active Gold mapping required'):
        with entry.open_store():raise AssertionError('missing mapping opened a store')


@pytest.mark.parametrize('name',['X;DROP TABLE Y','X.BAD','x',''])
def test_invalid_owner_stops_before_sql(name):
    with pytest.raises(ValueError):zip_config.target(dict(params(),GOLD_OWNER=name))


def test_packaged_files_have_exact_manifest():
    assert len(zip_pipeline.code_binding())==64
