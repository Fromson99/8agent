"""Mapped ingestion: strict YAML + durable checkpoint contracts, no external services."""
from pathlib import Path
import hashlib
import importlib.util
import io as streams
import json
import sys
import yaml
import pytest
from semantic_runtime.physical_mapping import SchemaMap,MappingError
from semantic_runtime import oracle_dp_io as io

ROOT=Path(__file__).resolve().parents[2]
DELIVERY=ROOT/'08_DEPLOYMENT/DATAIKU/pipeline_mapped_20261023_r1'
sys.path.insert(0,str(ROOT/'08_DEPLOYMENT/DATAIKU/pipeline_service_20261022_r3/src'))
sys.path.insert(0,str(DELIVERY/'src'))
import managed_job

class Folder:
    def __init__(self):self.data={};self.fail=None
    def list_paths_in_partition(self):return ['/'+p for p in self.data]
    def get_download_stream(self,path):return streams.BytesIO(self.data[path.lstrip('/')])
    def upload_stream(self,path,stream):
        if self.fail:raise RuntimeError(self.fail)
        self.data[path.lstrip('/')]=stream.read()


def test_mapping_and_generated_sql_are_same_contract():
    schema=SchemaMap.load(DELIVERY/'physical_mapping.yaml')
    assert len(schema.tables)==9 and sum(len(t['columns']) for t in schema.tables.values())==46
    sql=(DELIVERY/'01_CREATE_TABLES.sql').read_text()
    for _,_,_,statement in schema.ddl():assert statement+';' in sql
    assert 'DROP TABLE' not in sql and 'TRUNCATE' not in sql.upper().split('\n',4)[-1]
    assert schema.names('source_release').c('RELEASE_ID')=='SRC_PBLS_ID'
    assert schema.names('query_release').c('RELEASE_ID')=='SRCH_PBLS_ID'
    assert schema.names('document').select('DOCUMENT_ID')=='DOC_ID AS DOCUMENT_ID'


@pytest.mark.parametrize('change,error',[
 (lambda v:v['tables']['document'].update(name='X;DROP TABLE Y'),'MAP_IDENTIFIER'),
 (lambda v:v['tables']['document']['columns']['NAME'].update(name='DOC_ID'),'MAP_COLUMN_COLLISION'),
 (lambda v:v['tables']['document']['columns']['DOCUMENT_ID'].update(nullable=True),'MAP_PK_NULL'),
 (lambda v:v['tables'].pop('asset_part'),'MAP_TABLE_SET'),
])
def test_invalid_maps_are_rejected(tmp_path,change,error):
    value=yaml.safe_load((DELIVERY/'physical_mapping.yaml').read_text());change(value)
    path=tmp_path/'map.yaml';path.write_text(yaml.safe_dump(value))
    with pytest.raises(MappingError,match=error):SchemaMap.load(path)


def test_profile_duplicate_keys_and_documentation_hash(tmp_path):
    path=DELIVERY/'physical_mapping.yaml'
    with pytest.raises(MappingError,match='DISABLED'):SchemaMap.load(path,profile='prod_gold')
    with pytest.raises(MappingError,match='FILE_HASH'):SchemaMap.load(path,expected_sha256='0'*64)
    invalid=tmp_path/'invalid.yaml';invalid.write_text(path.read_text()+'\nrevision: duplicate\n')
    with pytest.raises(MappingError,match='MAP_KEYS'):SchemaMap.load(invalid)
    before=SchemaMap.load(path);value=yaml.safe_load(path.read_text());value['tables']['document']['description']='설명 보충'
    invalid.write_text(yaml.safe_dump(value));after=SchemaMap.load(invalid)
    assert before.file_sha256!=after.file_sha256 and before.target_sha256==after.target_sha256
    value['tables']['document']['name']='LGL_DOC_NEW';invalid.write_text(yaml.safe_dump(value))
    assert SchemaMap.load(invalid).target_sha256!=before.target_sha256


def test_source_insert_maps_identifiers_but_never_payload(tmp_path):
    from types import SimpleNamespace
    schema=SchemaMap.load(DELIVERY/'physical_mapping.yaml')
    row={'DATASET_VERSION':'0'*64,'DOCUMENT_ID':'0007','NAME':'본문 DATASET_VERSION DOCUMENT_ID',
         'SOURCE_ARTIFACT_SHA256':None,'SOURCE_JSON':'{"DOCUMENT_ID":"0007"}'}
    statement,binds=io.insert_statement('document',[row],sql=SimpleNamespace(schema_map=schema))
    assert 'SIDDA.LGL_DOC_VER' in statement and 'DATA_VER_ID' in statement
    assert not any(name in statement for name in ('DATASET_VERSION','SOURCE_JSON','DOCUMENT_ID'))
    assert row['SOURCE_JSON'] in [v for _,v,_ in binds]


