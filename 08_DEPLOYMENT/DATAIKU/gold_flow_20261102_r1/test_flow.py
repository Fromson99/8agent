import base64
import copy
import fcntl
import hashlib
import io
import json
from pathlib import Path
import sys
import types
import pytest

HERE=Path(__file__).resolve().parent;ROOT=HERE/'package'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'engine'))
import run as loader
import flow_inputs as inputs
import flow_spec as spec
import flow_entry as entry
import flow_runtime as runtime
from lawrag.pipeline import oracle_existing_nfs as nfs, oracle_full_package as full

class Folder:
    def __init__(self):self.files={}
    def list_paths_in_partition(self):return list(self.files)
    def get_download_stream(self,p):return io.BytesIO(self.files[p.lstrip('/')])
    def upload_stream(self,p,f):self.files[p.lstrip('/')]=f.read() if hasattr(f,'read') else f

def info_and_data():
    data={'generation/manifest.json':b'{"fixture":true}', 'generation/store.sqlite':b'fixture-db'}
    info={'protocol':nfs.PROTOCOL,'code_sha256':inputs.SERVICE_SHA,'generation':inputs.GENERATION,
          'chunk_bytes':nfs.CHUNK,'source_modified':False,'rebuild':False,
          'dataset_version':hashlib.sha256(data['generation/manifest.json']).hexdigest(),
          'files':{n:{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in data.items()}}
    info['snapshot_sha256']=loader.digest(info)
    return info,data

@pytest.fixture
def transfer(monkeypatch):
    info,data=info_and_data();calls=[]
    class Wire:
        def __init__(self,v):pass
        def call(self,op,**fields):
            calls.append((op,fields))
            if op=='EXISTING_NFS_INFO':return copy.deepcopy(info)
            name=fields['file'];offset=fields['offset'];raw=data[name][offset:offset+nfs.CHUNK]
            return dict(snapshot_sha256=info['snapshot_sha256'],file=name,offset=offset,total_bytes=len(data[name]),
                        bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),content=base64.b64encode(raw).decode())
    monkeypatch.setattr(inputs,'Wire',Wire)
    monkeypatch.setattr(loader,'resource_check',lambda p:None)
    def finish(local,value):
        assert all((local/n).read_bytes()==b for n,b in data.items())
        loader.atomic(local/'full-manifest.json',{'nfs_snapshot':value})
        return {'files':value['files']}
    monkeypatch.setattr(nfs,'finish_received',finish)
    monkeypatch.setattr(full,'verify_restored',lambda p:all((p/n).read_bytes()==b for n,b in data.items()))
    return info,data,calls

def test_first_receive_then_local_skip_no_network(tmp_path,transfer):
    _,data,calls=transfer;folder=Folder();old=tmp_path/'job'
    result=inputs.receive(old,{},[folder],lambda *a,**k:None)
    assert result['downloaded_bytes']==sum(map(len,data.values()))
    first=len(calls)
    result=inputs.receive(old,{},[folder],lambda *a,**k:None)
    assert result['origin']=='LOCAL_REUSED' and len(calls)==first

def test_restore_other_worker_from_cache_without_http(tmp_path,transfer):
    _,_,calls=transfer;folder=Folder()
    inputs.receive(tmp_path/'a'/'job',{},[folder],lambda *a,**k:None);first=len(calls)
    result=inputs.receive(tmp_path/'b'/'job',{},[folder],lambda *a,**k:None)
    assert result['origin']=='DATAIKU_CACHE_RESTORED' and result['downloaded_bytes']==0 and len(calls)==first

def test_missing_local_file_with_marker_restores_cache(tmp_path,transfer):
    _,_,calls=transfer;folder=Folder();old=tmp_path/'job'
    inputs.receive(old,{},[folder],lambda *a,**k:None);first=len(calls)
    (tmp_path/'generation/store.sqlite').unlink()
    result=inputs.receive(old,{},[folder],lambda *a,**k:None)
    assert result['origin']=='DATAIKU_CACHE_RESTORED' and len(calls)==first

