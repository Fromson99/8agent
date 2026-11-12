"""R7 수신 파이프라인 끝까지 점검 — R6 점검을 그대로 쓰고 Gold 대상을 프로젝트 변수로 바꾼 부분을 더 본다.

GENOS 서버는 R6 그대로(GENOS_AGENT_ZIP_R6.zip), Dataiku 쪽만 R7. 전용 Oracle 컨테이너 a8-agent-zip-r7,
loopback HTTPS·DSS/ORDS SDK 대역, 임베딩은 고정 값. 외부 모델·현장 DB·배포 없음.
추가로 보는 것: 변수 없으면 설치 거절 / LGL_GOLD_OWNER로 적재 / 같은 Agent 결과를 LGL_GOLD_TABLE_PREFIX로
시험 복사본에 적재(원래 표 그대로) / 없는 소유자는 쓰기 전에 멈춤 / 전달한 DDL·확인 SQL 그대로 실행.
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
CONTAINER='a8-agent-zip-r7'
R6=HERE.parent/'agent_layer_zip_20261105_r6'
PARENT=HERE.parent/'agent_layer_return_20261105_r4'


def main(out):
    import oracledb
    import pandas as pd
    oracledb.defaults.fetch_lobs=False
    settings=json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0]
    assert settings['Config']['Labels']['a8.task']=='agent-zip-r7'
    port=settings['NetworkSettings']['Ports']['1521/tcp'][0]
    assert port['HostIp']=='127.0.0.1'
    dsn='127.0.0.1:'+port['HostPort']+'/FREEPDB1'
    pw=dict(v.split('=',1) for v in settings['Config']['Env'])['ORACLE_PASSWORD']
    admin=oracledb.connect(user='system',password=pw,dsn=dsn)
    out.mkdir(exist_ok=False,parents=True)
    server,flow=out/'server',out/'flow'
    for path,d in [(R6/'GENOS_AGENT_ZIP_R6.zip',server),(HERE/'DATAIKU_ZIP_AGENT_GOLD_FLOW_R7.zip',flow)]:
        with zipfile.ZipFile(path) as z:z.extractall(d)
    pin=hashlib.sha256((server/'CODE_PINS.json').read_bytes()).hexdigest()
    assert (flow/'SERVER_PIN.txt').read_text().strip()==pin
    testpin=pin
    sys.path[:0]=[str(server),str(flow),str(flow/'engine'),str(flow/'engine/vendor'),str(flow/'engine/vendor/02_BACKEND')]
    spec=importlib.util.spec_from_file_location('agent_api',server/'service.py')
    api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
    import agent_stage,agent_ords,flow_runtime as runtime,prod_pipeline,prod_config
    secret=secrets.token_hex(20)
    users=('SIDDA','SIDDS','STG_GOLD','PIDD2APP','STG_WRITER')
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
            c.execute('GRANT CREATE ANY TABLE, CREATE ANY INDEX, SELECT ANY TABLE, INSERT ANY TABLE TO PIDD2APP')
        fail_ack=[False]
        ords_calls=[]
        class ORDS:
            SQL_PATH='/_/sql'
            def __init__(self,**opts): pass
            def request(self,method,path,json):
                assert method=='POST' and path==self.SQL_PATH
                statement=json['statementText']
                binds={v['name']:v['value'] for v in json.get('binds',[])}
                assert all(v['data_type']!='VARCHAR2' or len(v['value'].encode())<=3000 for v in json.get('binds',[]))
                ords_calls.append({'write':'JSON_TABLE' in statement,'binds':len(binds)})
                with login('STG_WRITER') as db,db.cursor() as c:
                    c.execute(statement,binds)
                    if fail_ack[0] and 'JSON_TABLE' in statement:
                        fail_ack[0]=False
                        raise OSError('FIXTURE_ORDS_COMMIT_ACK_LOST')
                return {'items':[{'result':1}]}
        genos=types.ModuleType('genos'); genos.__path__=[]
        ords=types.ModuleType('genos.ords'); ords.ORDSClient=ORDS
        sys.modules.update({'genos':genos,'genos.ords':ords})
        os.environ.update(ORACLE_ORDS_SCHEMA='stage',ORACLE_ORDS_CLIENT_ID='fixture',
                          ORACLE_ORDS_CLIENT_SECRET='fixture',HF_HUB_OFFLINE='1')
        # Service API is called across a loopback HTTPS socket using the packaged wire transport.
        import ssl
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        cert,key=out/'cert.pem',out/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',str(key),'-out',str(cert),
                        '-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1'],check=True,capture_output=True)
        calls=[]
        upload_ack_lost=[True]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a): pass
            def do_POST(self):
                assert self.headers['Authorization']=='Bearer fixture'
                req=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append(req['API_TYPE'])
                response=asyncio.run(api.service({},req))
                if upload_ack_lost[0] and req['API_TYPE']=='PUT' and req['slot']=='raw':
                    assert response['code']==0
                    upload_ack_lost[0]=False
                    response={'code':1,'error':'FIXTURE_UPLOAD_ACK_LOST'}
                res=json.dumps(response).encode()
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
            def get_info(self,sensitive_info=False):return {'type':'Filesystem','path':str(self.path)}
            def list_paths_in_partition(self):return ['/'+p.relative_to(self.path).as_posix() for p in self.path.rglob('*') if p.is_file()]
            def get_download_stream(self,p):return (self.path/p.lstrip('/')).open('rb')
            def upload_stream(self,p,s):
                dest=self.path/p;dest.parent.mkdir(exist_ok=True,parents=True)
                with dest.open('wb') as f:shutil.copyfileobj(s,f)
        class Executor:
            def __init__(self,connection):
                assert connection=='AIDP';self.user='PIDD2APP'
            def query_to_df(self,query,pre_queries=(),post_queries=(),**kw):
                with login(self.user) as conn,conn.cursor() as c:
                    for item in pre_queries:c.execute(item)
                    c.execute(query)
                    frame=pd.DataFrame(c.fetchall(),columns=[d[0] for d in c.description])
                    for item in post_queries:c.execute(item)
                    assert not any('INSERT INTO SIDDA.LGL_PIPE_RESULT_A' in s and 'IF FALSE' not in s for s in pre_queries)
                    return frame
        class Embed:
            def __init__(self):self.texts=[]
            def add_text(self,t):self.texts.append(t)
            def execute(self):
                embed_calls.append(len(self.texts))
                return types.SimpleNamespace(get_embeddings=lambda:[[1.]+[0.]*1023 for _ in self.texts])
        project=types.SimpleNamespace(project_key='LOCAL_TEST',get_llm=lambda name:types.SimpleNamespace(new_embeddings=lambda **kw:Embed()))
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
        project.project_key='LOCAL_TEST'
        project.get_llm=lambda name:types.SimpleNamespace(new_embeddings=lambda **kw:Embed())
        dku=types.ModuleType('dataiku');dku.Folder=Folder;dku.SQLExecutor2=Executor;dku.get_custom_variables=lambda:variables
        dku.api_client=lambda:types.SimpleNamespace(get_default_project=lambda:project,get_project=lambda k:project)
        sys.modules['dataiku']=dku
        variables['AGENT_FLOW_WORK_DIR']=str(out/'work')
        shutil.copyfile(HERE/'DATAIKU_ZIP_AGENT_GOLD_FLOW_R7.zip',Folder('code').path/'DATAIKU_ZIP_AGENT_GOLD_FLOW_R7.zip')
        shutil.copyfile(PARENT/'LAW_SAMPLE_R2.zip',Folder('code').path/'LAW_SAMPLE_R2.zip')
        shutil.copyfile(PARENT/'SAMPLE_SUPPORT_R2.zip',Folder('code').path/'SAMPLE_SUPPORT_R2.zip')
        text=(HERE/'DATAIKU_SETUP_R7.txt').read_text().replace("'CODE_FOLDER_ID': ''","'CODE_FOLDER_ID': 'code'")
        try:
            exec(compile(text,'DATAIKU_SETUP_R7.txt','exec'),{})
        except ValueError as exc:assert str(exc).startswith('LGL_GOLD_OWNER_REQUIRED'),exc
        else:raise AssertionError('설치가 LGL_GOLD_OWNER 없이 진행됨')
        assert not recipes
        checks.append('R7_install_refused_without_LGL_GOLD_OWNER')
        variables['LGL_GOLD_OWNER']='STG_GOLD'
        for _ in range(2):
            ns={};exec(compile(text,'DATAIKU_SETUP_R7.txt','exec'),ns)
        assert len(recipes)==3 and len(scenarios)==1 and len(by_id)==5
        assert sorted(recipes)==['LGL_AGENT_R7_PROD_01_SUBMIT','LGL_AGENT_R7_PROD_02_WAIT_AGENT','LGL_AGENT_R7_PROD_03_LOAD']
        installed=ns['cfg']
        assert installed['ENVIRONMENT']=='PROD' and installed['INPUT_MODE']=='ZIP' and 'GOLD_OWNER' not in installed
        assert not any('STG_GOLD' in r.code or 'GOLD_OWNER' in r.code.split('from flow_runtime import run')[1] for r in recipes.values())
        checks.append('R7_recipes_contain_no_gold_owner')
        assert installed['INPUT_FOLDER_ID']==installed['SUPPORT_FOLDER_ID']==installed['CODE_FOLDER_ID']=='code'
        cfg=installed
        folders=cfg['folders']
        for recipe in recipes.values():compile(recipe.code,recipe.name,'exec')
        assert not next(iter(scenarios.values())).active
        checks+=['exact_R7_notebook_installs_data_ZIP_to_Gold_flow',
                 'repeat_install_three_recipes_one_disabled_scenario']
        with admin.cursor() as c:
            c.execute('GRANT SELECT, INSERT ON SIDDA.LGL_PIPE_RESULT_A TO STG_WRITER')
        from stage_wire import Wire
        alias=runtime.wire({'LEGAL_PIPELINE_URL':variables['AGENT_PIPELINE_URL'],'LEGAL_PIPELINE_TOKEN':'fixture'})
        assert alias.url==runtime.wire(variables).url
        try:runtime.wire({'AGENT_PIPELINE_URL':variables['AGENT_PIPELINE_URL'],'LEGAL_PIPELINE_TOKEN':'fixture'})
        except ValueError:pass
        else:raise AssertionError('mixed credential pair accepted')
        assert api.handle({'API_TYPE':'HEALTH'})['agent_layer']['configured'] is True
        checks+=['existing_LEGAL_PIPELINE_variable_pair_supported','incomplete_credential_pair_rejected','GENOS_health_ORDS_Agent_configuration']
        def delivered(name,old):
            text=(HERE/name).read_text()
            return [blk.split('\n',1)[1].strip().replace(old+'.','STG_GOLD.') for blk in text.split('-- [')[1:]]
        with admin.cursor() as c:
            for name,old in (('CREATE_GOLD_TABLES_SIDDG_R1.txt','SIDDG'),('CREATE_TEST_COPY_SIDDS_R1.txt','SIDDS')):
                for stmt in delivered(name,old):
                    c.execute(stmt)
            for prefix in ('IDD_B003_LGL_','TST_B003_LGL_'):
                for k in prod_config.target({'TARGET_MODE':'GOLD','GOLD_OWNER':'STG_GOLD','TABLE_PREFIX':prefix})['tables'].values():
                    c.execute('GRANT SELECT, INSERT ON STG_GOLD.'+k['name']+' TO PIDD2APP')
        checks.append('delivered_CREATE_GOLD_and_TEST_COPY_DDL_executed')
        def table_rows(prefix):
            with admin.cursor() as c:
                return {k:c.execute('SELECT COUNT(*) FROM STG_GOLD.'+prefix+k).fetchone()[0]
                        for k in ('DOC_VER','DOC_UNIT','DOC_BLK','SRC_POST','SRCH_POST','SRCH_ROW','SRCH_CHNL','VCTR_POST','VCTR_ITEM')}
        fail_ack[0]=True
        try:runtime.run('submit',cfg)
        except RuntimeError as exc:
            reply=json.dumps({'code':1,'error':'FIXTURE_UPLOAD_ACK_LOST'}).encode()
            assert str(exc)=='GENOS_REPLY_'+hashlib.sha256(reply).hexdigest()[:16]
        else:raise AssertionError('raw ZIP upload acknowledgement loss was not injected')
        assert calls.count('RUN')==0 and calls.count('PUT')==1
        intent=runtime.run('submit',cfg)
        assert calls.count('RUN')==1
        runtime.run('submit',cfg)
        assert calls.count('RUN')==1 and calls.count('PUT')==2
        try:runtime.run('wait',cfg)
        except ValueError as exc:assert str(exc)=='AGENT_STAGE_PENDING_EXPLICIT_RESUME_REQUIRED'
        except BaseException:
            h=api.HANDLES[intent['job']]
            shutil.copyfile(h['folder']/'compute.log',out/'worker.log')
            raise
        else:raise AssertionError('ACK loss did not interrupt ORDS publish')
        query=runtime.layer_query('AIDP')
        assert not agent_stage.ready(query,intent['job'],intent['binding'])
        assert query('SELECT COUNT(*) AS N FROM SIDDA.LGL_PIPE_RESULT_A')[0]['N']>0
        h=api.HANDLES[intent['job']]
        shutil.copyfile(h['folder']/'compute.log',out/'worker.log')
        source=next((h['folder']/'workspace/01_DATA/RAW/external/sample_team/law').rglob('*.xml'))
        expected=json.loads((PARENT/'RELEASE.json').read_text())['sample']
        assert hashlib.sha256(source.read_bytes()).hexdigest()==expected['document_sha256']
        assert (h['folder']/'raw.zip').read_bytes()==(PARENT/'LAW_SAMPLE_R2.zip').read_bytes()
        assert 'READ' not in calls and calls.count('RUN')==1 and 'PUBLISH' not in calls
        # Explicitly resume saved bytes after an ambiguous ORDS acknowledgement.
        ready=runtime.run('resume',cfg)
        assert calls.count('RUN')==1 and calls.count('PUBLISH')==1
        http.shutdown();http.server_close()
        calls_before=list(calls)
        ready=runtime.run('wait',cfg)
        assert runtime.run('wait',cfg)==ready and calls==calls_before
        receipt=agent_stage.ready(query,intent['job'],intent['binding'])
        assert receipt and receipt['sha256']==h['result']['sha256']
        checks+=['Dataiku_existing_ZIP_upload_ACK_loss_resumes_received_offset',
                 'exact_public_law_ZIP_async_compute_and_ORDS_Agent_batch',
                 'duplicate_submit_one_RUN','local_ZIP_byte_identical_and_original_XML_hash',
                 'ORDS_commit_ACK_loss_no_READY_no_automatic_retransmit',
                 'explicit_PUBLISH_same_saved_result_without_recompute_or_HTTP_READ',
                 'SIDDA_READY_readback_and_repeat_wait']
        sys.path.insert(0,str(R6))
        from verify_stage import check_stage
        checks.extend(check_stage(agent_ords,agent_stage,ORDS(),query,out,login))
        # The real DSS load recipe and GENOS are separate interpreters. Release the
        # completed server's package cache before importing the DSS vendor modules.
        for name in list(sys.modules):
            if name.split('.')[0] in {'semantic_runtime','lawrag'}:
                del sys.modules[name]
        sys.path[:0]=[str(flow/'engine/vendor/02_BACKEND')]
        diagnostics['service_operations']=calls
        cfg['folders']=dict(folders,load='load-prod')
        assert table_rows('IDD_B003_LGL_')['DOC_VER']==0
        result=runtime.run('load',cfg)
        n=len(embed_calls)
        assert runtime.run('load',cfg)==result and len(embed_calls)==n
        assert result['checks'] and result['coverage']['selected_count']==1 and result['counts']['VCTR_ITEM']>0
        assert result['status']=='GOLD_LOADED' and result['gold_owner']=='STG_GOLD' and result['table_prefix']=='IDD_B003_LGL_'
        gold_rows=table_rows('IDD_B003_LGL_')
        assert gold_rows['DOC_VER']==result['counts']['DOC_VER'] and gold_rows['SRCH_ROW']==result['counts']['SRCH_ROW']
        assert not any(table_rows('TST_B003_LGL_').values())
        diagnostics['GOLD']=result
        checks.append('GOLD_owner_from_project_variable_counts_publications_duplicate_resume_without_GENOS')
        # 같은 Agent 결과를 시험 복사본에: 변수만 바꾸고 재설치·GENOS 없이
        variables['LGL_GOLD_TABLE_PREFIX']='TST_B003_LGL_'
        copy=runtime.run('load',cfg)
        assert copy['table_prefix']=='TST_B003_LGL_' and copy['counts']==result['counts'] and copy['checks']
        assert copy['query_release_id']==result['query_release_id']
        assert table_rows('TST_B003_LGL_')==gold_rows and table_rows('IDD_B003_LGL_')==gold_rows
        assert runtime.run('load',cfg)==copy
        saved_names=sorted(p.name for p in (out/'folders'/'load-prod'/'trial-001').iterdir())
        assert saved_names==['report-tst_b003_lgl.json','report.json'],saved_names
        diagnostics['TEST_COPY']={'counts':copy['counts'],'rows':table_rows('TST_B003_LGL_')}
        checks.append('same_agent_result_loaded_to_TST_copy_by_variable_original_unchanged')
        # 없는 소유자: 쓰기 전에 멈춤
        variables['LGL_GOLD_OWNER']='NO_SUCH_OWNER'; variables.pop('LGL_GOLD_TABLE_PREFIX')
        before=(table_rows('IDD_B003_LGL_'),table_rows('TST_B003_LGL_'))
        try:runtime.run('load',cfg)
        except Exception as exc:
            assert 'TRIAL_TARGET_CHANGED' in str(exc),exc
        else:raise AssertionError('다른 소유자로 같은 trial 적재가 진행됨')
        assert (table_rows('IDD_B003_LGL_'),table_rows('TST_B003_LGL_'))==before
        checks.append('owner_change_on_same_trial_stops_before_any_write')
        variables['LGL_GOLD_OWNER']='STG_GOLD'
        # 전달한 확인 SQL(Q03~Q05)을 이 DB에서 그대로: Gold 13·중간표는 차이 0, 남는 것은 이 시험 DB에 만들지 않은 서빙 기록 4표뿐
        check_text=(HERE/'CHECK_TABLES_SIDDS_R1.txt').read_text().replace("'SIDDS'","'STG_GOLD'").replace('SIDDS.','STG_GOLD.')
        blocks={blk.split(']',1)[0]:blk.split('\n',1)[1].strip() for blk in check_text.split('-- [')[1:]}
        with login('PIDD2APP') as conn,conn.cursor() as c:
            diff={}
            for q in ('Q03','Q04','Q05'):
                c.execute(blocks[q]);diff[q]=[tuple(r[:3]) for r in c.fetchall()]
            c.execute(blocks['Q02']);present=[tuple(r[:2]) for r in c.fetchall()]
        assert diff['Q05']==[]
        assert all(r[0]=='SIDDA' and r[1].startswith(('LGL_AGT_','LGL_EXEC_ST')) for r in diff['Q03']+diff['Q04']),diff
        assert len([r for r in present if r[0]=='STG_GOLD'])==13 and ('SIDDA','LGL_PIPE_RESULT_A') in present
        diagnostics['delivered_check_sql']={k:len(v) for k,v in diff.items()}
        checks.append('delivered_CHECK_SQL_gold13_and_stage_table_zero_diff')
        query=runtime.layer_query('AIDP')
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
        doc=Folder('code').path/'LAW_SAMPLE_R2.zip'
        with doc.open('ab') as f:f.write(b'changed')
        cfg.update(ENVIRONMENT='PROD',INPUT_MODE='ZIP',folders=folders)
        try:runtime.run('submit',cfg)
        except ValueError as err:assert 'DATA_ZIP_HASH_OR_SIZE' in str(err)
        else:raise AssertionError('same trial accepted different input')
        checks.append('changed_Dataiku_ZIP_rejected_before_new_GENOS_request')
        result={'status':'PASS','checks':checks,'diagnostics':diagnostics,'native_python_and_recipe_sources_same':True,
                'release_pin':pin,'fixture_pin':testpin,'fixture_glossary_policy_rebound':False,'GENOS_Oracle_access':True,'ORDS_environment':True,
                'oracle':admin.version,'field_execution':False,'dataiku_sdk':'local API fixture','ords_sdk':'request adapter executing real Oracle SQL','embedding':'local deterministic substitute'}
        diagnostics['ords_requests']=ords_calls
        diagnostics['installed_recipe_names']=sorted(recipes)
        diagnostics['oracle_connections']=['AIDP']
        diagnostics['GENOS_env_has_ORDS']=any(k.startswith('ORACLE_ORDS_') for k in os.environ)
        (out/'validation.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    finally:
        http.shutdown();http.server_close()
        with admin.cursor() as c:
            for user in reversed(added):c.execute('DROP USER '+user+' CASCADE')
        admin.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path)
    main(p.parse_args().output.resolve())
