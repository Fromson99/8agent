import io,json,os,hashlib,subprocess,sys,time,types,zipfile
from pathlib import Path
import pytest
from test_compute import env,Folder,module,HERE


def sources(env,entries=None):
    import selection as s
    entries=entries or {'01_DATA/RAW/문서'+e:('real fixture '+e).encode() for e in s.EXTENSIONS}
    raw=Folder();landing=Folder();items={};snapshot='a'*64
    for name,body in entries.items():
        path='snapshots/'+snapshot+'/files/'+name;raw.files[path]=body
        items[name]={'path':path,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)}
    record={'format':'legal-raw-s3-v1','archive_sha256':snapshot,'archive_bytes':200,'files':items}
    raw.files['snapshots/'+snapshot+'/manifest.json']=json.dumps(record).encode()
    landing.files['RAW_INPUT.zip.receipt.json']=json.dumps({'archive':'RAW_INPUT.zip','sha256':snapshot,'bytes':200}).encode()
    return raw,landing,record


def cfg():return dict(landing='ehA8dpVm',raw='raw',structured='structured',load='load',connection='connection')


class Project:
    def list_recipes(self):return [{'name':'LEGAL_02_STRUCTURE_GENOS_R1_NP'}]
    def get_recipe(self,name):return types.SimpleNamespace(get_settings=lambda:types.SimpleNamespace(get_code=lambda:"run_recipe('structure',"+repr(cfg())+")"))


def test_pick_actual_one_each_and_stable_smallest(env):
    import selection as s
    raw,land,record=sources(env,{'01_DATA/RAW/'+n:b for n,b in [('empty.doc',b''),('b.doc',b'abc'),('a.doc',b'abc'),('large.doc',b'12345'),('~$skip.doc',b'x'),('x.DOCX',b'abc'),('x.hwp',b'1'),('x.hwpx',b'12')]})
    assert s.discover(Project())==cfg()
    assert s.snapshot(land,raw)==record
    selected=s.pick(raw,record,env.tmp/'samples')
    assert all(r['status']=='SELECTED' for r in selected['documents'])
    assert selected['documents'][0]['source_name']=='01_DATA/RAW/a.doc'
    assert len(list((env.tmp/'samples').iterdir()))==4


def test_pick_zip_member_missing_and_source_corruption(env):
    import selection as s
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:z.writestr('압축/원문.HWP',b'actual member')
    raw,land,record=sources(env,{'01_DATA/RAW/archive.zip':buffer.getvalue(),'01_DATA/RAW/x.docx':b'office'})
    selected=s.pick(raw,record,env.tmp/'one')
    assert [r['status'] for r in selected['documents']]==['NOT_FOUND','SELECTED','SELECTED','NOT_FOUND']
    assert (env.tmp/'one/sample.hwp').read_bytes()==b'actual member'
    assert not list((env.tmp/'one').glob('*.zip'))
    record['files']['01_DATA/RAW/x.docx']['sha256']='f'*64
    with pytest.raises(ValueError,match='SOURCE_OBJECT_HASH'):s.pick(raw,record,env.tmp/'two')


def test_snapshot_not_latest_arbitrary_or_unbound(env):
    import selection as s
    raw,land,record=sources(env)
    record['files']['01_DATA/RAW/문서.doc']['path']='snapshots/other/file.doc'
    raw.files['snapshots/'+'a'*64+'/manifest.json']=json.dumps(record).encode()
    with pytest.raises(ValueError,match='SOURCE_OBJECT_INVALID'):s.snapshot(land,raw)


def test_config_existing_and_no_per_document_yaml(env,monkeypatch):
    import probe_runtime as p,yaml
    monkeypatch.delenv('GENOS_STRUCTURE_CONFIG',raising=False)
    monkeypatch.setattr(sys,'path',[str(env.tmp/'image')])
    target=env.tmp/'image/resource/parser_processor_config.yaml';target.parent.mkdir(parents=True)
    target.write_text('layout: {layout_model_type: genos_layout}\nocr: {}\nweights_path: models/a\nenrichment: [summary]\noutput: {format: chunks}\n')
    text,origin=p.normalized(env.root);config=yaml.safe_load(text)
    assert origin['source_kind']=='IMAGE' and config['enrichment']==[] and config['output']['format']=='docling'
    assert config['weights_path']==str(target.parent/'models/a')
    assert yaml.safe_load(target.read_text())['enrichment']==['summary']
    monkeypatch.setenv('GENOS_STRUCTURE_CONFIG','/nonexistent')
    assert p.inspect(env.root)['errors']==['POD_CONFIG_ENV_PATH_INVALID']


