"""Field resume contract against the unchanged transport client and real DSS SDK."""
import ast
import base64
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import zipfile
import pytest
import resume as fix
import update as updater

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'pipeline_recipes_20261027_r1'
REF=json.loads((HERE.parent/'pipeline_input_selection_20261027_r2/REFERENCE.json').read_text())
TEMP=tempfile.TemporaryDirectory(prefix='a8-resume-test-')
ROOT=Path(TEMP.name)
with zipfile.ZipFile(BASE/'DATAIKU_RECIPE_PACKAGE_20261027_R1.zip') as z:z.extractall(ROOT)
sys.path[:0]=[str(ROOT),str(ROOT/'client'),str(ROOT/'client/02_BACKEND')]
import recipes_runtime as r
import install_flow
BASE_STRUCTURE=r.structure
spec=importlib.util.spec_from_file_location('resume_sdk_test',BASE/'test_sdk.py')
sdk=importlib.util.module_from_spec(spec);spec.loader.exec_module(sdk)
with zipfile.ZipFile(HERE.parent/'pipeline_mapped_20261023_r1/GENOS_PIPELINE_SERVICE_20261022_R2.zip') as z:
    prefix='GENOS_PIPELINE_SERVICE_20261022_R2/'
    pins_raw=z.read(prefix+'CODE_PINS.json')
    assert hashlib.sha256(pins_raw).hexdigest()==r.EXPECTED
    service_raw=z.read(prefix+'service.py')
    assert hashlib.sha256(service_raw).hexdigest()==json.loads(pins_raw)['files']['service.py']
    (ROOT/'sealed_service.py').write_bytes(service_raw)
spec=importlib.util.spec_from_file_location('batch_api',ROOT/'sealed_service.py')
api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)


class Folder:
    def __init__(self): self.data={}; self.reads=[]; self.writes=[]
    def list_paths_in_partition(self): return ['/'+p for p in self.data]
    def get_download_stream(self,name):
        self.reads.append(name.lstrip('/'));return io.BytesIO(self.data[name.lstrip('/')])
    def upload_stream(self,name,stream):
        self.writes.append(name.lstrip('/'));self.data[name.lstrip('/')]=stream.read()


