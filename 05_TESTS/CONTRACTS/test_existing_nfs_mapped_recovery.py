"""Actual mapped preflight and importers; only Oracle/SDK/network ports are fake."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

import pytest
from test_compact_v2_rag import structured_generation
from test_oracle_full_package import full
from test_oracle_dp_runtime import AssetOracle
from test_oracle_query_catalog import Oracle as QueryOracle
from lawrag.pipeline import oracle_full_package as pack, oracle_query_publish as publisher
from semantic_runtime import oracle_dp_io as io, oracle_dp_assets as assets, oracle_query_catalog as q
from semantic_runtime.physical_mapping import SchemaMap, MappingError

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT/'08_DEPLOYMENT/DATAIKU/existing_nfs_transfer_20261029_r2'
BASE = HERE.with_name('existing_nfs_transfer_20261029_r1')
R1_CODE = '935f47a47ade390103312f3b21cd2156e10571cf955ec351199dda16c761115d'


class MappedOracle:
    """Dictionary at the SQL boundary; legacy table access explicitly rejected."""
    SQL_PATH = '/sql'
    def __init__(self, schema):
        self.schema_map = schema
        self.source, self.query = AssetOracle(), QueryOracle()
        self.statements = []
        self.damage = None

    def request(self, method, path, json):
        text = json['statementText']; self.statements.append(text)
        b = {v['name']:v['value'] for v in json.get('binds',[])}
        schema = self.schema_map
        if 'ALL_' in text:
            key = next((k for k,t in schema.tables.items() if t['name']==b.get('t') and schema.owners[t['role']]==b.get('o')),None)
            if 'ALL_INDEXES' in text or 'ALL_IND_COLUMNS' in text:
                key, idx = next((k,i) for k,t in schema.tables.items() for i in t['indexes'] if i['name']==b['i'])
                t = schema.tables[key]; n = schema.names(key)
                if 'ALL_INDEXES' in text:
                    rows=[dict(TABLE_OWNER=schema.owners[t['role']],TABLE_NAME=t['name'],STATUS='VALID',UNIQUENESS='NONUNIQUE')]
                    if self.damage=='index': rows=[]
                else: rows=[dict(COLUMN_NAME=n.c(c)) for c in idx['columns']]
            elif 'ALL_CONS_COLUMNS' in text:
                rows=[]
                for k,t in schema.tables.items():
                    if schema.owners[t['role']]!=b['o']:continue
                    for name, cols in [(t['pk_name'],t['pk']),*[(f['name'],f['columns']) for f in t['foreign_keys']]]:
                        if name==b['c']:rows=[dict(COLUMN_NAME=schema.names(k).c(c)) for c in cols]
                if self.damage=='primary':rows=[]
            elif 'ALL_TAB_COLUMNS' in text:
                rows=[]
                for c in schema.tables[key]['columns'].values():
                    typ=c['type']; number=re.search(r'\((\d+)',typ)
                    rows.append(dict(COLUMN_NAME=c['name'], DATA_TYPE=typ.split('(')[0],
                        DATA_LENGTH=int(number[1]) if number else 0,CHAR_USED='B' if typ.startswith('VARCHAR2') else None,
                        DATA_PRECISION=int(number[1]) if number and typ.startswith('NUMBER') else None,
                        DATA_SCALE=0 if typ.startswith('NUMBER') else None,NULLABLE='Y' if c['nullable'] else 'N',DATA_DEFAULT=c['default']))
                if self.damage=='column':rows.pop()
            else:
                assert 'ALL_CONSTRAINTS' in text
                t=schema.tables[key]
                rows=[dict(CONSTRAINT_NAME=t['pk_name'],CONSTRAINT_TYPE='P',STATUS='ENABLED',VALIDATED='VALIDATED')]
                for c in t['checks']:
                    rows.append(dict(CONSTRAINT_NAME=c['name'],CONSTRAINT_TYPE='C',STATUS='ENABLED',VALIDATED='VALIDATED',SEARCH_CONDITION_VC=schema.check_expression(key,c)))
                for f in t['foreign_keys']:
                    target=schema.tables[f['target']]
                    rows.append(dict(CONSTRAINT_NAME=f['name'],CONSTRAINT_TYPE='R',STATUS='ENABLED',VALIDATED='VALIDATED',R_OWNER=schema.owners[target['role']],R_CONSTRAINT_NAME=target['pk_name']))
                if self.damage=='constraint':rows[0]['STATUS']='DISABLED'
            return {'items':[{'resultSet':{'items':rows,'hasMore':False,'offset':0}}]}
        assert 'SIDDA.LEGAL_' not in text, 'Legacy physical identifier leaked: '+text
        legacy={**{k:'SIDDA.'+v for k,v in io.TABLES.items()},'asset_part':assets.PART_TABLE,
                'source_release':assets.RELEASE_TABLE,'query_row':q.ROW,'query_release':q.RELEASE,
                'query_active':q.ACTIVE,'query_state':q.STATE}
        keys=[k for k in schema.tables if schema.names(k).table in text]
        assert len(keys)==1, text
        key=keys[0]; n=schema.names(key)
        translated=text.replace(n.table,legacy[key])
        columns={v['name']:k for k,v in schema.tables[key]['columns'].items()}
        translated=re.sub(r"'(?:''|[^'])*'|\b[A-Z][A-Z0-9_]*\b",lambda m:columns.get(m[0],m[0]),translated)
        remote=self.query if key.startswith('query_') else self.source
        return remote.request('POST','/sql',{**json,'statementText':translated})


@pytest.fixture
def mapped(tmp_path):
    with zipfile.ZipFile(BASE/'DATAIKU_EXISTING_NFS_CLIENT_20261029_R1.zip') as z:
        path=tmp_path/'map.yaml';path.write_bytes(z.read('client/physical_mapping.yaml'))
    return MappedOracle(SchemaMap.load(path))


def test_mapped_schema_returns_importer_contract(mapped,tmp_path):
    sql=io.SQL(mapped,journal=tmp_path/'schema.jsonl',binding='test')
    result=publisher.schema(sql)
    assert result['deferred_indexes']==[] and result['missing']==[] and result['tables']==4
    assert result['target_map_sha256']==mapped.schema_map.target_sha256
    assert mapped.source.writes==mapped.query.writes==0


@pytest.mark.parametrize('damage',['index','primary','column','constraint'])
@pytest.mark.parametrize('allow',[False,True])
def test_mapped_schema_never_defers_bad_objects(mapped,tmp_path,damage,allow):
    mapped.damage=damage
    with pytest.raises(MappingError,match='TARGET_'):
        publisher.schema(io.SQL(mapped,journal=tmp_path/'schema.jsonl',binding='test'),allow_missing_lookup_indexes=allow)
    assert mapped.source.writes==mapped.query.writes==0


def test_mapped_policy_type_and_no_ddl(mapped,tmp_path):
    sql=io.SQL(mapped,journal=tmp_path/'schema.jsonl',binding='test')
    with pytest.raises(io.DPError,match='QUERY_INDEX_POLICY'):publisher.schema(sql,allow_missing_lookup_indexes='False')
    with pytest.raises(io.DPError,match='MAPPED_DDL_SEPARATE'):publisher.schema(sql,create=True)
    assert not mapped.statements


def load_r1_importer(tmp_path):
    path=tmp_path/'r1_oracle_full_package.py'
    with zipfile.ZipFile(BASE/'DATAIKU_EXISTING_NFS_CLIENT_20261029_R1.zip') as z:
        path.write_bytes(z.read('client/02_BACKEND/lawrag/pipeline/oracle_full_package.py'))
    spec=importlib.util.spec_from_file_location('lawrag.pipeline.r1_oracle_full_package',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_pinned_r1_failure_recovered_full_mapped_import(full,mapped,tmp_path,monkeypatch):
    old=load_r1_importer(tmp_path)
    current=publisher.schema
    # Execute old schema implementation too, rather than mocking its result.
    with zipfile.ZipFile(BASE/'DATAIKU_EXISTING_NFS_CLIENT_20261029_R1.zip') as z:
        text=z.read('client/02_BACKEND/lawrag/pipeline/oracle_query_publish.py')
    namespace=dict(publisher.__dict__);exec(compile(text,'sealed-r1-query.py','exec'),namespace)
    monkeypatch.setattr(publisher,'schema',namespace['schema'])
    # The field also has legacy asset tables, allowing its old WHERE 1=0 checks.
    request=mapped.request
    def allow_old_empty(method,path,json):
        if 'WHERE 1=0' in json['statementText']:
            return {'items':[{'resultSet':{'items':[],'hasMore':False,'offset':0}}]}
        return request(method,path,json)
    monkeypatch.setattr(mapped,'request',allow_old_empty)
    olddir=tmp_path/'r1-failed'
    with pytest.raises(KeyError,match='deferred_indexes'):
        old.import_generation(mapped,full[4],target_binding='mapped',directory=olddir,action='publish')
    prior=(olddir/'full-state.json').read_bytes();state=json.loads(prior)
    assert state['stages']=={} and state['identity']['code']==R1_CODE
    assert mapped.source.writes==mapped.query.writes==0
    monkeypatch.setattr(publisher,'schema',current);monkeypatch.setattr(mapped,'request',request)
    newdir=tmp_path/'r2'
    def run():return pack.import_generation(mapped,full[4],target_binding='mapped',directory=newdir,action='publish',prior_schema_failure_directory=olddir)
    result=run();assert result['status']=='FULL_DATA_VERIFIED' and result['deferred_indexes']==[]
    new=json.loads((newdir/'full-state.json').read_text())
    assert new['deadline']==state['deadline'] and new['prior_schema_calls']>0
    assert (olddir/'full-state.json').read_bytes()==prior
    writes=mapped.source.writes,mapped.query.writes
    assert run()==result and writes==(mapped.source.writes,mapped.query.writes)
    assert not mapped.query.active and not mapped.query.states
    mapped.query.rows.pop(next(iter(mapped.query.rows)))
    with pytest.raises(io.DPError):run()


@pytest.mark.parametrize('damage',['code','target','stage','writes','status','reason','deferred','deadline'])
def test_r1_upgrade_limits(tmp_path,damage):
    old=tmp_path/'old';old.mkdir()
    identity={'target':'mapped','data':'data','generation':'/fixed','code':R1_CODE}
    state={'identity':identity,'status':'FAILED','stages':{},'deadline':1,'error':'KeyError',
           'schema_check':{'status':'READY','tables':4,'target_map_sha256':'a'*64}}
    new_identity={**identity,'code':io.file_sha(pack.__file__)}
    if damage=='code':identity['code']='other'
    if damage=='target':identity['target']='other'
    if damage=='stage':state['stage']='source'
    if damage=='status':state['status']='COMPLETE'
    if damage=='reason':state['error']='another error'
    if damage=='deferred':state['schema_check']['deferred_indexes']=[]
    io.atomic_json(old/'full-state.json',state)
    (old/'schema.jsonl').write_text(json.dumps({'binding':io.digest(identity),'call':22,'write':damage=='writes'})+'\n')
    if damage=='deadline':assert pack._prior_schema_failure(old,new_identity)['deadline']==1
    else:
        with pytest.raises(io.DPError,match='IMPORT_UPGRADE'):pack._prior_schema_failure(old,new_identity)


def test_native_delivered_notebook(full,tmp_path):
    result=subprocess.run([sys.executable,str(HERE/'validate_notebook.py'),str(full[7]),str(tmp_path/'native')],
                          capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'NATIVE_R2_NOTEBOOK_PASS' in result.stdout


@pytest.mark.parametrize('stage',['source','assets','query'])
def test_mapped_write_uncertainty_and_resume(full,mapped,tmp_path,monkeypatch,stage):
    if stage=='source':mapped.source.mode='after_timeout'
    elif stage=='query':mapped.query.fail_after_write=True
    else:
        original=pack.source_publish.publish
        def publish(*args,**kwargs):
            mapped.source.mode='after_timeout'
            monkeypatch.setattr(pack.source_publish,'publish',original)
            return original(*args,**kwargs)
        monkeypatch.setattr(pack.source_publish,'publish',publish)
    directory=tmp_path/'load'
    def run():return pack.import_generation(mapped,full[4],target_binding='mapped',directory=directory,action='publish')
    with pytest.raises(io.DPError,match='WRITE_UNCONFIRMED'):run()
    state=json.loads((directory/'full-state.json').read_text())
    assert state['status']=='FAILED' and state['stage']==stage
    assert run()['status']=='FULL_DATA_VERIFIED'
    assert json.loads((directory/'full-state.json').read_text())['deadline']==state['deadline']
    assert {k:len(v) for k,v in mapped.source.data.items()}==full[6]['source_counts']
    writes=mapped.source.writes,mapped.query.writes
    run();assert writes==(mapped.source.writes,mapped.query.writes)
    assert not mapped.query.active and not mapped.query.states


def test_mapped_expired_import_does_not_issue_sql(full,mapped,tmp_path):
    directory=tmp_path/'load'
    pack.import_generation(mapped,full[4],target_binding='mapped',directory=directory,action='check')
    path=directory/'full-state.json';state=json.loads(path.read_text());state['deadline']=1;io.atomic_json(path,state)
    calls=len(mapped.statements)
    with pytest.raises(io.BudgetPause):
        pack.import_generation(mapped,full[4],target_binding='mapped',directory=directory,action='publish')
    assert len(mapped.statements)==calls and mapped.source.writes==mapped.query.writes==0
