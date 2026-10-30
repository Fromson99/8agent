import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import types
import zipfile
import pytest
from dataikuapi.dss.project import DSSProject
from vector_silver.install import install, RECIPE, RESULT, RESULT_PATH, DATASETS
from vector_silver import runtime as rt
from semantic_runtime.initial_vector import VectorError

HERE=Path(__file__).resolve().parents[1]

class Folder:
    def __init__(self): self.values={}; self.writes=[]
    def list_paths_in_partition(self): return list(self.values)
    def get_download_stream(self,p): return io.BytesIO(self.values[p])
    def upload_stream(self,p,b): self.values[p]=b.read() if hasattr(b,'read') else b; self.writes.append(p)

class Backend:
    def get_project(self,key):return DSSProject(self,key)
    def __init__(self):
        self.items={'managedfolders':{
            'ehA8dpVm':{'id':'ehA8dpVm','name':'landing','type':'S3','params':{'connection':'OBS_DP_PUBLIC','bucket':'fixture','path':'/landing'}}},
            'recipes':{},'datasets':{n:{'name':n,'type':'Oracle','managed':False,
                'params':{'connection':'AIDP','schema':'SIDDS','table':n,'mode':'table'}} for n in DATASETS},
            'variables':{'standard':{},'local':{}}}
        self.calls=[]
    def _perform_json(self,method,path,body=None,**kwargs):
        self.calls.append((method,path))
        parts=path.strip('/').split('/'); assert parts[:2]==['projects','LEGAL_RAG']
        kind=parts[2]
        if kind=='variables':
            if method=='GET': return copy.deepcopy(self.items[kind])
            self.items[kind]=copy.deepcopy(body); return {}
        values=self.items[kind]
        if len(parts)==3:
            if method=='GET': return copy.deepcopy([v['recipe'] if kind=='recipes' else v for v in values.values()])
            if kind=='recipes':
                proto=copy.deepcopy(body['recipePrototype']);proto.setdefault('params',{'envSelection':{'envMode':'INHERIT'}})
                name=proto['name']; values[name]={'recipe':proto,'payload':body['creationSettings']['script']};return {'name':name}
            value=copy.deepcopy(body);name='f'+str(len(values));value['id']=name;values[name]=value;return {'id':name}
        name=parts[3]
        if method=='GET':return copy.deepcopy(values[name])
        values[name]=copy.deepcopy(body);return {}
    _perform_empty=_perform_json

def refs(b,kind): return {x['ref'] for x in b.items['recipes'][RECIPE]['recipe'][kind]['main']['items']}

def test_install_without_any_import_recipe_and_reinstall_readonly():
    b=Backend();p=DSSProject(b,'LEGAL_RAG')
    cfg=install(p,'# verified code\n',query_release_id='a'*64)
    assert refs(b,'inputs')=={'ehA8dpVm','LGL_SRCH_PBLS_S'}
    assert refs(b,'outputs')=={cfg['output'],'LGL_VCTR_SET_S','LGL_VCTR_ITEM_S'}
    assert set(b.items['recipes'])=={RECIPE} and 'load' not in cfg
    assert all(i['appendMode'] for i in b.items['recipes'][RECIPE]['recipe']['outputs']['main']['items'])
    before=copy.deepcopy(b.items);b.calls=[]
    assert install(p,'# verified code\n')==cfg and b.items==before
    assert all(m=='GET' for m,_ in b.calls)

@pytest.mark.parametrize('fault',['owner','managed','producer','code','missing','pin','local_override'])
def test_conflict_preserves_project(fault):
    b=Backend();p=DSSProject(b,'LEGAL_RAG');kwargs={}
    if fault=='owner':b.items['datasets'][DATASETS[0]]['params']['schema']='WRONG'
    if fault=='managed':b.items['datasets'][DATASETS[0]]['managed']=True
    if fault=='missing':del b.items['datasets'][DATASETS[1]]
    if fault=='pin':kwargs['query_release_id']='latest'
    if fault=='local_override':
        b.items['variables']['local']['LEGAL_VECTOR_QUERY_RELEASE']='b'*64
        kwargs['query_release_id']='a'*64
    if fault=='producer':b.items['recipes']['OLD']={'recipe':{'name':'OLD','type':'python','inputs':{},'outputs':{'main':{'items':[{'ref':DATASETS[0]}]}}},'payload':'# old'}
    if fault=='code':
        install(p,'# custom')
    before=copy.deepcopy(b.items);b.calls=[]
    with pytest.raises(ValueError):install(p,'# current',**kwargs)
    assert b.items==before and all(m=='GET' for m,_ in b.calls)