def test_reuse_legacy_folder_cache(tmp_path,transfer):
    _,_,calls=transfer;old_cache=Folder();new_cache=Folder()
    inputs.receive(tmp_path/'a'/'job',{},[old_cache],lambda *a,**k:None);first=len(calls)
    result=inputs.receive(tmp_path/'b'/'job',{},[new_cache,old_cache],lambda *a,**k:None)
    assert result['downloaded_bytes']==0 and len(calls)==first

def test_partial_resume_fetches_only_missing_chunk(tmp_path,transfer):
    _,_,calls=transfer;folder=Folder()
    inputs.receive(tmp_path/'a'/'job',{},[folder],lambda *a,**k:None)
    key=next(k for k in folder.files if k.endswith('.bin'));del folder.files[key]
    first=len(calls);inputs.receive(tmp_path/'b'/'job',{},[folder],lambda *a,**k:None)
    assert [op for op,_ in calls[first:]]==['EXISTING_NFS_INFO','EXISTING_NFS_READ']

def test_bad_cache_never_triggers_silent_refetch(tmp_path,transfer):
    _,_,calls=transfer;folder=Folder()
    inputs.receive(tmp_path/'a'/'job',{},[folder],lambda *a,**k:None)
    key=next(k for k in folder.files if k.endswith('.bin'));folder.files[key]=b'bad'
    first=len(calls)
    with pytest.raises(ValueError,match='NFS_CHUNK_HASH'):inputs.receive(tmp_path/'b'/'job',{},[folder],lambda *a,**k:None)
    assert len(calls)==first

def test_new_source_local_conflict_keeps_bytes(tmp_path,transfer):
    folder=Folder();(tmp_path/'generation').mkdir();p=tmp_path/'generation/manifest.json';p.write_text('my data')
    with pytest.raises(ValueError,match='NFS_LOCAL_CONFLICT'):inputs.receive(tmp_path/'job',{},[folder],lambda *a,**k:None)
    assert p.read_text()=='my data'

def test_missing_endpoint_clear_error():
    with pytest.raises(ValueError,match='NFS_CONNECTION_REQUIRED'):inputs.Wire({})

