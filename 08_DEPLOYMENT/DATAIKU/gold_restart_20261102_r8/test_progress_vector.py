import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from progress_display import Display, digest, duration
from mesh_embedding import settings, encode, resolve_settings
import vector_stage as vector


@pytest.mark.parametrize('seconds,text', [(0,'0분 00초'),(61,'1분 01초'),(3661,'1시간 1분 01초'),(None,'계산 중')])
def test_duration(seconds, text):
    assert duration(seconds) == text


def test_observer_resume_stage_eta_and_unchanged_file(tmp_path):
    old = tmp_path/'old'; old.mkdir()
    state_dir = tmp_path/'gold-shape-aaaaaaaaaaaa'; state_dir.mkdir()
    path = state_dir/'state.json'
    now = [0]
    view = Display(old, 'a'*64, 'load', clock=lambda:now[0])
    view.totals = {'source': 100, 'query': 1000}
    state = {'source': {'doc': {'rows': 90}}, 'query': {}, 'status': 'LOADING'}
    path.write_text(json.dumps(state))
    raw = path.read_bytes()
    assert '90 / 100행' in view.render()
    assert '계산 중' in view.render()
    assert path.read_bytes() == raw
    now[0] = 10
    state['source']['doc']['rows'] = 100
    path.write_text(json.dumps(state)); view.render()
    now[0] = 100
    view.render()  # Query wait is not treated as query throughput.
    now[0] = 110
    state['query'] = {'file': {'rows':100}}
    path.write_text(json.dumps(state))
    assert '10.0행/초 | 예상 잔여 1분 30초' in view.render()


@pytest.mark.parametrize('text', ['', 'x', 'x'*800, 'x'*801, 'x'*1500, 'x'*1501, ' '*900])
def test_windows_full_coverage(text):
    seen = set()
    for start, part in vector.windows(text):
        assert len(part) <= 800
        assert text[start:start+len(part)] == part
        seen.update(range(start,start+len(part)))
    assert all(i in seen for i,c in enumerate(text) if not c.isspace())


def test_environment_and_mesh_call():
    with pytest.raises(ValueError): settings({})
    config = settings({'LEGAL_EMBED_LLM_ID':'chosen-model','LEGAL_EMBED_DIMENSIONS':'2'})
    calls = []
    class Request:
        def add_text(self,text): calls.append(('text',text))
        def execute(self): calls.append(('execute',)); return self
        def get_embeddings(self): return [[3.,4.]]
    project = types.SimpleNamespace(get_llm=lambda name:(calls.append(('model',name)) or
                                   types.SimpleNamespace(new_embeddings=lambda:Request())))
    assert encode(project,config,['sample']) == [[.6,.8]]
    assert calls == [('model','chosen-model'),('text','sample'),('execute',)]


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    package = HERE.parent/'gold_shape_silver_20261102_r1/package'
    spec = importlib.util.spec_from_file_location('gold_io', package/'gold_io.py')
    gold = importlib.util.module_from_spec(spec); spec.loader.exec_module(gold)
    monkeypatch.setitem(sys.modules,'gold_io',gold)
    contract = gold.Contract(package/'contract.json')
    old = tmp_path/'old'; old.mkdir()
    directory = tmp_path/('gold-shape-'+contract.sha256[:12]); directory.mkdir()
    source = {'dataset_version':'v', 'source_manifest': {'scope':{'document_version_ids':['d']}}}
    query = {'query':'q'}
    root = tmp_path/'generation'; root.mkdir()
    binding = {'code':'code','files':{},'database':[{'user':'fake'}],'objects':[],
               'source_release':digest(source),'query_release':digest(query)}
    state = {'binding':binding,'status':'SOURCE_QUERY_VERIFIED','deadline':9999999999}
    (directory/'state.json').write_text(json.dumps(state))
    counters = {'embed':0,'rows':{},'writes':0,'fail_db':False,'fail_model':False}
    def atomic(path,value): Path(path).write_text(json.dumps(value))
    loader = types.SimpleNamespace(read=lambda p:json.loads(Path(p).read_text()),
        verify_code=lambda:'code',object_binding=lambda *a:[],
        inputs=lambda *a:(root,{},source,query,{}),atomic=atomic,
        resource_check=lambda p:None,file_hash=lambda p:'helper')
    monkeypatch.setitem(sys.modules,'run',loader)
    row = {'DATASET_VERSION':'v','DOCUMENT_ID':'d','BLOCK_ID':'b','UNIT_ID':'u','TEXT':'x'*12000}
    migration = types.SimpleNamespace(source_binding=lambda p:({},None), unchanged=lambda b:None,
        source_open=lambda p:types.SimpleNamespace(close=lambda:None),
        source_batch=lambda db,kind,v,cursor,**kw:[] if cursor else [row])
    pipeline = types.ModuleType('lawrag.pipeline'); pipeline.oracle_migration=migration
    monkeypatch.setitem(sys.modules,'lawrag',types.ModuleType('lawrag'))
    monkeypatch.setitem(sys.modules,'lawrag.pipeline',pipeline)
    class DB:
        def __init__(self,*a): pass
        def query(self,sql):
            if 'SYS_CONTEXT' in sql: return binding['database']
            return [{'N':len(counters['rows'])}]
        def block(self,sql,binds,rollback=False):
            args={b[0]:b[1] for b in binds}
            if 'pub' not in args: return
            if counters['fail_db']:
                counters['fail_db']=False
                raise RuntimeError('simulated database uncertainty')
            for item in json.loads(args['payload']):
                if rollback: assert counters['rows'][item['id']] == item
                else:
                    assert item['id'] not in counters['rows'] or counters['rows'][item['id']] == item
                    counters['rows'][item['id']]=item
            counters['writes']+=1
    monkeypatch.setattr(gold,'Database',DB)
    import jdbc_transport
    monkeypatch.setattr(jdbc_transport,'install',lambda loader:None)  # Transport is covered by native Oracle checks.
    loader.Database=DB
    loader.Job=type('Job',(),{'batch':lambda *a,**k:None})
    monkeypatch.setenv('G19_DIAGNOSTIC_FILE',str(tmp_path/'errors.jsonl'))
    monkeypatch.setattr(gold.Contract,'preflight',lambda *a:None)
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(SQLExecutor2=lambda **k:None,
        api_client=lambda:types.SimpleNamespace(get_default_project=lambda:None)))
    monkeypatch.setenv('LEGAL_EMBED_LLM_ID','fake'); monkeypatch.setenv('LEGAL_EMBED_DIMENSIONS','2')
    def embed(project,config,texts):
        counters['embed']+=1
        if counters['fail_model']: raise RuntimeError('unknown model response')
        return [[1.,0.] for t in texts]
    monkeypatch.setattr(vector,'encode',embed)
    return package,old,directory,counters