def test_upgrade_sealed_r3_reuses_folder_and_backs_up(monkeypatch):
    b=Backend();p=DSSProject(b,'LEGAL_RAG');folder=Folder()
    b.items['managedfolders']['out']={'id':'out','name':RESULT,'type':'S3','params':{'connection':'OBS_DP_PUBLIC','bucket':'fixture','path':RESULT_PATH}}
    b.items['managedfolders']['prior']={'id':'prior','name':'LEGAL_VECTOR_SILVER_RESULT_R3','type':'S3','params':{}}
    cfg={'landing':'ehA8dpVm','load':'load','output':'out','legacy':'prior'}
    code=(HERE/'LEGACY_BOOTSTRAP.txt').read_text()+'\nfrom vector_silver.runtime import run\nrun('+repr(cfg)+', action="build")\n'
    b.items['recipes'][RECIPE]={'recipe':{'name':RECIPE,'type':'python','inputs':{'main':{'items':[{'ref':x} for x in ('ehA8dpVm','load','prior')]}},'outputs':{'main':{'items':[{'ref':'out','appendMode':True}]}},'params':{}},'payload':code}
    original=copy.deepcopy(b.items['recipes'][RECIPE])
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(Folder=lambda x:folder))
    cfg=install(p,'# new bootstrap\n')
    assert cfg['output']=='out' and cfg['legacy']=='prior' and len(b.items['managedfolders'])==3
    assert refs(b,'inputs')=={'ehA8dpVm',DATASETS[0]}
    backup=json.loads(next(iter(folder.values.values())))
    assert backup['recipe']==original['recipe'] and backup['code']==original['payload']
    before=copy.deepcopy(b.items);b.calls=[]
    assert install(p,'# new bootstrap\n')==cfg and b.items==before
    assert len(folder.writes)==1 and all(m=='GET' for m,_ in b.calls)

def runtime_fixture(monkeypatch):
    out=Folder(); folders=[]
    config={'schema_version':'legal-vector-profile-v1','model':'fixture','revision':'r1','dimensions':2,
            'endpoint_sha256':hashlib.sha256(b'https://example.invalid/api/gateway/rep/serving/3').hexdigest(),
            'chunk_chars':800,'overlap_chars':100,'normalization':'l2','metric':'COSINE'}
    variables={'LEGAL_VECTOR_PROFILE':config,'LEGAL_VECTOR_QUERY_RELEASE':'a'*64,'GENOS_BASE_URL':'https://example.invalid',
               'GENOS_EMBED_SERVING_ID':'3','GENOS_EMBED_KEY':'fixture'}
    def get_folder(n):
        folders.append(n);assert n=='out';return out
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(get_custom_variables=lambda:variables,
        SQLExecutor2=lambda **k:None,default_project_key=lambda:'LEGAL_RAG',Folder=get_folder))
    monkeypatch.setattr(rt,'DataikuClient',lambda *a,**k:types.SimpleNamespace(identity=lambda:('binding',{})))
    class FakeSQL:
        def __init__(self,*a,**k):self.calls=0;self.deadline=time.monotonic()+600
    monkeypatch.setattr(rt,'SQL',FakeSQL)
    monkeypatch.setattr(rt,'validate',lambda s:{'columns':6})
    snapshot=types.SimpleNamespace(release_id='b'*64,dataset_version='c'*64,excluded={'excluded'},
        manifest={'scope':{'document_version_ids':['doc','excluded']}})
    manifest={'source_release_id':'b'*64,'dataset_version':'c'*64,'source_manifest':snapshot.manifest,'tables':{'source.integrity':{}}}
    selection_calls=[]
    def select(sql,**kw):
        selection_calls.append(kw);return {'release_id':kw['release_id'],'revision':None,'manifest':manifest}
    monkeypatch.setattr(rt,'select_release',select)
    monkeypatch.setattr(rt,'Snapshot',types.SimpleNamespace(open=lambda *a:snapshot))
    scopes=[]
    def request(sql,q,rev,s,m,docs):
        scopes.append(docs);return types.SimpleNamespace(sql=sql,release_id=q)
    monkeypatch.setattr(rt,'_request',request)
    class Encoder:
        def __init__(self,*a,**k):self.calls=0
        def encode(self,texts):self.calls+=1;return [[1.0,0.0] for _ in texts]
    monkeypatch.setattr(rt,'Encoder',Encoder)
    state={'fail':False,'builds':0}
    class Publisher:
        def __init__(self,request,config,encoder,save):self.request=request;self.encoder=encoder;self.save=save
        def build(self):
            state['builds']+=1;self.request.sql.calls+=2
            self.encoder.encode(['x'])
            if state['fail']:raise RuntimeError('partial build')
            return {'status':'READY','publication_id':'p'*64,'query_release_id':'a'*64,'count':1}
    monkeypatch.setattr(rt,'Publisher',Publisher)
    return out,variables,manifest,snapshot,state,scopes,selection_calls,folders