def test_config_missing_ambiguous_and_vendor_example_ignored(env,monkeypatch):
    import probe_runtime as p
    monkeypatch.delenv('GENOS_STRUCTURE_CONFIG',raising=False)
    bases=[env.tmp/'pod_vendor',env.tmp/'first',env.tmp/'second']
    monkeypatch.setattr(sys,'path',[str(x) for x in bases])
    for i,b in enumerate(bases):
        f=b/'resource/parser_processor_config.yaml';f.parent.mkdir(parents=True);f.write_text('layout: {}\nocr: {}\nid: '+str(i))
    assert p.inspect(env.root)['errors']==['POD_EXISTING_PARSER_CONFIG_AMBIGUOUS']
    for b in bases[1:]:(b/'resource/parser_processor_config.yaml').unlink()
    assert p.inspect(env.root)['errors']==['POD_EXISTING_PARSER_CONFIG_NOT_FOUND']


def test_probe_purpose_bound_to_same_handle(env,monkeypatch):
    import probe_runtime as p
    monkeypatch.setattr(p,'inspect',lambda root:{'ready':True,'config_sha256':'e'*64,'errors':[]})
    health=env.api.handle({'API_TYPE':'PROBE_HEALTH'})
    assert health['probe_purpose']=='document-format-probe-v1'
    data=dict(API_TYPE='OPEN',handle='c'*32,handle_token='d'*64,instance=health['instance'],code_sha256=health['code_sha256'],parser_config_sha256='e'*64,archives={'raw':{'bytes':1,'sha256':'a'*64},'support':{'bytes':1,'sha256':'b'*64}},deadline=time.time()+600,purpose=health['probe_purpose'])
    env.api.handle(data)
    assert env.api.HANDLES['c'*32]['purpose']==health['probe_purpose']
    with pytest.raises(ValueError):env.api.handle({**data,'purpose':'pipeline'})


def synthetic_runtime(env,monkeypatch):
    import fitz
    from docling_core.types.doc import DoclingDocument,DocItemLabel,Size
    doc=DoclingDocument(name='synthetic');doc.add_page(page_no=1,size=Size(width=595,height=842));doc.add_text(label=DocItemLabel.TEXT,text='제1조 모의 파싱 결과입니다.')
    facade=env.root/'pod_vendor/genon/preprocessor/facade/parser_processor.py'
    facade.write_text('''import os,fitz
class DocumentProcessor:
    def __init__(self,config_path):pass
    async def __call__(self,request,file_path,**kwargs):
        with fitz.open(file_path) as pdf:text=''.join(p.get_text() for p in pdf)
        if os.environ.get('FAIL_PARSE') and '.hwpx' in text:raise RuntimeError('synthetic parse failure')
        return '''+repr({'document':doc.model_dump(mode='json')})+'\n')
    pins=json.loads((env.root/'CODE_PINS.json').read_text());pins['files'][str(facade.relative_to(env.root))]=env.t.sha(facade)
    (env.root/'CODE_PINS.json').write_text(json.dumps(pins,sort_keys=True)+'\n')
    binary=env.tmp/'bin';binary.mkdir();soffice=binary/'soffice'
    soffice.write_text('#!'+sys.executable+'''\nimport os,sys,fitz
from pathlib import Path
p=Path(sys.argv[-1])
if os.environ.get('FAIL_CONVERT') and p.suffix=='.hwp':raise SystemExit(1)
out=Path(sys.argv[sys.argv.index('--outdir')+1])/p.with_suffix('.pdf').name
pdf=fitz.open();page=pdf.new_page(width=595,height=842);page.insert_text((40,40),'Fixture '+p.suffix);pdf.save(out)
''');soffice.chmod(0o755)
    config=env.tmp/'parser.yaml';config.write_text('layout:\n  layout_model_type: genos_layout\n  genos_layout:\n    endpoint: http://fixture.invalid/layout\nocr:\n  ocr_mode: disable\nenrichment: []\noutput:\n  format: docling\n')
    monkeypatch.setenv('GENOS_STRUCTURE_CONFIG',str(config));monkeypatch.setenv('PATH',str(binary)+':'+os.environ['PATH'])
    import probe_runtime
    probe_runtime.checked_runtime.cache_clear()
    return probe_runtime.require(env.root)