@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setattr(r,'structure',r.structure)
    monkeypatch.setattr(r,'input_receipts',r.input_receipts)
    named={};exec(REF['adapter_source'],named);named['install_input_selection'](r)
    folders={k:Folder() for k in ('landing','raw','structured','load')}
    receipts={}
    for name,member in [('RAW_INPUT.zip','01_DATA/RAW/internal/team/원문.xml'),
                        ('PIPELINE_SUPPORT.zip','01_DATA/CATALOG/test.json')]:
        p=tmp_path/(name+'.input');p.write_bytes(b'fixture original')
        target=tmp_path/name; info=r.t.pack({member:p},target)
        folders['landing'].data[name]=target.read_bytes()
        folders['landing'].data[name+'.receipt.json']=json.dumps({'archive':name,**info}).encode()
        receipts[name]={**info,'remote':'/'+name}
    data=tmp_path/'returned.txt';data.write_text('source fixture')
    result=tmp_path/'result.zip'
    result_info=r.t.pack({'generation/fixture.txt':data},result,metadata={'code_sha256':r.EXPECTED})
    server=tmp_path/'server';server.mkdir()
    r.t.write(server/'instance.json',{'instance':'test-instance'})
    monkeypatch.setattr(api,'scratch',lambda:server)
    monkeypatch.setattr(api,'code_pin',lambda:r.EXPECTED)
    # No worker/model is launched. Actual START/UPLOAD/STATUS/DOWNLOAD auth,
    # idempotence, ownership and offset handling run through api.handle.
    calls=[]; lose_start=[False]; ready_on_status=[False]
    class Remote:
        url='https://fixture.invalid/pipeline'; token='private-platform-token'
        def call(self,op,**fields):
            calls.append((op,copy.deepcopy(fields)))
            if op=='EXECUTE' or (op=='STATUS' and ready_on_status[0]):
                state=r.t.read(server/fields['job_id']/'state.json')
                state.update(status='COMPLETE',phase='RETURN_READY',result=result_info)
                r.t.write(server/fields['job_id']/'state.json',state)
                (server/fields['job_id']/'result.zip').write_bytes(result.read_bytes())
            try: reply=api.handle({'API_TYPE':op,**fields})
            except ValueError as exc:
                raise RuntimeError('GENOS_'+str(exc).split(':',1)[0]) from None
            if op=='START' and lose_start[0]:
                lose_start[0]=False;raise RuntimeError('GENOS_TIMEOUT')
            return reply
    remote=Remote()
    identity={'service_url_sha256':hashlib.sha256(remote.url.encode()).hexdigest(),
              'service_code':r.EXPECTED,'input':{'archives':{n:{k:v[k] for k in ('sha256','bytes')} for n,v in receipts.items()}}}
    preflights=[]
    def preflight(sql):
        preflights.append(True)
        # Exercise the real durable budget reservation without a database server.
        sql.client.request('GET','/query')
    oracle=SimpleNamespace(SQL_PATH='/query',request=lambda *a,**k: {},
                           schema_map=SimpleNamespace(preflight=preflight))
    monkeypatch.setattr(r,'context',lambda *args:(oracle,{},remote,identity))
    monkeypatch.setattr(r,'remote_client',lambda variables:remote)
    store=r.ManagedJob(folders['structured'],'same-job',identity)
    state={'job_id':'a'*32,'job_token':'b'*64,'instance':'test-instance','code_sha256':r.EXPECTED,
           'deadline':store.value['deadline'],'archives':{'raw':{k:receipts['RAW_INPUT.zip'][k] for k in ('sha256','bytes')},
           'support':{k:receipts['PIPELINE_SUPPORT.zip'][k] for k in ('sha256','bytes')}},'status':'NEW'}
    store.value.update(client=state,raw_blob=store.put_blob(tmp_path/'RAW_INPUT.zip'),reserved_sql_calls=128)
    store.save()
    fix.install_resume(r)
    def run(name='run'):
        work=tmp_path/name;work.mkdir()
        return r.structure({},folders,{},work,'same-job')
    def start():
        return remote.call('START',**{k:state[k] for k in ('job_id','job_token','instance','code_sha256','archives','deadline')})
    def snapshot():return r.ManagedJob(folders['structured'],'same-job',identity)
    def reset_reads():
        for f in folders.values():f.reads.clear()
        calls.clear();preflights.clear()
    return SimpleNamespace(**locals())


def assert_no_inputs(e):
    assert e.folders['raw'].reads==[]
    assert not any(p.endswith('.zip') for p in e.folders['landing'].reads)
    assert e.store.value['raw_blob']['path'] not in e.folders['structured'].reads


def test_busy_is_detected_before_inputs_and_sql_and_preserves_original_state(env):
    e=env
    other=copy.deepcopy(e.state);other.update(job_id='c'*32,job_token='d'*64)
    e.remote.call('START',**{k:other[k] for k in ('job_id','job_token','instance','code_sha256','archives','deadline')})
    before=copy.deepcopy(e.folders['structured'].data);e.reset_reads()
    with pytest.raises(RuntimeError,match='GENOS_BUSY'):e.run()
    assert_no_inputs(e)
    assert e.preflights==[] and [op for op,_ in e.calls]==['START']
    assert e.folders['structured'].data==before
    assert e.snapshot().value['reserved_sql_calls']==128