def test_direct_check_and_build_without_load_folder(monkeypatch):
    out,variables,m,s,state,scopes,calls,folders=runtime_fixture(monkeypatch)
    cfg={'output':'out'}
    checked=rt.run(cfg,action='check')
    assert checked['status']=='CHECKED' and checked['embedding_calls']==0
    assert state['builds']==0 and not any('build-state' in p for p in out.values)
    result=rt.run(cfg,action='build')
    assert result['status']=='READY' and result['embedding_calls']==1
    assert scopes==[{'doc'},{'doc'}] and set(folders)=={'out'}
    assert calls==[{'release_id':'a'*64,'channel':None}]*2

def test_failure_and_resume_preserves_prior_deadline_and_budgets(monkeypatch):
    out,v,m,s,state,*_=runtime_fixture(monkeypatch)
    work=rt.digest(['a'*64,v['LEGAL_VECTOR_PROFILE']]);path='/vector/'+work+'/build-state.json'
    old={'work_key':work,'target_binding':'binding','started_at':time.time()-100,'embedding_calls':7,
         'sql_calls':20,'sql_reserved':128,'receipt_sha256':'old-load-receipt','receipt_path':'jobs/old/complete.json'}
    out.values[path]=json.dumps(old).encode()
    state['fail']=True
    with pytest.raises(RuntimeError,match='partial'):rt.run({'output':'out'},action='build')
    failed=json.loads(out.values[path]);assert failed['status']=='FAILED' and failed['embedding_calls']==8
    state['fail']=False
    result=rt.run({'output':'out'},action='build')
    saved=json.loads(out.values[path])
    assert result['embedding_calls']==9 and saved['started_at']==old['started_at']
    assert saved['receipt_sha256']==old['receipt_sha256'] and saved['sql_calls']>=132

@pytest.mark.parametrize('fault',['missing_pin','mismatch','no_integrity','changed_binding','expired','wrong_target','budget'])
def test_invalid_source_or_resume_stops_before_embedding(monkeypatch,fault):
    out,v,m,s,state,*_=runtime_fixture(monkeypatch)
    work=rt.digest(['a'*64,v['LEGAL_VECTOR_PROFILE']]);path='/vector/'+work+'/build-state.json'
    old={'work_key':work,'target_binding':'binding','started_at':time.time()-10}
    if fault=='missing_pin':v.pop('LEGAL_VECTOR_QUERY_RELEASE')
    if fault=='mismatch':m['dataset_version']='d'*64
    if fault=='no_integrity':m['tables']={}
    if fault=='changed_binding':old['source_binding_sha256']='bad'
    if fault=='expired':old['started_at']=time.time()-8*24*3600
    if fault=='wrong_target':old['target_binding']='wrong'
    if fault=='budget':old['embedding_calls']=rt.MAX_EMBED
    out.values[path]=json.dumps(old).encode()
    with pytest.raises(VectorError):rt.run({'output':'out'},action='build')
    if fault!='budget':assert state['builds']==0
    saved=json.loads(out.values[path]);assert saved.get('embedding_calls',0)==old.get('embedding_calls',0)