def inputs(env,missing=False,extra=False):
    import selection as s
    raw,landing,record=sources(env)
    if missing:del record['files']['01_DATA/RAW/문서.hwp']
    chosen=s.pick(raw,record,env.tmp/'samples')
    folder=env.tmp/'job';folder.mkdir();(folder/'compute.log').write_text('fixture\n')
    env.t.write(folder/'selection.json',chosen);paths={'selection.json':folder/'selection.json'}
    for r in chosen['documents']:
        if r['status']=='SELECTED':paths['documents/'+r['file']]=env.tmp/'samples'/r['file']
    if extra:paths['documents/extra.doc']=env.tmp/'samples/sample.doc'
    purpose={'purpose':'document-format-probe-v1'}
    raw=env.t.pack(paths,folder/'raw.zip',metadata=purpose)
    env.t.write(folder/'control.json',purpose);support=env.t.pack({'control.json':folder/'control.json'},folder/'support.zip',metadata=purpose)
    return folder,{key:{k:value[k] for k in ('bytes','sha256')} for key,value in [('raw',raw),('support',support)]},chosen


@pytest.mark.parametrize('scenario',['pass','convert_failure','parse_failure','missing','extra'])
def test_final_worker_four_documents(env,monkeypatch,scenario):
    if scenario=='convert_failure':monkeypatch.setenv('FAIL_CONVERT','1')
    if scenario=='parse_failure':monkeypatch.setenv('FAIL_PARSE','1')
    info=synthetic_runtime(env,monkeypatch)
    folder,archives,selected=inputs(env,missing=scenario=='missing',extra=scenario=='extra')
    r=subprocess.run([sys.executable,'-B',str(env.root/'sample_worker.py'),str(folder),json.dumps(archives),info['config_sha256']],cwd=env.root,capture_output=True,text=True,timeout=50)
    if scenario=='extra':
        assert r.returncode and 'PROBE_EXTRA_INPUT' in r.stderr and not (folder/'result.zip').exists();return
    assert r.returncode==0,r.stderr
    result=env.t.read(folder/'probe-output/summary.json');rows=result['documents']
    assert result['status']==('PASS' if scenario=='pass' else 'COMPLETED_WITH_FAILURE_OR_MISSING')
    assert len(rows)==4 and result['application_review_calls']==0 and not result['sql_writes'] and not result['indexing']
    assert not (folder/'effective-parser.yaml').exists()
    for row in rows:
        if row['status']=='PASS':
            directory=folder/'probe-output'/row['extension'][1:]
            assert row['conversion']==row['parsing']=='PASS' and row['original_unchanged']
            assert '제1조' in (directory/'parsed.txt').read_text()
    if scenario=='convert_failure':assert rows[2]['conversion']=='FAILED' and rows[3]['status']=='PASS'
    if scenario=='parse_failure':assert rows[3]['conversion']=='PASS' and rows[3]['parsing']=='FAILED' and (folder/'probe-output/hwpx/result.pdf').is_file()
    if scenario=='missing':assert rows[2]['status']=='NOT_FOUND'
    with zipfile.ZipFile(folder/'result.zip') as z:assert not any(n.endswith('.yaml') for n in z.namelist())


def client_environment(env,monkeypatch):
    import probe_client as p,probe_runtime
    raw,landing,record=sources(env);structured=Folder();folders={'raw':raw,'ehA8dpVm':landing,'structured':structured}
    dataiku=types.SimpleNamespace(default_project_key=lambda:'LEGAL_RAG',api_client=lambda:types.SimpleNamespace(get_project=lambda _:Project()),Folder=folders.__getitem__,get_custom_variables=lambda:{})
    calls=[]
    class Wire:
        url='https://fixture.invalid/compute'
        def call(self,op,**kwargs):calls.append(op);return env.api.handle({'API_TYPE':op,**kwargs})
    monkeypatch.setattr(p.c,'remote',lambda _:Wire())
    monkeypatch.setattr(probe_runtime,'inspect',lambda _:{'ready':True,'config_sha256':'e'*64,'errors':[]})
    return p,dataiku,structured,calls


def make_return(env,h):
    folder=h['folder'];env.t.unpack(folder/'raw.zip',folder/'input',prefixes=('documents/','selection.json'))
    selected=env.t.read(folder/'input/selection.json')
    # Valid failure rows exercise transport/storage without faking parsing success.
    result={'status':'COMPLETED_WITH_FAILURE_OR_MISSING','documents':[{**r,'status':'FAILED','conversion':'FAILED','parsing':'NOT_RUN'} for r in selected['documents']]}
    path=folder/'summary.json';env.t.write(path,result)
    info=env.t.pack({'probe/summary.json':path},folder/'result.zip',metadata={'purpose':'document-format-probe-v1','complete':True,'code_sha256':env.c.EXPECTED})
    h.update(state='COMPLETE',result={k:info[k] for k in ('bytes','sha256')})