def test_partial_upload_resumes_saved_zip_and_offset_through_real_service(env):
    e=env;e.start()
    raw=(e.tmp_path/'RAW_INPUT.zip').read_bytes();piece=raw[:11]
    e.remote.call('UPLOAD',**{k:e.state[k] for k in ('job_id','job_token','instance','code_sha256')},
                  slot='raw',offset=0,sha256=hashlib.sha256(piece).hexdigest(),file_content_base64=base64.b64encode(piece).decode())
    e.reset_reads();result=e.run()
    assert result['status']=='STRUCTURED' and e.folders['raw'].reads==[]
    assert [f['offset'] for op,f in e.calls if op=='UPLOAD' and f['slot']=='raw']==[11]
    assert [op for op,_ in e.calls].count('START')==1
    assert [op for op,_ in e.calls].count('EXECUTE')==1
    assert all(f.get('job_id',e.state['job_id'])==e.state['job_id'] for _,f in e.calls)
    assert e.snapshot().value['deadline']==e.state['deadline']
    assert e.snapshot().value['reserved_sql_calls']==192
    proof=r.read_json(e.folders['structured'],'jobs/same-job/structured.json')
    assert proof==r.structured_record(e.snapshot()) # exact unchanged recipe03 consumer


@pytest.mark.parametrize('phase',['RUNNING','COMPLETE'])
def test_processing_and_completed_skip_all_input_downloads(env,phase,monkeypatch):
    e=env;e.start();path=e.server/e.state['job_id']/'state.json'
    state=r.t.read(path);state.update(status=phase,phase='STRUCTURE',worker=api.pid_identity(__import__('os').getpid()))
    if phase=='COMPLETE':
        state['result']=e.result_info;(path.parent/'result.zip').write_bytes(e.result.read_bytes())
    else:e.ready_on_status[0]=True
    r.t.write(path,state);e.reset_reads()
    monkeypatch.setattr(r.client.time,'sleep',lambda value:None)
    assert e.run()['status']=='STRUCTURED'
    assert_no_inputs(e)
    assert not any(op in {'UPLOAD','EXECUTE','ACK','CANCEL'} for op,_ in e.calls)


def test_downloaded_restores_only_result_and_completed_repeat_is_read_only(env):
    e=env;s=e.snapshot();s.value['client'].update(status='DOWNLOADED',result=e.result_info)
    s.value['result_blob']=s.put_blob(e.result);s.save();e.reset_reads()
    result=e.run();assert result['status']=='STRUCTURED' and not e.calls
    reads=e.folders['structured'].reads
    assert s.value['result_blob']['path'] in reads and s.value['raw_blob']['path'] not in reads
    before=copy.deepcopy(e.folders['structured'].data);e.reset_reads()
    assert e.run('repeat')==result
    assert e.folders['structured'].data==before and not e.calls


def test_start_reply_loss_reuses_same_job_without_download_on_uncertain_attempt(env):
    e=env;e.lose_start[0]=True;e.reset_reads()
    with pytest.raises(RuntimeError,match='TIMEOUT'):e.run('uncertain')
    assert_no_inputs(e)
    assert e.run('recovered')['status']=='STRUCTURED'
    assert len(list(e.server.glob('*/state.json')))==1
    assert [op for op,_ in e.calls].count('EXECUTE')==1


@pytest.mark.parametrize('kind',['expired','raw_binding','support_binding','result_binding'])
def test_saved_contract_or_deadline_failure_cannot_start_or_download(env,kind):
    e=env;s=e.snapshot()
    if kind=='expired':s.value['deadline']=s.value['client']['deadline']=time.time()-1
    elif kind=='raw_binding':s.value['raw_blob']['sha256']='0'*64
    elif kind=='support_binding':s.value['client']['archives']['support']['sha256']='0'*64
    else:s.value['client']['status']='DOWNLOADED';s.value['client']['result']=e.result_info
    s.save();e.reset_reads()
    with pytest.raises(ValueError):e.run()
    assert_no_inputs(e);assert not e.calls


def test_tampered_blob_never_uploads(env):
    e=env;s=e.snapshot();e.folders['structured'].data[s.value['raw_blob']['path']]=b'corrupt'
    e.reset_reads()
    with pytest.raises(ValueError,match='BLOB_HASH'):e.run()
    assert [op for op,_ in e.calls]==['START']


