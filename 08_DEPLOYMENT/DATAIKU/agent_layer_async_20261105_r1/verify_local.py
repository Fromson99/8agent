"""Local native document -> async service -> real Oracle -> DEV/PROD recipe checks.

Requires a dedicated disposable Oracle Free container labeled a8.task=agent-flow-1379.
Only the fixture glossary policy, its resulting pins, DSS/ORDS SDKs and embeddings
are substituted. The worker subprocess, SQL, target schemas and archive checks run.
"""
from pathlib import Path
import argparse
import asyncio
import hashlib
import importlib.util
import io
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import types
import zipfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
FIX=REPO/'09_ARTIFACTS/TEMP/single-cpu-r10-native/test_actual_native_flow_withou1'
CONTAINER='a8-agent-1379-oracle'


def main(out):
    import oracledb
    import pandas as pd
    oracledb.defaults.fetch_lobs=False
    settings=json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]
    assert settings['Config']['Labels']['a8.task']=='agent-flow-1379'
    port=settings['NetworkSettings']['Ports']['1521/tcp'][0]
    assert port['HostIp']=='127.0.0.1'
    dsn='127.0.0.1:'+port['HostPort']+'/FREEPDB1'
    pw=dict(v.split('=',1) for v in settings['Config']['Env'])['ORACLE_PASSWORD']
    admin=oracledb.connect(user='system',password=pw,dsn=dsn)
    out.mkdir(exist_ok=False,parents=True)
    server,flow=out/'server',out/'flow'
    for name,d in [('GENOS_AGENT_ASYNC_R1.zip',server),('DATAIKU_AGENT_FLOW_R1.zip',flow)]:
        with zipfile.ZipFile(HERE/name) as z:z.extractall(d)
    pin=hashlib.sha256((server/'CODE_PINS.json').read_bytes()).hexdigest()
    assert (flow/'SERVER_PIN.txt').read_text().strip()==pin
    # Use the same small locally generated support binding used by the parent R10 tests.
    policy='00_SYSTEM/GLOSSARY_PIPELINE.json'
    shutil.copyfile(FIX/'dev'/policy,server/policy)
    pins=json.loads((server/'CODE_PINS.json').read_bytes())
    pins['files'][policy]=hashlib.sha256((server/policy).read_bytes()).hexdigest()
    (server/'CODE_PINS.json').write_text(json.dumps(pins,sort_keys=True,indent=2)+'\n')
    testpin=hashlib.sha256((server/'CODE_PINS.json').read_bytes()).hexdigest()
    (flow/'SERVER_PIN.txt').write_text(testpin+'\n')
    manifest=json.loads((flow/'FLOW_MANIFEST.json').read_bytes())
    manifest['files']['SERVER_PIN.txt']=hashlib.sha256((flow/'SERVER_PIN.txt').read_bytes()).hexdigest()
    (flow/'FLOW_MANIFEST.json').write_text(json.dumps(manifest))
    sys.path[:0]=[str(server),str(flow),str(flow/'engine'),str(flow/'engine/vendor'),str(flow/'engine/vendor/02_BACKEND')]
    spec=importlib.util.spec_from_file_location('agent_api',server/'service.py')
    api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
    import agent_stage,flow_runtime as runtime,prod_pipeline,prod_config
    secret=secrets.token_hex(20)
    users=('SIDDA','SIDDS','STG_GOLD','STG_READER','STG_WRITER','STG_TARGET')
    added=[]
    checks=[]
    diagnostics={}
    embed_calls=[]
    def login(user):
        return oracledb.connect(user=user,password=secret,dsn=dsn)
    try:
        with admin.cursor() as c:
            for user in users:
                c.execute(f'CREATE USER {user} IDENTIFIED BY "{secret}" DEFAULT TABLESPACE USERS QUOTA 512M ON USERS')
                added.append(user)
                c.execute('GRANT CREATE SESSION TO '+user)
            ddl=(HERE/'AGENT_STAGE.sql').read_text().split('CREATE TABLE',1)[1].split(';',1)[0]
            c.execute('CREATE TABLE'+ddl)
            c.execute('GRANT SELECT, INSERT ON SIDDA.LGL_PIPE_RESULT_A TO STG_WRITER')
            c.execute('GRANT SELECT ON SIDDA.LGL_PIPE_RESULT_A TO STG_READER')
        class ORDS:
            SQL_PATH='/_/sql'
            def __init__(self,**opts): pass
            def request(self,method,path,json):
                assert method=='POST' and path==self.SQL_PATH
                binds={v['name']:v['value'] for v in json.get('binds',[])}
                with login('STG_WRITER') as db,db.cursor() as c:
                    c.execute(json['statementText'],binds)
                    if c.description:
                        items=[dict(zip([d[0] for d in c.description],row)) for row in c.fetchall()]
                        return {'items':[{'resultSet':{'items':items,'hasMore':False,'offset':0}}]}
                    return {'items':[{'result':1}]}
        genos=types.ModuleType('genos'); genos.__path__=[]
        ords=types.ModuleType('genos.ords'); ords.ORDSClient=ORDS
        sys.modules.update({'genos':genos,'genos.ords':ords})
        os.environ.update(ORACLE_ORDS_SCHEMA='stage',ORACLE_ORDS_CLIENT_ID='fixture',ORACLE_ORDS_CLIENT_SECRET='fixture',HF_HUB_OFFLINE='1')
        # Service API is called across a loopback HTTPS socket using the packaged wire transport.
        import ssl
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        cert,key=out/'cert.pem',out/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',str(key),'-out',str(cert),
                        '-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1'],check=True,capture_output=True)
        calls=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a): pass
            def do_POST(self):
                assert self.headers['Authorization']=='Bearer fixture'
                req=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append(req['API_TYPE'])
                res=json.dumps(asyncio.run(api.service({},req))).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(res)));self.end_headers();self.wfile.write(res)
        http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(cert,key)
        http.socket=ctx.wrap_socket(http.socket,server_side=True)
        threading.Thread(target=http.serve_forever,daemon=True).start()
        os.environ['SSL_CERT_FILE']=str(cert)
        variables={'AGENT_PIPELINE_URL':'https://127.0.0.1:'+str(http.server_port),'AGENT_PIPELINE_TOKEN':'fixture'}
        class Folder:
            def __init__(self,k,*a,**kw):
                self.path=out/'folders'/k
                self.path.mkdir(parents=True,exist_ok=True)
            def list_paths_in_partition(self):return ['/'+p.relative_to(self.path).as_posix() for p in self.path.rglob('*') if p.is_file()]
            def get_download_stream(self,p):return (self.path/p.lstrip('/')).open('rb')
            def upload_stream(self,p,s):
                dest=self.path/p;dest.parent.mkdir(exist_ok=True,parents=True)
                with dest.open('wb') as f:shutil.copyfileobj(s,f)
        class Executor:
            def __init__(self,connection):
                self.user={'agent':'STG_READER','target':'STG_TARGET'}[connection]
            def query_to_df(self,query,pre_queries=(),post_queries=(),**kw):
                with login(self.user) as conn,conn.cursor() as c:
                    for item in pre_queries:c.execute(item)
                    c.execute(query)
                    frame=pd.DataFrame(c.fetchall(),columns=[d[0] for d in c.description])
                    for item in post_queries:c.execute(item)
                    return frame
        class Embed:
            def __init__(self):self.texts=[]
            def add_text(self,t):self.texts.append(t)
            def execute(self):
                embed_calls.append(len(self.texts))
                return types.SimpleNamespace(get_embeddings=lambda:[[1.,0.,0.,0.] for _ in self.texts])
        project=types.SimpleNamespace(project_key='LOCAL_TEST',get_llm=lambda name:types.SimpleNamespace(new_embeddings=lambda **kw:Embed()))
        dku=types.ModuleType('dataiku');dku.Folder=Folder;dku.SQLExecutor2=Executor;dku.get_custom_variables=lambda:variables
        dku.api_client=lambda:types.SimpleNamespace(get_default_project=lambda:project,get_project=lambda k:project)
        sys.modules['dataiku']=dku
        for p in (FIX/'dev/01_DATA/RAW/internal/test_team').iterdir():shutil.copyfile(p,Folder('docs').path/p.name)
        os.environ['AGENT_PIPELINE_SUPPORT_ZIP']=str(FIX/'export/PIPELINE_SUPPORT.zip')
        os.environ['AGENT_PIPELINE_SUPPORT_SHA256']=hashlib.sha256((FIX/'export/PIPELINE_SUPPORT.zip').read_bytes()).hexdigest()
        for name in ('PIPELINE_SUPPORT.zip','PIPELINE_SUPPORT.zip.receipt.json'):
            shutil.copyfile(FIX/'export'/name,Folder('support').path/name)
        folders={k:k for k in ('submit','wait','load')}
        cfg=dict(project='LOCAL_TEST',folders=folders,CODE_FOLDER_ID='code',INPUT_FOLDER_ID='docs',SUPPORT_FOLDER_ID='',
                 DOCUMENT_PREFIX='internal/test_team',WORK_DIR=str(out/'work'),TARGET_CONNECTION='target',AGENT_CONNECTION='agent',
                 GOLD_OWNER='STG_GOLD',EXPECTED_DB_USER='STG_TARGET',ENVIRONMENT='DEV',EMBED_MODEL='fixture',EMBED_DIMENSIONS=4)
        for mode in ('DEV_1','GOLD'):
            definition=prod_config.target({'TARGET_MODE':mode,'GOLD_OWNER':'STG_GOLD'})
            path=out/(mode+'.json');path.write_text(json.dumps(definition))
            contract=prod_pipeline.Contract(path)
            with admin.cursor() as c:
                for k in contract.tables:
                    c.execute(contract.ddl(k))
                    for stmt in contract.indexes(k):c.execute(stmt)
                    c.execute('GRANT SELECT, INSERT ON '+contract.table(k)+' TO STG_TARGET')
        intent=runtime.run('submit',cfg)
        assert calls.count('RUN')==1
        runtime.run('submit',cfg)
        assert calls.count('RUN')==1 and calls.count('PUT')==1
        try:runtime.run('wait',cfg)
        except BaseException:
            h=api.HANDLES[intent['job']]
            shutil.copyfile(h['folder']/'compute.log',out/'worker.log')
            raise
        h=api.HANDLES[intent['job']]
        shutil.copyfile(h['folder']/'compute.log',out/'worker.log')
        checks+=['native_DOCX_async_SUBMIT','duplicate_submit_one_RUN','GENOS_to_SIDDA_READY']
        assert 'READ' not in calls
        http.shutdown();http.server_close()
        # The real DSS load recipe and GENOS are separate interpreters. Release the
        # completed server's package cache before importing the DSS vendor modules.
        for name in list(sys.modules):
            if name.split('.')[0] in {'semantic_runtime','lawrag'}:
                del sys.modules[name]
        sys.path[:0]=[str(flow/'engine/vendor/02_BACKEND')]
        diagnostics['service_operations']=calls
        for mode in ('DEV','PROD'):
            cfg['ENVIRONMENT']=mode
            if mode=='PROD':
                # Same test database and receipt, distinct DSS project/flow output namespaces in deployment.
                cfg['folders']=dict(folders,load='load-prod')
            result=runtime.run('load',cfg)
            n=len(embed_calls)
            assert runtime.run('load',cfg)==result and len(embed_calls)==n
            assert result['checks'] and result['coverage']['selected_count']==1 and result['counts']['VCTR_ITEM']>0
            diagnostics[mode]=result
            checks.append(mode+'_counts_publications_duplicate_resume_without_GENOS')
        query=runtime.layer_query('agent')
        j,b=intent['job'],intent['binding']
        receipt=agent_stage.ready(query,j,b)
        assert agent_stage.ready(query,j,'0'*64) is None
        # Simulate corruption, then an incomplete header in the dedicated test database.
        with admin.cursor() as c:
            c.execute("UPDATE SIDDA.LGL_PIPE_RESULT_A SET DATA_HASH=:h WHERE JOB_ID=:j AND SEQ_NO=1",h='0'*64,j=j)
            admin.commit()
        try:agent_stage.restore(query,j,b,receipt,out/'bad.zip')
        except ValueError as err:assert 'STAGE_PART_HASH' in str(err)
        else:raise AssertionError('corruption accepted')
        with admin.cursor() as c:
            c.execute('DELETE FROM SIDDA.LGL_PIPE_RESULT_A WHERE JOB_ID=:j AND SEQ_NO=0',j=j);admin.commit()
        assert not agent_stage.ready(query,j,b)
        checks+=['changed_binding_rejected','corrupt_chunk_rejected','partial_job_invisible']
        doc=next(Folder('docs').path.glob('*.docx'))
        with doc.open('ab') as f:f.write(b'changed')
        cfg.update(ENVIRONMENT='DEV',folders=folders)
        try:runtime.run('submit',cfg)
        except ValueError as err:assert 'DOCUMENTS_CHANGED_USE_NEW_TRIAL' in str(err)
        else:raise AssertionError('same trial accepted different input')
        checks.append('same_trial_rejects_changed_loose_document')
        result={'status':'PASS','checks':checks,'diagnostics':diagnostics,'native_python_and_recipe_sources_same':True,
                'release_pin':pin,'fixture_pin':testpin,'fixture_glossary_policy_rebound':True,
                'oracle':admin.version,'field_execution':False,'dataiku_ords_sdks':'local substitutes','embedding':'local deterministic substitute'}
        (out/'validation.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    finally:
        with admin.cursor() as c:
            for user in reversed(added):c.execute('DROP USER '+user+' CASCADE')
        admin.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path)
    main(p.parse_args().output.resolve())