def test_client_full_transport_and_repeat_no_second_compute(env,monkeypatch):
    p,dku,folder,calls=client_environment(env,monkeypatch)
    hits=[]
    def compute(h):hits.append(h['id']);make_return(env,h)
    monkeypatch.setattr(env.api,'run_compute',compute)
    first=p.run(dku,env.tmp/'first');assert len(hits)==1 and len(first['documents'])==4
    assert not env.api.HANDLES and 'PUT' in calls and 'READ' in calls
    assert any(k.endswith('/summary.json') for k in folder.files)
    calls.clear();second=p.run(dku,env.tmp/'second')
    assert second==first and not calls and len(hits)==1


def test_uncertain_run_reply_resumes_same_handle_deadline(env,monkeypatch):
    p,dku,folder,calls=client_environment(env,monkeypatch);hits=[]
    def compute(h):hits.append(h['id']);make_return(env,h)
    monkeypatch.setattr(env.api,'run_compute',compute)
    remote=p.c.remote;flag=[True]
    class Uncertain:
        url='https://fixture.invalid/compute'
        def call(self,op,**kwargs):
            answer=remote({}).call(op,**kwargs)
            if op=='RUN' and flag[0]:flag[0]=False;raise TimeoutError('lost response')
            return answer
    monkeypatch.setattr(p.c,'remote',lambda _:Uncertain())
    with pytest.raises(TimeoutError):p.run(dku,env.tmp/'first')
    deadline=list(env.api.HANDLES.values())[0]['deadline'];time.sleep(.05)
    result=p.run(dku,env.tmp/'second');assert len(hits)==1 and len(result['documents'])==4
    checkpoints=[json.loads(b) for n,b in folder.files.items() if '/checkpoints/' in n and n.endswith('.json')]
    assert all(v['deadline']>=deadline for v in checkpoints if 'deadline' in v)


def test_bad_return_source_not_published(env,monkeypatch):
    import probe_client as p
    raw,land,record=sources(env);import selection as s
    selected=s.pick(raw,record,env.tmp/'samples')
    folder=Folder();store=p.ManagedJob(p.Scope(folder),'probe',{'code':env.c.EXPECTED});store.value['selection']=selected;store.save()
    rows=[{**r,'status':'FAILED','conversion':'FAILED','parsing':'NOT_RUN'} for r in selected['documents']];rows[0]['sha256']='f'*64
    file=env.tmp/'summary.json';env.t.write(file,{'status':'COMPLETED_WITH_FAILURE_OR_MISSING','documents':rows})
    archive=env.tmp/'result.zip';env.t.pack({'probe/summary.json':file},archive,metadata={'purpose':p.PURPOSE,'complete':True,'code_sha256':env.c.EXPECTED})
    with pytest.raises(ValueError,match='PROBE_RETURN_SOURCE_BINDING'):p.publish(store,archive,env.tmp/'publish','probe')
    assert not any('/reports/' in n for n in folder.files)


def test_partial_cancel_normalizes_four_rows_no_pass(env):
    import probe_client as p,selection as s
    raw,land,record=sources(env);selected=s.pick(raw,record,env.tmp/'samples')
    folder=Folder();store=p.ManagedJob(p.Scope(folder),'probe',{'code':env.c.EXPECTED});store.value.update(selection=selected,last_state='CANCELLED')
    file=env.tmp/'summary.json';env.t.write(file,{'status':'RUNNING','documents':[{**selected['documents'][0],'status':'RUNNING','conversion':'RUNNING','parsing':'NOT_RUN'}]})
    archive=env.tmp/'audit.zip';env.t.pack({'probe/summary.json':file},archive,metadata={'purpose':p.PURPOSE,'complete':False})
    result=p.publish(store,archive,env.tmp/'publish','probe')
    assert result['status']=='CANCELLED' and len(result['documents'])==4
    assert all(r['status']=='INTERRUPTED' for r in result['documents'])
    assert result['documents'][0]['conversion']=='INTERRUPTED'


def test_config_changed_after_health_rejected_before_worker(env,monkeypatch):
    import probe_runtime as p
    monkeypatch.setattr(p,'normalized',lambda _:('new text',{'source_kind':'ENV'}))
    monkeypatch.setattr(p,'checked_runtime',lambda *args:{'config':'new'})
    with pytest.raises(ValueError,match='POD_PROBE_CONFIG_CHANGED'):
        with p.use(env.root,env.tmp,'a'*64):pass
    assert not (env.tmp/'effective-parser.yaml').exists()


@pytest.mark.parametrize('case',['zero','nonzero','missing','tampered','count_mismatch','exhausted'])
def test_r4_migration_keeps_original_budget_and_review_proof(env,tmp_path,case):
    r4=module('r4_migration_regression',HERE.parent/'pipeline_pod_20261028_r4/test_pod.py')
    r4.OLD='8789724175dbe2177eb52c535a6e6b2279af7a4687d7fb0ec24c28a241e52685'
    r4.test_r3_migration_budget_proof(env,tmp_path,case)