def test_failed_remote_remains_failed_without_input_reads_or_release(env):
    e=env;e.start();path=e.server/e.state['job_id']/'state.json'
    state=r.t.read(path);state.update(status='FAILED',phase='STRUCTURE');r.t.write(path,state)
    e.reset_reads()
    with pytest.raises(RuntimeError,match='PIPELINE_FAILED'):e.run()
    assert_no_inputs(e)
    assert e.snapshot().value['phase']=='FAILED'
    assert [op for op,_ in e.calls]==['START']


def test_inspection_is_bounded_read_only_deduplicated_and_no_tokens(env,capsys):
    e=env;e.start();e.folders['load'].data=copy.deepcopy(e.folders['structured'].data)
    before=copy.deepcopy({k:v.data for k,v in e.folders.items()});e.reset_reads()
    rows=fix.inspect_jobs(r,e.folders,{})
    assert len(rows)==2 and all(row['status']=='UPLOADING' for row in rows)
    assert [op for op,_ in e.calls]==['HEALTH','STATUS']
    assert {k:v.data for k,v in e.folders.items()}==before
    output=capsys.readouterr().out
    assert e.state['job_token'] not in output and e.remote.token not in output


def test_first_preparation_still_uses_original_snapshot_and_batch(env):
    e=env;work=e.tmp_path/'unpack';work.mkdir()
    r.unpack_raw(e.folders['landing'],e.folders['raw'],work)
    s=e.snapshot();s.value.pop('client');s.value.pop('raw_blob');s.save();e.reset_reads()
    assert e.run()['status']=='STRUCTURED'
    assert any('/files/01_DATA/RAW/' in p for p in e.folders['raw'].reads)
    assert [op for op,_ in e.calls].count('EXECUTE')==1
    assert e.snapshot().value['deadline']==s.value['deadline']


def test_actual_updated_recipe_bootstrap_routes_busy_to_resume_before_raw(env,monkeypatch):
    e=env;backend,project,cfg=sdk_setup(True);apply(project,e.tmp_path)
    other=copy.deepcopy(e.state);other.update(job_id='c'*32,job_token='d'*64)
    e.remote.call('START',**{k:other[k] for k in ('job_id','job_token','instance','code_sha256','archives','deadline')})
    name='DATAIKU_RECIPE_PACKAGE_20261027_R1.zip'
    e.folders['landing'].data[name]=(BASE/name).read_bytes()
    variables={'LEGAL_PIPELINE_URL':e.remote.url,'LEGAL_PIPELINE_TOKEN':e.remote.token,
               'LEGAL_RECIPE_JOB_NAME':'same-job','LEGAL_PIPELINE_SCRATCH':str(e.tmp_path)}
    fake=SimpleNamespace(default_project_key=lambda:'LEGAL_RAG',get_custom_variables=lambda:variables,
        Folder=lambda name:e.folders[next(k for k,v in cfg.items() if v==name)])
    monkeypatch.setitem(sys.modules,'dataiku',fake)
    monkeypatch.setattr(r,'structure',BASE_STRUCTURE)
    e.reset_reads()
    source=backend.items['recipes']['LEGAL_02_STRUCTURE_GENOS_R1']['payload']
    with pytest.raises(RuntimeError,match='GENOS_BUSY'):exec(compile(source,'actual-updated-recipe','exec'),{})
    assert e.folders['raw'].reads==[]
    assert [n for n in e.folders['landing'].reads if n.endswith('.zip')]==[name]
    assert [op for op,_ in e.calls]==['START']
    assert e.snapshot().value['client']['job_id']==e.state['job_id']


def sdk_setup(r2=False,backend=None):
    backend=backend or sdk.Backend();project=sdk.DSSProject(backend,'LEGAL_RAG')
    cfg=install_flow.install(project,REF['baseline_bootstrap'],'ehA8dpVm')
    if r2:
        path=HERE.parent/'pipeline_input_selection_20261027_r2/update_recipes.py'
        spec=importlib.util.spec_from_file_location('old_updater',path);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        item=backend.items['recipes']['LEGAL_02_STRUCTURE_GENOS_R1']
        _,item['payload'],_=old.expected_sources(item['payload'],'structure',REF['baseline_bootstrap'],REF['adapter_source'])
    return backend,project,cfg


