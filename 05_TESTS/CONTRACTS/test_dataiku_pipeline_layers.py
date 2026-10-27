"""User-confirmed development layer targets and exact final delivery contract."""
from pathlib import Path
import hashlib
import json
import zipfile
from types import SimpleNamespace
import pytest
from semantic_runtime.physical_mapping import SchemaMap
from semantic_runtime import oracle_dp_io as io

ROOT=Path(__file__).resolve().parents[2]
DELIVERY=ROOT/'08_DEPLOYMENT/DATAIKU/pipeline_layers_20261027_r1'
BASE=ROOT/'08_DEPLOYMENT/DATAIKU/pipeline_mapped_20261023_r1'


def test_every_consumer_target_is_in_the_user_assigned_layer():
    schema=SchemaMap.load(DELIVERY/'physical_mapping.yaml')
    old=SchemaMap.load(BASE/'physical_mapping.yaml')
    assert schema.target_sha256!=old.target_sha256
    assert len(schema.tables)==9
    for key in schema.tables:
        table=schema.names(key).table
        assert table==('SIDDA.LGL_EXEC_ST_A' if key=='query_state' else 'SIDDS.'+old.tables[key]['name']+'_S')
    for _,_,_,statement in schema.ddl():
        assert statement+';' in (DELIVERY/'01_CREATE_TABLES.sql').read_text()
    assert 'REFERENCES SIDDS.LGL_SRCH_PBLS_S' in (DELIVERY/'01_CREATE_TABLES.sql').read_text()


def test_insert_preserves_payload_while_rebinding_source_schema():
    schema=SchemaMap.load(DELIVERY/'physical_mapping.yaml')
    row={'DATASET_VERSION':'0'*64,'DOCUMENT_ID':'0007','NAME':'SIDDA.LGL_DOC_VER 원문',
         'SOURCE_ARTIFACT_SHA256':None,'SOURCE_JSON':'{"DOCUMENT_ID":"0007"}'}
    statement,binds=io.insert_statement('document',[row],sql=SimpleNamespace(schema_map=schema))
    assert 'SIDDS.LGL_DOC_VER_S' in statement and 'DATA_VER_ID' in statement
    assert row['SOURCE_JSON'] in [v for _,v,_ in binds]
    assert row['NAME'] in [v for _,v,_ in binds]


def test_package_pins_exact_client_and_unchanged_worker():
    manifest=json.loads((DELIVERY/'DELIVERY_MANIFEST.json').read_text())
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((DELIVERY/name).read_bytes()).hexdigest()==digest
    with zipfile.ZipFile(DELIVERY/'DATAIKU_PIPELINE_CLIENT_20261027_R1.zip') as new, zipfile.ZipFile(BASE/'DATAIKU_PIPELINE_CLIENT_20261023_R1.zip') as old:
        a={n.split('/',1)[1]:new.read(n) for n in new.namelist()}
        b={n.split('/',1)[1]:old.read(n) for n in old.namelist()}
    changed={key for key in a if a[key]!=b[key]}
    assert changed=={'physical_mapping.yaml','MAPPING_BINDING.json','GUIDE.txt','CODE_PINS.json','dataiku_run.py'}
    for name,digest in json.loads(a['CODE_PINS.json'])['files'].items():
        assert hashlib.sha256(a[name]).hexdigest()==digest
    assert a['SERVICE_CODE_SHA256.txt']==b['SERVICE_CODE_SHA256.txt']


def test_placeholder_folder_is_rejected_before_local_or_remote_work(tmp_path,monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules,'dataiku',SimpleNamespace(default_project_key=lambda:'LEGAL_RAG'))
    namespace={'__name__':'fixture'}
    exec(compile((DELIVERY/'DATAIKU_PIPELINE_RUN_20261027_R1.txt').read_bytes(),'runner','exec'),namespace)
    with pytest.raises(namespace['RunError'],match='FOLDER_REQUIRED'):
        namespace['run']('prepare',work_dir=str(tmp_path/'absent'))
    assert not (tmp_path/'absent').exists()
