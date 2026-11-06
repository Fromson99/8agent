"""Exercise the exact installation files against a new Git checkout and a DSS API double."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import zipfile

HERE=Path(__file__).resolve().parent


def verify(work):
    root=work/'checkout'
    subprocess.run(['git','init','-q',str(root)],check=True)
    def install(action,ok=True):
        process=subprocess.run(['bash','GENOS_INSTALL_R1.txt',action,str(root)],cwd=HERE,capture_output=True,text=True)
        if (process.returncode==0)!=ok:raise AssertionError(process.stderr)
    for op in ('check','apply','apply','verify'):install(op)
    before=(root/'service.py').read_bytes()
    (root/'service.py').write_bytes(before+b'\n')
    install('apply',ok=False)
    assert (root/'service.py').read_bytes()==before+b'\n'
    (root/'service.py').write_bytes(before)
    install('verify')
    code=(root/'CODE_PINS.json').read_bytes()
    assert hashlib.sha256(code).hexdigest()==json.loads((HERE/'CODE_MANIFEST.json').read_bytes())['server_pin']
    with zipfile.ZipFile(HERE/'DATAIKU_AGENT_FLOW_R1.zip') as z:
        for n in z.namelist():
            if n.endswith('.py'):compile(z.read(n),n,'exec')
    # Exact unmodified notebook bootstraps the uploaded production ZIP.
    by_id={}
    recipes={}
    scenarios={}
    zones={}
    class Object:
        def __init__(self,name):
            self.name=name;self.id=name
            self.type='Filesystem';self.ins=[];self.outs=[];self.code=None
        def get_settings(self):return self
        def get_raw_params(self):return {'connection':'filesystem'}
        def move_to_zone(self,z):self.zone=z
        def get_info(self,sensitive_info):return {'type':self.type,'path':str(work/self.id)}
        def get_download_stream(self,p):return (HERE/p.lstrip('/')).open('rb')
        def list_paths_in_partition(self):return ['/DATAIKU_AGENT_FLOW_R1.zip']
        def get_code(self):return self.code
        def get_flat_input_refs(self):return self.ins
        def get_flat_output_refs(self):return self.outs
        def with_input(self,x):self.ins.append(x);return self
        def with_output(self,x,append):assert append;self.outs.append(x);return self
        def with_script(self,code):self.code=code;return self
        def create(self):recipes[self.name]=self;return self
        def set_code_env(self,inherit):assert inherit
        def save(self):pass
    def create(store,name,**kw):
        assert name not in store
        store[name]=Object(name);return store[name]
    for key in ('code','docs'):create(by_id,key)
    project=types.SimpleNamespace(project_key='DEMO',get_managed_folder=by_id.__getitem__,
        get_flow=lambda:types.SimpleNamespace(list_zones=lambda:list(zones.values()),create_zone=lambda n:create(zones,n)),
        list_managed_folders=lambda:[{'name':n,'id':n} for n in by_id],
        create_managed_folder=lambda n,**kw:create(by_id,n),new_recipe=lambda kind,n:Object(n),
        list_recipes=lambda:[{'name':n} for n in recipes],get_recipe=recipes.__getitem__,
        list_scenarios=lambda:[{'name':n,'id':n} for n in scenarios],get_scenario=scenarios.__getitem__,
        create_scenario=lambda n,kind:create(scenarios,n))
    api=types.ModuleType('dataiku')
    api.api_client=lambda:types.SimpleNamespace(get_default_project=lambda:project)
    api.Folder=lambda id,**kw:by_id[id]
    sys.modules['dataiku']=api
    src=(HERE/'INSTALL_DATAIKU_R1.txt').read_text()
    for k,v in {'CODE_FOLDER_ID':'code','INPUT_FOLDER_ID':'docs','WORK_DIR':str(work/'state')}.items():
        old=repr(k)+": ''"
        assert src.count(old)==1
        src=src.replace(old,repr(k)+': '+repr(v))
    for i in range(2):
        ns={};exec(compile(src,'INSTALL_DATAIKU_R1.txt','exec'),ns)
    assert len(recipes)==3 and len(scenarios)==1 and len(by_id)==5
    for r in recipes.values():compile(r.code,r.name,'exec')
    scenario=next(iter(scenarios.values()))
    assert not scenario.active and scenario.code.count('NON_RECURSIVE_FORCED_BUILD')==3
    assert recipes['LGL_AGENT_R1_DEV_03_LOAD'].ins==['code','LGL_AGENT_R1_DEV_02_WAIT_AGENT_OUT']
    return {'server_checkout_files':len(json.loads(code)['files'])+1,'server_pin':hashlib.sha256(code).hexdigest(),
            'install_conflict_rejected':True,'double_install_recipes':len(recipes),
            'scenarios':len(scenarios),'installed_without_running':True,'installer_test':'DSS API double'}


if __name__=='__main__':
    with tempfile.TemporaryDirectory() as tmp:
        print(json.dumps(verify(Path(tmp)),sort_keys=True))