def test_live_notebook_lock_prevents_transfer(tmp_path,monkeypatch):
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace())
    old=tmp_path/'job';directory=entry.job_dir(old);directory.mkdir()
    with (directory/'job.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(RuntimeError,match='EXISTING_LOAD_RUNNING'):entry.execute('receive',{},old)

def test_engine_exactly_matches_previously_sent_fresh1():
    original=HERE.parent/'gold_fresh_1_20261102_r1/package'
    for p in (ROOT/'engine').rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:assert p.read_bytes()==(original/p.relative_to(ROOT/'engine')).read_bytes()
    assert loader.verify_code()

def test_17_tables_once_and_no_db_writers_or_delete():
    spec.validate_spec()
    for n in ['flow_entry.py','install_flow.py','flow_runtime.py','flow_inputs.py']:
        text=(ROOT/n).read_text()
        for bad in ['DELETE FROM ','TRUNCATE TABLE ','LOCK TABLE ','get_writer(','.write_with_schema(']:assert bad not in text

def test_display_escapes_error_and_does_not_invent_db_count():
    from flow_view import render
    text=render({'source':{'status':'FAILED','error':'<script>alert(1)</script>','rows':12,'total':100}},preview=False)
    assert '<script>' not in text and '&lt;script&gt;' in text and '중단됨' in text
    assert '최종 DB 확인 전' in text

def test_runtime_failure_saved_and_stops(tmp_path,monkeypatch):
    folders={s[0]:Folder() for s in spec.STAGES}
    cfg={'folders':{k:k for k in folders},'landing':'input','legacy_cache':[]}
    dku=types.SimpleNamespace(get_custom_variables=lambda:{'LEGAL_GOLD_OLD_JOB_DIR':str(tmp_path/'job')},
                             Folder=lambda k,**kw:folders[k])
    monkeypatch.setitem(sys.modules,'dataiku',dku)
    monkeypatch.setattr(runtime,'publish_insight',lambda records:None)
    monkeypatch.setattr(runtime,'observations',lambda *a:{})
    # Real subprocess and UTF-8 stream path, synthetic backend adapter.
    entrypoint=tmp_path/'flow_entry.py'
    entrypoint.write_text('import json\nprint(json.dumps({"phase":"DIAGNOSTIC_ERROR","context":{"stage":"source"},"causes":[{"type":"Exception","message":"ORA-01031: 권한 부족"}]}),flush=True)\nraise SystemExit(1)\n')
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    with pytest.raises(RuntimeError,match='ORA-01031'):runtime.run('source',cfg)
    record=json.loads(folders['source'].files['latest.json'])
    assert record['status']=='FAILED' and 'ORA-01031' in record['error']
    assert not folders['query'].files
    assert any('/log-' in n for n in folders['source'].files)

def test_runtime_success_retains_complete_result(tmp_path,monkeypatch):
    folders={s[0]:Folder() for s in spec.STAGES};cfg={'folders':{k:k for k in folders}}
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(get_custom_variables=lambda:{'LEGAL_GOLD_OLD_JOB_DIR':str(tmp_path/'job')},Folder=lambda k,**kw:folders[k]))
    monkeypatch.setattr(runtime,'publish_insight',lambda records:None);monkeypatch.setattr(runtime,'observations',lambda *a:{})
    (tmp_path/'flow_entry.py').write_text('print(\'{"phase":"FLOW_STAGE_RESULT","result":{"origin":"LOCAL_REUSED"}}\',flush=True)')
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    runtime.run('receive',cfg)
    record=json.loads(folders['receive'].files['latest.json'])
    assert record['status']=='SUCCESS' and record['detail']=='LOCAL_REUSED'

def test_old_job_path_defaults_and_custom_scratch(monkeypatch):
    monkeypatch.delenv('LEGAL_GOLD_OLD_JOB_DIR',raising=False);monkeypatch.delenv('LEGAL_PIPELINE_SCRATCH',raising=False)
    assert runtime.old_job_path({})==loader.DEFAULT_OLD_JOB
    assert str(runtime.old_job_path({'LEGAL_PIPELINE_SCRATCH':'/mnt/flow'})).startswith('/mnt/flow/')

def test_observer_keeps_verify_error_visible(monkeypatch,tmp_path):
    import flow_monitor
    state={'binding':{'contract':loader.Contract(ROOT/'engine/contract.json').sha256},'status':'VERIFY_FAILED',
           'source':{'document':{'rows':10}},'query':{'a':{'rows':20}},'last_error':{'codes':['ORA-01031']}}
    original=flow_monitor.read
    monkeypatch.setattr(flow_monitor,'read',lambda p:state if Path(p).name=='state.json' else original(p))
    monkeypatch.setattr(flow_monitor.Display,'planned_totals',lambda *a:{'source':10,'query':20})
    result=flow_monitor.snapshot(tmp_path/'job',{})
    assert result['source']['status']=='SUCCESS' and result['verify']['status']=='FAILED'
    assert 'ORA-01031' in result['verify']['error'] and 'report' not in result

def test_observer_source_progress_has_no_false_db_count(monkeypatch,tmp_path):
    import flow_monitor
    state={'binding':{'contract':loader.Contract(ROOT/'engine/contract.json').sha256},'status':'LOADING',
           'source':{'document':{'rows':5}},'query':{}}
    original=flow_monitor.read
    monkeypatch.setattr(flow_monitor,'read',lambda p:state if Path(p).name=='state.json' else original(p))
    monkeypatch.setattr(flow_monitor.Display,'planned_totals',lambda *a:{'source':10,'query':20})
    result=flow_monitor.snapshot(tmp_path/'job',{})
    assert result['source']['rows']==5 and result['query']['status']=='WAITING'
    from flow_view import render
    assert '최종 DB 확인 전' in render(result)