def apply(project,tmp_path,action='apply'):
    return updater.update(project,REF['baseline_bootstrap'],REF['adapter_source'],
                          (HERE/'resume.py').read_text(),tmp_path/'backup',action)


@pytest.mark.parametrize('r2',[False,True])
def test_real_sdk_updates_only_02_idempotence_and_exact_rollback(tmp_path,r2):
    backend,project,cfg=sdk_setup(r2);before=copy.deepcopy(backend.items)
    assert apply(project,tmp_path)==cfg
    after=copy.deepcopy(backend.items)
    before02=before['recipes']['LEGAL_02_STRUCTURE_GENOS_R1']['payload']
    changed=copy.deepcopy(after);changed['recipes']['LEGAL_02_STRUCTURE_GENOS_R1']['payload']=before02
    assert changed==before
    backend.calls=[];apply(project,tmp_path)
    assert backend.items==after and all(method=='GET' for method,_,_ in backend.calls)
    apply(project,tmp_path,'rollback');assert backend.items==before


@pytest.mark.parametrize('kind',['code','flow'])
def test_sdk_unknown_change_is_preserved(tmp_path,kind):
    backend,project,cfg=sdk_setup()
    item=backend.items['recipes']['LEGAL_02_STRUCTURE_GENOS_R1']
    if kind=='code':item['payload']='# custom edit\n'+item['payload']
    else:item['recipe']['inputs']['main']['items'].append({'ref':'extra'})
    before=copy.deepcopy(backend.items);backend.calls=[]
    with pytest.raises(ValueError,match='CHANGED'):apply(project,tmp_path)
    assert backend.items==before and all(m=='GET' for m,_,_ in backend.calls)


def test_lost_recipe_save_reply_can_be_verified_on_repeat(tmp_path):
    class Backend(sdk.Backend):
        lose=False
        def _perform_json(self,method,path,body=None,**kwargs):
            result=super()._perform_json(method,path,body,**kwargs)
            if method=='PUT' and self.lose:
                self.lose=False;raise RuntimeError('save response lost')
            return result
    backend,project,cfg=sdk_setup(backend=Backend());backend.lose=True
    with pytest.raises(RuntimeError,match='lost'):apply(project,tmp_path)
    assert apply(project,tmp_path)==cfg


def test_delivered_notebook_and_zip_exact_and_cell_executes_sdk_and_status(env,monkeypatch):
    e=env;backend,project,cfg=sdk_setup(True)
    fake=SimpleNamespace(default_project_key=lambda:'LEGAL_RAG',api_client=lambda:backend,
        get_custom_variables=lambda:{'LEGAL_PIPELINE_URL':e.remote.url,'LEGAL_PIPELINE_TOKEN':e.remote.token},
        Folder=lambda name:e.folders[next(k for k,v in cfg.items() if v==name)])
    monkeypatch.setitem(sys.modules,'dataiku',fake);monkeypatch.chdir(e.tmp_path)
    import urllib.request
    requests=[]
    def open_request(request,timeout):
        data=json.loads(request.data);op=data.pop('API_TYPE');requests.append(op)
        try:reply={'code':0,'data':e.remote.call(op,**data)}
        except RuntimeError as exc:reply={'code':1,'error':str(exc).replace('GENOS_','',1)}
        return io.BytesIO(json.dumps(reply).encode())
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:SimpleNamespace(open=open_request))
    script=(HERE/'DATAIKU_RESUME_FIX_20261027_R3.txt').read_text()
    ast.parse(script,feature_version=(3,9));ns={};exec(compile(script,'delivered-resume','exec'),ns)
    assert requests==['HEALTH','STATUS']
    assert ns['JOB_STATUS'][0]['error']=='GENOS_JOB_LOST'
    with zipfile.ZipFile(HERE/'DATAIKU_RESUME_FIX_20261027_R3.zip') as z:
        assert z.read('DATAIKU_RESUME_FIX_20261027_R3.txt')==script.encode()
        assert all(Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