def test_vector_success_and_rerun_no_model(runtime):
    package,old,directory,c=runtime
    vector.execute(package,old)
    calls=c['embed']; assert calls == 2
    assert len(c['rows']) == 17
    vector.execute(package,old)
    assert c['embed'] == calls
    state=json.loads(next((directory/'vectors').glob('*/state.json')).read_text())
    assert state['status']=='VECTORS_STORED_VERIFIED_NOT_ACTIVATED'


def test_cached_response_after_database_failure(runtime):
    package,old,directory,c=runtime
    c['fail_db']=True
    with pytest.raises(RuntimeError): vector.execute(package,old)
    assert c['embed']==1
    vector.execute(package,old)
    assert c['embed']==2  # Only the second batch is newly embedded.


def test_unknown_model_never_resent(runtime):
    package,old,directory,c=runtime
    c['fail_model']=True
    with pytest.raises(RuntimeError): vector.execute(package,old)
    c['fail_model']=False
    with pytest.raises(ValueError,match='OUTCOME_UNKNOWN'): vector.execute(package,old)
    assert c['embed']==1


def test_original_deadline_blocks_model(runtime):
    package,old,directory,c=runtime
    path=directory/'state.json'; state=json.loads(path.read_text());state['deadline']=1
    path.write_text(json.dumps(state))
    with pytest.raises(ValueError,match='DEADLINE'): vector.execute(package,old)
    assert c['embed']==0


def test_pending_second_batch_does_not_block_rechecking_first(runtime, monkeypatch):
    package,old,directory,c=runtime
    original=vector.encode
    def second_unknown(*args):
        if c['embed']==1:
            c['embed']+=1
            raise RuntimeError('unknown second response')
        return original(*args)
    monkeypatch.setattr(vector,'encode',second_unknown)
    with pytest.raises(RuntimeError): vector.execute(package,old)
    with pytest.raises(ValueError,match='OUTCOME_UNKNOWN'): vector.execute(package,old)
    assert c['embed']==2
    assert len(c['rows'])==16


def test_totals_are_bound_to_local_manifest(tmp_path):
    import hashlib
    old=tmp_path/'old';old.mkdir()
    generation=tmp_path/'generation';generation.mkdir()
    raw=json.dumps({'counts':{'document':10,'source_unit':20,'source_block':30}}).encode()
    (generation/'manifest.json').write_bytes(raw)
    files={'manifest.json':hashlib.sha256(raw).hexdigest()}
    body={'binding':{'source':'s','files':files},'tables':{'a':{'rows':123},'b':{'rows':456}}}
    (old/'projection-descriptor-r7.json').write_text(json.dumps({**body,'checksum':digest(body)}))
    state={'binding':{'generation':str(generation),'files':files,'source_release':'s'}}
    assert Display(old,'a'*64,'load').planned_totals(state)=={'source':60,'query':579}
    (generation/'manifest.json').write_text('{}')
    with pytest.raises(ValueError): Display(old,'a'*64,'load').planned_totals(state)


def test_model_dimension_error_is_not_accepted():
    config=settings({'LEGAL_EMBED_LLM_ID':'model','LEGAL_EMBED_DIMENSIONS':'2'})
    class Request:
        def add_text(self,text): pass
        def execute(self): return self
        def get_embeddings(self): return [[1.,2.,3.]]
    project=types.SimpleNamespace(get_llm=lambda m:types.SimpleNamespace(new_embeddings=Request))
    with pytest.raises(ValueError,match='VALUES_INVALID'): encode(project,config,['sample'])


def test_dataiku_project_variables_and_environment_priority():
    variables={'LEGAL_EMBED_LLM_ID':'project-model','LEGAL_EMBED_DIMENSIONS':1024}
    assert resolve_settings({},variables)['model']=='project-model'
    assert resolve_settings({},variables)['dimensions']==1024
    assert resolve_settings({'LEGAL_EMBED_LLM_ID':'environment-model'},variables)['model']=='environment-model'
    with pytest.raises(ValueError):resolve_settings({}, {})
