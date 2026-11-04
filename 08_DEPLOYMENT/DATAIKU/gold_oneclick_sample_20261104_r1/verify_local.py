"""Run the exact sent Python/TXT using real disposable Oracle and a minimal DSS substitute."""
from pathlib import Path
import argparse
import hashlib
import json
import secrets
import subprocess
import sys
import traceback
import types

HERE=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
    import oracledb
    import pandas as pd
    oracledb.defaults.fetch_lobs=False
    result={'status':'RUNNING','checks':[],'external_models':0,'dataiku_sdk':'LOCAL_SUBSTITUTE','cleaned':False}
    container=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
    assert container['Config']['Labels']['a8.task']=='legal-mapped-20261023'
    endpoint=container['HostConfig']['PortBindings']['1521/tcp'];assert len(endpoint)==1 and endpoint[0]['HostIp']=='127.0.0.1'
    dsn='127.0.0.1:'+endpoint[0]['HostPort']+'/FREEPDB1'
    password=dict(s.split('=',1) for s in container['Config']['Env'])['ORACLE_PASSWORD']
    owner='A8_ONE_'+secrets.token_hex(4).upper();secret=secrets.token_hex(24)
    admin=oracledb.connect(user='system',password=password,dsn=dsn);admin.call_timeout=15000
    conn=None;created=False;sql_calls=0;model_calls=0;lose_ack=True;storage_failure=False
    try:
        with admin.cursor() as c:
            c.execute('CREATE USER '+owner+' IDENTIFIED BY "'+secret+'" DEFAULT TABLESPACE USERS QUOTA 128M ON USERS');created=True
            c.execute('GRANT CREATE SESSION,CREATE TABLE TO '+owner)
        conn=oracledb.connect(user=owner,password=secret,dsn=dsn);conn.call_timeout=15000
        class Executor:
            def query_to_df(self,query,pre_queries=(),post_queries=(),**kw):
                nonlocal sql_calls,lose_ack
                with conn.cursor() as c:
                    for sql in pre_queries:c.execute(sql);sql_calls+=1
                    if lose_ack and any('INSERT INTO '+owner+'.TST_B003_LGL_DOC_VER' in s for s in pre_queries):
                        lose_ack=False
                        raise ConnectionError('INJECTED_ACK_LOST_AFTER_ORACLE_COMMIT')
                    c.execute(query);sql_calls+=1
                    frame=pd.DataFrame(c.fetchall(),columns=[d[0] for d in c.description])
                    for sql in post_queries:c.execute(sql)
                    return frame
        folder_root=out/'existing-upload-folder';folder_root.mkdir()
        name='DATAIKU_GOLD_ONECLICK_SAMPLE_20261104_R1.zip'
        (folder_root/name).write_bytes((HERE/name).read_bytes())
        (folder_root/'unrelated-existing-file.txt').write_text('preserve this')
        class Folder:
            def __init__(self,key,*a,**kw):assert key=='existingFolder'
            def list_paths_in_partition(self):return ['/'+p.relative_to(folder_root).as_posix() for p in folder_root.rglob('*') if p.is_file()]
            def get_download_stream(self,path):return (folder_root/path.lstrip('/')).open('rb')
            def upload_stream(self,path,stream):
                if storage_failure:raise OSError('synthetic S3 denied')
                p=folder_root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(stream.read())
        class Embedding:
            def __init__(self):self.texts=[]
            def add_text(self,text):self.texts.append(text)
            def execute(self):
                nonlocal model_calls
                model_calls+=1
                return types.SimpleNamespace(get_embeddings=lambda:[[1.,0.,0.,0.] for _ in self.texts])
        class Project:
            project_key='EXISTING_DEV_PROJECT'
            def get_llm(self,name):
                assert name=='SYNTHETIC_NO_EXTERNAL_MODEL'
                return types.SimpleNamespace(new_embeddings=lambda **kw:Embedding())
            def __getattr__(self,name):raise AssertionError('FLOW_OR_PROJECT_MUTATION_API_FORBIDDEN:'+name)
        project=Project()
        shim=types.ModuleType('dataiku');shim.Folder=Folder;shim.SQLExecutor2=lambda **kw:Executor()
        shim.api_client=lambda:types.SimpleNamespace(get_default_project=lambda:project,get_project=lambda key:project)
        sys.modules['dataiku']=shim
        text=(HERE/'DATAIKU_GOLD_ONECLICK_RUN_R1.txt').read_text()
        replacements={"'CODE_FOLDER_ID': ''":"'CODE_FOLDER_ID': 'existingFolder'",
            "'ORACLE_CONNECTION': 'AIDP'":"'ORACLE_CONNECTION': 'synthetic'",
            "'EXPECTED_DB_USER': 'PIDD2APP'":"'EXPECTED_DB_USER': "+repr(owner),
            "'GOLD_OWNER': ''":"'GOLD_OWNER': "+repr(owner),
            "'WORK_DIR': ''":"'WORK_DIR': "+repr(str(out/'work')),
            "'EMBED_MODEL': 'openai:genos-embedding:embedding-kure-v1'":"'EMBED_MODEL': 'SYNTHETIC_NO_EXTERNAL_MODEL'",
            "'EMBED_DIMENSIONS': 1024":"'EMBED_DIMENSIONS': 4"}
        for a,b in replacements.items():assert a in text;text=text.replace(a,b)
        def invoke():
            ns={};exec(compile(text,'<exact-delivered-oneclick>','exec'),ns);return ns
        storage_failure=True
        try:invoke()
        except RuntimeError as exc:assert 'STORAGE_CHECK_FAILED' in str(exc)
        else:raise AssertionError('storage failure accepted')
        assert sql_calls==0 and model_calls==0
        storage_failure=False
        result['checks'].append('storage_failure_before_any_oracle_or_model_call')
        try:invoke()
        except ConnectionError as exc:
            assert str(exc)=='INJECTED_ACK_LOST_AFTER_ORACLE_COMMIT'
            (out/'injected-ack-loss.txt').write_text(traceback.format_exc())
        else:raise AssertionError('source commit response-loss injection not reached')
        ns=invoke();assert ns['RESULT']['status']=='ONECLICK_GOLD_LOADED'
        expected={'DOC_VER':2,'DOC_UNIT':3,'DOC_BLK':3,'SRCH_ROW':112,'VCTR_ITEM':3}
        assert ns['RESULT']['counts']==expected
        result['checks'].append('exact_delivered_notebook_existing_project_one_folder_all_stages')
        result['checks'].append('committed_source_response_loss_resumed_without_duplicates')
        before=model_calls;invoke();assert model_calls==before==1
        result['checks'].append('same_cell_replay_without_additional_embedding')
        assert (folder_root/'unrelated-existing-file.txt').read_text()=='preserve this'
        assert (folder_root/name).read_bytes()==(HERE/name).read_bytes()
        assert sorted(p.name for p in (folder_root/'_gold_oneclick_sample_r1/input').iterdir())==[
            'ORIGINAL.sha256','PARTS.sha256','gold-dev-sample.zip.part000000','gold-dev-sample.zip.part000001']
        remote=folder_root/'_gold_oneclick_sample_r1/result'
        assert json.loads((remote/'latest.json').read_text())['status']=='SUCCESS'
        assert list((remote/'runs').rglob('log-*.txt'))
        result['checks'].append('existing_upload_bytes_preserved_scoped_parts_logs_and_receipts')
        # A missing local workspace cannot silently adopt a populated remote checkpoint.
        receipt=out/'work/workspace.json';backup=out/'workspace-backup.json';receipt.rename(backup)
        before=(sql_calls,model_calls)
        try:invoke()
        except ValueError as exc:assert 'CHECKPOINT_WORKSPACE_MISSING_OR_CHANGED' in str(exc)
        else:raise AssertionError('orphaned remote checkpoint accepted')
        assert before==(sql_calls,model_calls);backup.rename(receipt)
        result['checks'].append('missing_local_workspace_stops_before_oracle_and_embedding')
        # Inspect actual DB guards independently without mutating any table.
        ready=remote/'test-db-ready.json';saved=out/'db-ready-backup.json';ready.rename(saved)
        try:invoke()
        except ValueError as exc:assert 'TEST_TABLE_ALREADY_HAS_DATA' in str(exc)
        else:raise AssertionError('populated unknown test tables accepted')
        saved.rename(ready)
        result['checks'].append('populated_tables_without_ownership_receipt_rejected')
        credentials=out/'credentials.json';credentials.touch(mode=0o600)
        credentials.write_text(json.dumps({'dsn':dsn,'user':owner,'password':secret}))
        fresh=subprocess.run([sys.executable,str(HERE/'verify_serving.py'),str(out/'work'),str(credentials)],capture_output=True,text=True,timeout=90)
        credentials.unlink();(out/'serving.log').write_text(fresh.stdout+fresh.stderr)
        if fresh.returncode:raise AssertionError('Fresh connector check failed; see serving.log')
        result['checks'].append('fresh_process_source_vector_acl_and_profile_readback')
        result.update(status='PASS',counts=expected,synthetic_embedding_calls=model_calls,sql_calls=sql_calls,
                      code_sha256=hashlib.sha256((HERE/name).read_bytes()).hexdigest(),flow_api_calls=0)
    except BaseException as exc:
        result.update(status='FAILED',error_type=type(exc).__name__,error=str(exc))
        (out/'failure.txt').write_text(traceback.format_exc())
    finally:
        if conn is not None:conn.close()
        (out/'credentials.json').unlink(missing_ok=True)
        if created:
            with admin.cursor() as c:c.execute('DROP USER '+owner+' CASCADE')
        admin.close();result['cleaned']=True
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(result['checks']),'cleaned':result['cleaned']}))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
