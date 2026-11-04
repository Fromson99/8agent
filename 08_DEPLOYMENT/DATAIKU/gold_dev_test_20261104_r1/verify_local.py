"""Explicit CLI verification: synthetic ZIP, real disposable local Oracle schema.

Dataiku folders/SDK are substituted locally; SQL and JDBC block encoding execute
on Oracle. Embeddings are synthetic 4D, with no external inference call.
"""
from pathlib import Path
import argparse
import hashlib
import json
import secrets
import subprocess
import sys
import time
import traceback
import types

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PACKAGE = HERE/'package'
sys.dont_write_bytecode = True
sys.path[:0] = [str(PACKAGE),str(PACKAGE/'engine'),str(PACKAGE/'engine/vendor'),str(PACKAGE/'engine/vendor/02_BACKEND')]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upload', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve(); out.mkdir(parents=True, exist_ok=False)
    upload = Path(args.upload).resolve(strict=True)
    import oracledb
    import pandas as pd
    import dev_pipeline as flow
    import zip_config
    from gold_io import Contract, Stop
    import vector_stage
    oracledb.defaults.fetch_lobs = False
    result = {'status':'RUNNING','external_models':0,'dataiku_sdk':'LOCAL_SUBSTITUTE','checks':[], 'cleaned':False}
    container = json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
    assert container['Config']['Labels']['a8.task'] == 'legal-mapped-20261023'
    endpoint = container['HostConfig']['PortBindings']['1521/tcp']
    assert len(endpoint)==1 and endpoint[0]['HostIp']=='127.0.0.1'
    dsn = '127.0.0.1:'+endpoint[0]['HostPort']+'/FREEPDB1'
    password = dict(s.split('=',1) for s in container['Config']['Env'])['ORACLE_PASSWORD']
    owner = 'A8_ZIP_'+secrets.token_hex(4).upper()
    key = secrets.token_hex(24)
    admin = oracledb.connect(dsn=dsn,user='system',password=password); admin.call_timeout=15000
    conn = None; created=False; model_calls=0; sql_calls=0; lose_ack=False
    try:
        with admin.cursor() as c:
            c.execute('CREATE USER '+owner+' IDENTIFIED BY "'+key+'" DEFAULT TABLESPACE USERS QUOTA 128M ON USERS')
            created=True
            c.execute('GRANT CREATE SESSION,CREATE TABLE TO '+owner)
        conn = oracledb.connect(dsn=dsn,user=owner,password=key);conn.call_timeout=15000
        params = {'CODE_FOLDER_ID':'code','ORACLE_CONNECTION':'synthetic','EXPECTED_DB_USER':owner,
                  'TARGET_MODE':'GOLD','GOLD_OWNER':owner,'TABLE_PREFIX':'TST_B003_LGL_','DEVELOPMENT_ONLY':True,'TABLE_NAMES':{},
                  'EMBED_MODEL':'SYNTHETIC_NO_EXTERNAL_MODEL','EMBED_DIMENSIONS':4,
                  'EXPECTED_ARCHIVE':'gold-dev-sample.zip','EXPECTED_PARTS':2,'ACTIVATE_NEW_VECTOR_HEAD':True}
        cfg = {'project':'LEGAL_RAG_DEV_TEST','input_folder':'input','folders':{s[0]:s[0] for s in zip_config.STAGES},'params':params,'target':zip_config.target(params)}
        work=out/'work';work.mkdir();params['WORK_DIR']=str(work)
        (out/'contract.json').write_text(json.dumps(cfg['target']))
        contract=Contract(out/'contract.json')
        class Executor:
            def query_to_df(self,query,pre_queries=(),post_queries=(),**kwargs):
                nonlocal sql_calls,lose_ack
                with conn.cursor() as c:
                    for sql in pre_queries:c.execute(sql);sql_calls+=1
                    # Actual COMMIT succeeds, then the caller loses its response.
                    if pre_queries and lose_ack:
                        lose_ack=False
                        raise ConnectionError('SYNTHETIC_ACK_LOST_AFTER_ORACLE_COMMIT')
                    c.execute(query);sql_calls+=1
                    frame=pd.DataFrame(c.fetchall(),columns=[d[0] for d in c.description])
                    for sql in post_queries:c.execute(sql)
                    return frame
        remote=out/'managed-folders';remote.mkdir()
        class Folder:
            def __init__(self,key,*a,**kw):
                self.key=key; self.root=upload if key=='input' else remote/key
                self.root.mkdir(exist_ok=True)
            def list_paths_in_partition(self):
                return ['/'+p.relative_to(self.root).as_posix() for p in self.root.rglob('*') if p.is_file() and p.name!='manifest.json']
            def get_download_stream(self,name): return (self.root/name.lstrip('/')).open('rb')
            def upload_stream(self,name,stream):
                p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(stream.read())
        class Embedding:
            def __init__(self):self.texts=[]
            def add_text(self,text):self.texts.append(text)
            def execute(self):
                nonlocal model_calls
                model_calls+=1
                return types.SimpleNamespace(get_embeddings=lambda:[[1.,0.,0.,0.] for _ in self.texts])
        class Project:
            project_key="LEGAL_RAG_DEV_TEST"
            def get_llm(self,name):
                assert name==params['EMBED_MODEL']
                return types.SimpleNamespace(new_embeddings=lambda **kw:Embedding())
        shim=types.ModuleType('dataiku')
        shim.Folder=Folder
        shim.SQLExecutor2=lambda **kw:Executor()
        shim.api_client=lambda:types.SimpleNamespace(get_project=lambda key:Project(),get_default_project=lambda:Project())
        sys.modules['dataiku']=shim
        import zip_runtime
        def invoke(stage):
            zip_runtime.run(stage,cfg)
            value=json.loads((remote/stage/'latest.json').read_text())
            assert value['status']=='SUCCESS'
            return value['result']
        for stage,*_ in zip_config.STAGES:
            if stage=='source': lose_ack=True
            try:
                value=invoke(stage)
            except ConnectionError as exc:
                assert stage=='source' and str(exc)=='SYNTHETIC_ACK_LOST_AFTER_ORACLE_COMMIT'
                (out/'injected-ack-failure.txt').write_text(traceback.format_exc())
                value=invoke(stage)
                result['checks'].append('committed_source_batch_resumed_without_duplicate_insert')
            result[stage]=value
        result['checks'].append('two_parts_create_test_tables_restore_source_search_publish_vector_head_report')
        result['checks'].append('runtime_folder_status_logs_and_workspace_receipts')
        before=(model_calls,sql_calls)
        for stage,*_ in zip_config.STAGES:invoke(stage)
        assert model_calls==before[0]
        result['checks'].append('all_stages_replayed_without_new_embedding')
        # Catch the former hard-coded VARCHAR2(50) in vector JSON_TABLE.
        for did in ('x'*100,'한'*33):
            row={'VCTR_POST_ID':'width-only','VCTR_SEG_ID':hashlib.sha256(did.encode()).hexdigest(),
                 'DOC_ID':did,'SRC_UNIT_ID':'fixture-source','VCTR_META_CTNT':'{}','EMBD_VCTR_VALU':'[1,0,0,0]'}
            sql,binds=vector_stage.vector_sql(contract,[row],4)
            from jdbc_transport import render
            with conn.cursor() as c:c.execute(render(sql,binds,write=True))
        with conn.cursor() as c:
            c.execute('SELECT RGLT_DOC_ID,LENGTHB(RGLT_DOC_ID) FROM '+owner+".TST_B003_LGL_VCTR_ITEM WHERE VCTR_POST_ID='width-only'")
            assert sorted(n for _,n in c)==[99,100]
        try:
            vector_stage.vector_sql(contract,[dict(row,DOC_ID='한'*34)],4)
        except Stop:pass
        else:raise AssertionError('overlength vector document accepted')
        result['checks'].append('vector_document_id_100_byte_and_utf8_boundary')
        # A fresh process exercises the selected MAIN connector, never vendor modules.
        credentials=out/'credentials.json';credentials.touch(mode=0o600)
        credentials.write_text(json.dumps({'dsn':dsn,'user':owner,'password':key}))
        runner=HERE/'verify_serving.py'
        p=subprocess.run([sys.executable,str(runner),str(work),str(credentials)],capture_output=True,text=True,timeout=90)
        credentials.unlink()
        (out/'serving.log').write_text(p.stdout+p.stderr)
        if p.returncode:raise AssertionError('Fresh Gold connector failed; see serving.log')
        result['checks'].append('fresh_selected_main_source_vector_acl_and_profile')
        result.update(status='PASS',synthetic_embedding_calls=model_calls,sql_calls=sql_calls)
    except BaseException as exc:
        result.update(status='FAILED',error_type=type(exc).__name__,error=str(exc))
        (out/'failure.txt').write_text(traceback.format_exc())
    finally:
        if conn is not None:conn.close()
        (out/'credentials.json').unlink(missing_ok=True)
        if created:
            with admin.cursor() as c:c.execute('DROP USER '+owner+' CASCADE')
        admin.close(); result['cleaned']=True
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(result['checks']),'cleaned':result['cleaned'],'output':str(out)}))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