def test_real_catalog_rejects_incomplete_and_tampered_manifest(monkeypatch):
    import semantic_runtime.oracle_query_catalog as catalog
    value={'schema_version':catalog.SCHEMA,'status':'COMPLETE','source_release_id':'b'*64,'dataset_version':'c'*64}
    monkeypatch.setattr(catalog,'clob_text',lambda *a,**k:json.dumps(value))
    sql=types.SimpleNamespace(client=types.SimpleNamespace(schema_map=None))
    good=catalog.digest(value)
    assert catalog.read_release(sql,good)==value
    value['status']='BUILDING'
    with pytest.raises(Exception,match='QUERY_RELEASE_BINDING'):catalog.read_release(sql,catalog.digest(value))
    value['status']='COMPLETE';value['dataset_version']='d'*64
    with pytest.raises(Exception,match='QUERY_RELEASE_BINDING'):catalog.read_release(sql,good)

def test_package_and_literal_cells():
    with zipfile.ZipFile(HERE/'ORACLE_VECTOR_ONLY_CODE_20261029_R1.zip') as z:
        manifest=json.loads(z.read('CODE_MANIFEST.json'))
        assert set(z.namelist())==set(manifest['files'])|{'CODE_MANIFEST.json'}
        assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in manifest['files'].items())
        assert not any(n.endswith(('.sqlite','.db','.env')) for n in z.namelist())
    for n in ('DATAIKU_INSTALL.txt','DATAIKU_RUN.txt','DATAIKU_INVENTORY.txt'):
        compile((HERE/n).read_text(),n,'exec')
    assert json.loads((HERE/'BUILD_RECEIPT.json').read_text())['base_backend_identical']

def test_literal_install_cell_in_clean_process():
    import ast
    import subprocess
    tree=ast.parse(Path(__file__).read_text())
    backend=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Backend')
    child='import copy,io,json,sys,types\nfrom pathlib import Path\n'
    child+='sys.path.insert(0,"/tmp/a8-vector-sdk/dataiku_api_client-15.2.0")\nfrom dataikuapi.dss.project import DSSProject\n'
    child+='DATASETS='+repr(DATASETS)+'\n'+ast.unparse(backend)+'\n'
    child+='b=Backend(); p=DSSProject(b,"LEGAL_RAG")\n'
    child+='dataiku=types.ModuleType("dataiku")\n'
    child+='dataiku.Folder=lambda n:types.SimpleNamespace(get_download_stream=lambda f:io.BytesIO((Path('+repr(str(HERE))+')/f).read_bytes()))\n'
    child+='dataiku.api_client=lambda:types.SimpleNamespace(get_default_project=lambda:p)\nsys.modules["dataiku"]=dataiku\n'
    child+='exec(compile(Path('+repr(str(HERE/'DATAIKU_INSTALL.txt'))+').read_text(),"install-cell","exec"))\n'
    child+='assert set(b.items["recipes"])=={"LEGAL_04_VECTOR_SILVER_R4"}\n'
    result=subprocess.run([sys.executable,'-c',child],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert 'FLOW_READY' in result.stdout

def test_backup_failure_keeps_existing_recipe(monkeypatch):
    b=Backend();p=DSSProject(b,'LEGAL_RAG')
    b.items['managedfolders']['out']={'id':'out','name':RESULT,'type':'S3','params':{'connection':'OBS_DP_PUBLIC','bucket':'fixture','path':RESULT_PATH}}
    cfg={'landing':'ehA8dpVm','load':'load','output':'out','legacy':None}
    code=(HERE/'LEGACY_BOOTSTRAP.txt').read_text()+'\nfrom vector_silver.runtime import run\nrun('+repr(cfg)+', action="build")\n'
    b.items['recipes'][RECIPE]={'recipe':{'name':RECIPE,'type':'python','inputs':{'main':{'items':[{'ref':'ehA8dpVm'},{'ref':'load'}]}},'outputs':{'main':{'items':[{'ref':'out'}]}},'params':{}},'payload':code}
    before=copy.deepcopy(b.items)
    def fail(*a):raise OSError('backup unavailable')
    monkeypatch.setitem(sys.modules,'dataiku',types.SimpleNamespace(Folder=lambda n:types.SimpleNamespace(upload_stream=fail)))
    with pytest.raises(OSError,match='backup unavailable'):install(p,'# new\n')
    assert b.items==before
