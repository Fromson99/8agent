from pathlib import Path
import json,os,socket,subprocess,sys,time,urllib.request
import pytest

C=Path(os.environ['LOOP_TEST_CODE_ROOT'])

def environment():
    # No inherited Python path, model/DB credentials, or loaded test modules.
    return {'PATH':os.environ['PATH'],'LANG':'C.UTF-8','DP':'oracle','PYTHONDONTWRITEBYTECODE':'1',
            'GENOS_SYSTEM_LOG_DIR':'/__startup_fixture_unmounted__/logs',
            'GENOS_RUNTIME_DIR':'/__oracle_agent__/runtime','GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0'}


@pytest.mark.parametrize('oracle',['oracle',''])
@pytest.mark.parametrize('different_cwd',[False,True])
def test_clean_exact_script_check_without_pythonpath(tmp_path,oracle,different_cwd):
    env=environment();env['DP']=oracle
    # Non-Oracle diagnostics would be allowed to spool; disable only in this
    # control. Oracle tests exercise the unchanged mount guard while enabled.
    if not oracle:env['GENOS_SYSTEM_LOG_ENABLED']='0'
    p=subprocess.run([sys.executable,'-I',str(C/'08_DEPLOYMENT/GENOS/start_sse.py'),'--check'],
                     cwd=tmp_path if different_cwd else C,env=env,text=True,capture_output=True,timeout=20)
    assert p.returncode==0,p.stdout+p.stderr
    data=json.loads(p.stdout.splitlines()[-1]);assert data['code_root']==str(C)
    assert data['app']=='stream_app:app'
    assert not Path('/__startup_fixture_unmounted__').exists()


def test_direct_stream_module_import_before_any_backend_import(tmp_path):
    source='''import importlib.util,sys,json
assert 'semantic_runtime' not in sys.modules
spec=importlib.util.spec_from_file_location('direct_http',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
print(json.dumps({'title':module.app.title,'service_loaded':'service' in sys.modules}))
'''
    p=subprocess.run([sys.executable,'-I','-c',source,str(C/'08_DEPLOYMENT/GENOS/stream_app.py')],
                     cwd=tmp_path,env=environment(),text=True,capture_output=True,timeout=20)
    assert p.returncode==0,p.stdout+p.stderr
    assert json.loads(p.stdout.splitlines()[-1])['service_loaded'] is False


def test_actual_start_command_and_http_routes_without_db_or_model(tmp_path):
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env=environment();env['PORT']=str(port);env['WEB_CONCURRENCY']='4'
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(path,payload=None):
        raw=None if payload is None else json.dumps(payload).encode()
        req=urllib.request.Request('http://127.0.0.1:'+str(port)+path,data=raw,headers={'Content-Type':'application/json'})
        with opener.open(req,timeout=5) as response:return response.status,response.read().decode()
    with (tmp_path/'server.log').open('w') as log:
        # Exactly the photographed command: no -I, --port or PYTHONPATH.
        p=subprocess.Popen([sys.executable,'08_DEPLOYMENT/GENOS/start_sse.py'],cwd=C,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            until=time.monotonic()+15
            while True:
                assert p.poll() is None,(tmp_path/'server.log').read_text()
                try:status,body=request('/health');break
                except OSError:
                    if time.monotonic()>until:raise
                    time.sleep(.05)
            assert status==200 and json.loads(body)['data_readiness']=='NOT_CHECKED'
            status,body=request('/stream',{'API_TYPE':'SSE_CHECK'})
            assert status==200 and '"sse_ready":true' in body
            status,body=request('/json',{'API_TYPE':'PING'})
            value=json.loads(body)
            assert status==200 and value['status']==200,value
            assert not Path('/__startup_fixture_unmounted__').exists()
            (tmp_path/'http-result.json').write_text(json.dumps({'health':True,'SSE_CHECK':True,'JSON_PING':value,'Oracle_credentials_present':False,'model_credentials_present':False},ensure_ascii=False,indent=2)+'\n')
        finally:
            p.terminate()
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
    logs=(tmp_path/'server.log').read_text();assert '"workers": 1' in logs