def test_durable_resume_budgets_and_changed_binding(tmp_path):
    folder=Folder();store=managed_job.ManagedJob(folder,'job',{'target':'a'})
    deadline=store.value['deadline']
    class Client:
        SQL_PATH='/sql';schema_map=None
        def request(self,*a,**k):return 'called'
    client=managed_job.BudgetClient(Client(),store,max_calls=65)
    assert client.request()=='called' and store.value['reserved_sql_calls']==64
    resumed=managed_job.ManagedJob(folder,'job',{'target':'a'})
    assert resumed.value['deadline']==deadline
    again=managed_job.BudgetClient(Client(),resumed,max_calls=65)
    assert again.request()=='called'
    with pytest.raises(io.BudgetPause,match='BUDGET_EXHAUSTED'):again.request()
    with pytest.raises(ValueError,match='BINDING_CHANGED'):managed_job.ManagedJob(folder,'job',{'target':'b'})
    blob=tmp_path/'a.zip';blob.write_bytes(b'archive')
    info=resumed.put_blob(blob);resumed.get_blob(info,tmp_path/'restored.zip')
    assert (tmp_path/'restored.zip').read_bytes()==b'archive'
    folder.data[info['path']]=b'changed'
    with pytest.raises(ValueError,match='BLOB'):resumed.get_blob(info,tmp_path/'other.zip')


def test_checkpoint_failures_do_not_issue_sql_or_relabel_success():
    folder=Folder();store=managed_job.ManagedJob(folder,'job',{})
    class Client:
        SQL_PATH='/sql';schema_map=None
        def request(self,*a,**k):pytest.fail('SQL must not run after checkpoint failure')
    client=managed_job.BudgetClient(Client(),store)
    folder.fail='upload lost'
    with pytest.raises(RuntimeError,match='upload lost'):client.request()


def test_short_stream_reads_and_checkpoint_corruption():
    class Short(streams.BytesIO):
        def read(self,n=-1):return super().read(min(n,7))
    class ShortFolder(Folder):
        def get_download_stream(self,path):return Short(self.data[path.lstrip('/')])
    folder=ShortFolder();store=managed_job.ManagedJob(folder,'job',{'x':'가나다'})
    assert managed_job.ManagedJob(folder,'job',{'x':'가나다'}).value==store.value
    latest=max(folder.data);folder.data[latest]=b'truncated'
    with pytest.raises(ValueError,match='CHECKPOINT_HASH'):managed_job.ManagedJob(folder,'job',{'x':'가나다'})


def test_orphan_snapshot_can_resume_before_first_start(tmp_path):
    spec=importlib.util.spec_from_file_location('mapped_dataiku_run',DELIVERY/'src/dataiku_run.py')
    client=importlib.util.module_from_spec(spec);spec.loader.exec_module(client)
    inputs=tmp_path/'inputs';raw=inputs/'01_DATA/RAW/a.xml';raw.parent.mkdir(parents=True);raw.write_text('same source')
    support=tmp_path/'support.zip';support.write_bytes(b'support')
    job=tmp_path/'job';job.mkdir()
    client.t.pack({'01_DATA/RAW/a.xml':raw},job/'RAW_INPUT.zip')
    class Remote:
        def call(self,op,**fields):
            if op=='HEALTH':return {'code_sha256':'a'*64,'instance':'fixture'}
            assert op=='START'
            raise RuntimeError('expected stop at START')
    with pytest.raises(RuntimeError,match='expected stop'):
        client.process(Remote(),inputs,support,job,expected_code_sha256='a'*64)
    assert client.t.read(job/'client.json')['status']=='NEW'


@pytest.fixture
def notebook_env(tmp_path,monkeypatch):
    import test_dataiku_pipeline_managed_folder as base
    monkeypatch.setattr(base,'R2',DELIVERY)
    monkeypatch.setattr(base,'RUN','DATAIKU_PIPELINE_RUN_20261023_R1')
    monkeypatch.setattr(base,'PREFIXES',(*base.PREFIXES,'managed_job'))
    generator=base.env.__wrapped__(tmp_path,monkeypatch)
    env=next(generator)
    env.folder.data.pop('/DATAIKU_PIPELINE_CLIENT_20261022_R1.zip')
    name='DATAIKU_PIPELINE_CLIENT_20261023_R1.zip'
    env.folder.data['/'+name]=(DELIVERY/name).read_bytes()
    try:yield env
    finally:
        try:next(generator)
        except StopIteration:pass


def test_final_notebook_prepares_new_client_with_stream_folder(notebook_env):
    env=notebook_env
    assert env.run()['status']=='READY'
    assert env.run()['status']=='READY'
    code=env.work/'code/DATAIKU_PIPELINE_CLIENT_20261023_R1'
    assert (code/'physical_mapping.yaml').is_file()
    assert hashlib.sha256((code/'physical_mapping.yaml').read_bytes()).hexdigest()==json.loads((code/'MAPPING_BINDING.json').read_text())['yaml_sha256']
    assert env.folder.reads


def test_final_notebook_rejects_corrupt_code_before_import(notebook_env):
    env=notebook_env
    env.folder.data['/DATAIKU_PIPELINE_CLIENT_20261023_R1.zip']=b'bad code'
    with pytest.raises(env.m['RunError']):env.run()
    assert not (env.work/'inputs').exists()
