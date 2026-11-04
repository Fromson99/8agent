"""Exact delivered TXT, 34 synthetic parts, real Oracle with separate owner/login.

All schemas are disposable; DSS SDK and embedding are local substitutes.
The loader's SQL path rejects DDL. Only this fixture prepares/drops its own tables.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import secrets
import subprocess
import sys
import traceback
import types

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
    import oracledb
    import pandas as pd
    oracledb.defaults.fetch_lobs=False
    result={'status':'RUNNING','checks':[],'external_models':0,'dataiku_sdk':'LOCAL_SUBSTITUTE',
            'field_execution':False,'full_production_corpus':False,'cleaned':False}
    container=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
    assert container['Config']['Labels']['a8.task']=='legal-mapped-20261023'
    endpoint=container['HostConfig']['PortBindings']['1521/tcp'];assert len(endpoint)==1 and endpoint[0]['HostIp']=='127.0.0.1'
    dsn='127.0.0.1:'+endpoint[0]['HostPort']+'/FREEPDB1'
    password=dict(s.split('=',1) for s in container['Config']['Env'])['ORACLE_PASSWORD']
    suffix=secrets.token_hex(4).upper();owner='A8_PO_'+suffix;login='A8_PL_'+suffix;secret=secrets.token_hex(24)
    admin=oracledb.connect(user='system',password=password,dsn=dsn);admin.call_timeout=15000
    conn=None;created=[];sql_calls=0;writes=0;model_calls=0;lose_ack=True;storage_failure=False;final_failure=False
    try:
        with admin.cursor() as c:
            for user in (owner,login):
                c.execute('CREATE USER '+user+' IDENTIFIED BY "'+secret+'" DEFAULT TABLESPACE USERS QUOTA 128M ON USERS')
                created.append(user);c.execute('GRANT CREATE SESSION TO '+user)
        conn=oracledb.connect(user=login,password=secret,dsn=dsn);conn.call_timeout=15000
        class Executor:
            def query_to_df(self,query,pre_queries=(),post_queries=(),**kw):
                nonlocal sql_calls,writes,lose_ack
                with conn.cursor() as c:
                    for sql in pre_queries:
                        assert not re.search(r'\b(CREATE|ALTER|DROP|TRUNCATE|DELETE|UPDATE)\b',sql,re.I),sql[:100]
                        c.execute(sql);sql_calls+=1
                        if 'INSERT INTO' in sql and 'IF FALSE' not in sql:writes+=1
                    if lose_ack and any('INSERT INTO '+owner+'.IDD_B003_LGL_DOC_VER' in s and 'IF FALSE' not in s for s in pre_queries):
                        lose_ack=False
                        raise ConnectionError('INJECTED_ACK_LOST_AFTER_ORACLE_COMMIT')
                    c.execute(query);sql_calls+=1
                    frame=pd.DataFrame(c.fetchall(),columns=[d[0] for d in c.description])
                    for sql in post_queries:c.execute(sql)
                    return frame
        folder_root=out/'existing-upload-folder';folder_root.mkdir()
        name='DATAIKU_GOLD_ONECLICK_PROD_20261104_R2.zip'
        (folder_root/name).write_bytes((HERE/name).read_bytes())
        (folder_root/'unrelated-existing-file.txt').write_text('preserve this')
        fixture=REPO/'09_ARTIFACTS/AUDITS/20261104-gold-r5-code-integration/fixture/upload'
        archive='genos-rag-data-20261007T002029Z-7c0b050f.zip'
        for p in fixture.iterdir():
            if '.part' in p.name:(folder_root/p.name.replace('synthetic-gold.zip',archive)).write_bytes(p.read_bytes())
            elif p.suffix=='.sha256':(folder_root/p.name).write_text(p.read_text().replace('synthetic-gold.zip',archive))
        original_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder_root.iterdir()}
        class Folder:
            def __init__(self,key,*a,**kw):assert key=='existingFolder'
            def list_paths_in_partition(self):return ['/'+p.relative_to(folder_root).as_posix() for p in folder_root.rglob('*') if p.is_file()]
            def get_download_stream(self,path):return (folder_root/path.lstrip('/')).open('rb')
            def upload_stream(self,path,stream):
                if storage_failure:raise OSError('synthetic S3 denied')
                if final_failure and path.endswith('/report.json'):raise OSError('INJECTED_FINAL_UPLOAD_FAILURE')
                assert path.startswith('_gold_oneclick_prod_r1/')
                p=folder_root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(stream.read())
        class Embedding:
            def __init__(self):self.texts=[]
            def add_text(self,text):self.texts.append(text)
            def execute(self):
                nonlocal model_calls
                model_calls+=1
                return types.SimpleNamespace(get_embeddings=lambda:[[1.,0.,0.,0.] for _ in self.texts])
        class Project:
            project_key='EXISTING_PRODUCTION_PROJECT'
            def get_llm(self,name):
                assert name=='SYNTHETIC_NO_EXTERNAL_MODEL'
                return types.SimpleNamespace(new_embeddings=lambda **kw:Embedding())
            def __getattr__(self,name):raise AssertionError('FLOW_OR_PROJECT_MUTATION_API_FORBIDDEN:'+name)
        project=Project()
        shim=types.ModuleType('dataiku');shim.Folder=Folder;shim.SQLExecutor2=lambda **kw:Executor()
        shim.api_client=lambda:types.SimpleNamespace(get_default_project=lambda:project,get_project=lambda key:project)
        sys.modules['dataiku']=shim
        text=(HERE/'DATAIKU_GOLD_PROD_RUN_R2.txt').read_text()
        replacements={"'CODE_FOLDER_ID': ''":"'CODE_FOLDER_ID': 'existingFolder'",
            "'ORACLE_CONNECTION': 'AIDP'":"'ORACLE_CONNECTION': 'synthetic'",
            "'EXPECTED_DB_USER': 'PIDD2APP'":"'EXPECTED_DB_USER': "+repr(login),
            "'GOLD_OWNER': 'SIDDS'":"'GOLD_OWNER': "+repr(owner),
            "'WORK_DIR': ''":"'WORK_DIR': "+repr(str(out/'work-base')),
            "'EMBED_MODEL': 'openai:genos-embedding:embedding-kure-v1'":"'EMBED_MODEL': 'SYNTHETIC_NO_EXTERNAL_MODEL'",
            "'EMBED_DIMENSIONS': 1024":"'EMBED_DIMENSIONS': 4"}
        for a,b in replacements.items():assert a in text;text=text.replace(a,b)
        def invoke():
            ns={};exec(compile(text,'<exact-delivered-production>','exec'),ns);return ns
        storage_failure=True
        try:invoke()
        except RuntimeError as exc:assert 'STORAGE_CHECK_FAILED' in str(exc)
        else:raise AssertionError('storage failure accepted')
        assert sql_calls==0 and model_calls==0
        storage_failure=False
        result['checks'].append('S3_failure_before_Oracle_or_model')
        try:invoke()
        except RuntimeError as exc:assert 'OBJECT_IDENTITY_INCOMPLETE' in str(exc)
        else:raise AssertionError('missing tables accepted')
        assert writes==model_calls==0
        result['checks'].append('missing_registered_tables_blocked_without_DDL')
        import prod_run,prod_pipeline
        ns={};exec(text.split('import hashlib')[0],ns)
        params=ns['PARAMS'];cfg,work=prod_run.configure(params,project.project_key)
        contract=prod_pipeline.Contract(work/'contract.json')
        with admin.cursor() as c:
            for key in contract.tables:
                c.execute(contract.ddl(key))
                for statement in contract.indexes(key):c.execute(statement)
                c.execute('GRANT SELECT ON '+contract.table(key)+' TO '+login)
        # Field screenshot: VARCHAR2(1), whereas R1 required CHAR(1 BYTE).
        # Reproduce the exact R1 check against this disposable Oracle schema.
        import copy
        previous=copy.deepcopy(cfg['target'])
        previous['tables']['DOC_BLK']['columns']['ADD_INFO_TEXT_OMIT_YN']['type']='CHAR(1 BYTE)'
        previous_path=out/'r1-contract.json'
        previous_path.write_text(json.dumps(previous))
        db=prod_pipeline.connection(cfg)
        try:prod_pipeline.Contract(previous_path).preflight(db,'DOC_BLK')
        except RuntimeError as exc:
            assert str(exc)=='TYPE_MISMATCH:'+owner+'.IDD_B003_LGL_DOC_BLK.ADDN_IFMN_UN_APPN_YN'
            (out/'expected-r1-column-failure.txt').write_text(traceback.format_exc())
        else:raise AssertionError('R1 unexpectedly accepted VARCHAR2')
        contract.preflight(db,'DOC_BLK')
        assert writes==model_calls==0
        result['checks'].append('R1_CHAR_failure_reproduced_and_R2_VARCHAR2_preflight_passed_real_Oracle')
        try:invoke()
        except Exception as exc:
            assert 'ORA-01031' in str(exc) or 'ORA-00942' in str(exc),str(exc)
            (out/'expected-insert-privilege-failure.txt').write_text(traceback.format_exc())
        else:raise AssertionError('SELECT-only account passed INSERT privilege check')
        assert writes==model_calls==0
        result['checks'].append('different_owner_SELECT_only_login_rejected_before_any_rows')
        with admin.cursor() as c:
            for key in contract.tables:
                if not key.startswith('ONTL'):c.execute('GRANT INSERT ON '+contract.table(key)+' TO '+login)
        # Invalid source bytes must stop before a single INSERT or model call.
        part=folder_root/(archive+'.part000002');correct=part.read_bytes();part.write_bytes(b'corrupt')
        try:invoke()
        except Exception as exc:assert 'PART_HASH' in str(exc)
        else:raise AssertionError('corrupt part accepted')
        assert writes==model_calls==0;part.write_bytes(correct)
        result['checks'].append('corrupt_part_rejected_before_first_insert_or_embedding')
        try:invoke()
        except ConnectionError as exc:
            assert str(exc)=='INJECTED_ACK_LOST_AFTER_ORACLE_COMMIT'
            (out/'injected-ack-loss.txt').write_text(traceback.format_exc())
        else:raise AssertionError('source commit response-loss injection not reached')
        final_failure=True
        try:invoke()
        except OSError as exc:assert 'INJECTED_FINAL_UPLOAD_FAILURE' in str(exc)
        else:raise AssertionError('failed final upload reported success')
        remote=folder_root/cfg['storage']['result']
        assert json.loads((remote/'latest.json').read_text())['status']=='FAILED'
        assert model_calls==1
        result['checks'].append('final_result_upload_failure_not_reported_as_success')
        final_failure=False
        ns=invoke();assert ns['RESULT']['status']=='PRODUCTION_GOLD_LOADED'
        expected={'DOC_VER':2,'DOC_UNIT':3,'DOC_BLK':3,'SRCH_ROW':112,'VCTR_ITEM':3}
        assert ns['RESULT']['counts']==expected
        result['checks']+=['exact_delivered_TXT_34_parts_all_stages_no_DDL_no_Flow',
                          'committed_source_response_loss_resumed_without_duplicates']
        before=model_calls;invoke();assert model_calls==before==1
        result['checks'].append('same_cell_and_final_upload_resume_no_new_embedding')
        assert {n:hashlib.sha256((folder_root/n).read_bytes()).hexdigest() for n in original_hashes}==original_hashes
        assert json.loads((remote/'latest.json').read_text())['status']=='SUCCESS'
        assert list((remote/'runs').rglob('log-*.txt'))
        result['checks'].append('all_original_uploads_preserved_scoped_status_and_logs')
        receipt=work/'workspace.json';backup=out/'workspace-backup.json';receipt.rename(backup)
        before=(sql_calls,model_calls)
        try:invoke()
        except ValueError as exc:assert 'CHECKPOINT_WORKSPACE_MISSING_OR_CHANGED' in str(exc)
        else:raise AssertionError('orphaned remote checkpoint accepted')
        assert before==(sql_calls,model_calls);backup.rename(receipt)
        result['checks'].append('missing_local_workspace_blocks_before_Oracle_and_embedding')
        # Missing load checkpoint cannot adopt matching existing data silently.
        state=work/'load/state.json';saved=out/'load-state-backup.json';state.rename(saved)
        before=(writes,model_calls)
        try:invoke()
        except RuntimeError as exc:assert 'EXISTING_RELEASE_REQUIRES_ORIGINAL_CHECKPOINT' in str(exc)
        else:raise AssertionError('existing release adopted without checkpoint')
        assert before==(writes,model_calls);saved.rename(state)
        result['checks'].append('existing_release_without_original_checkpoint_rejected')
        credentials=out/'credentials.json';credentials.touch(mode=0o600)
        credentials.write_text(json.dumps({'dsn':dsn,'user':login,'password':secret}))
        fresh=subprocess.run([sys.executable,str(HERE/'verify_serving.py'),str(work),str(credentials)],capture_output=True,text=True,timeout=90)
        credentials.unlink();(out/'serving.log').write_text(fresh.stdout+fresh.stderr)
        if fresh.returncode:raise AssertionError('Fresh connector check failed; see serving.log')
        result['checks'].append('fresh_process_source_vector_acl_and_profile_readback')
        result.update(status='PASS',counts=expected,synthetic_embedding_calls=model_calls,sql_calls=sql_calls,
                      code_sha256=hashlib.sha256((HERE/name).read_bytes()).hexdigest(),flow_api_calls=0,
                      loader_DDL_calls=0,distinct_owner_and_login=True,work_dir=str(work))
    except BaseException as exc:
        result.update(status='FAILED',error_type=type(exc).__name__,error=str(exc))
        (out/'failure.txt').write_text(traceback.format_exc())
    finally:
        if conn is not None:conn.close()
        (out/'credentials.json').unlink(missing_ok=True)
        for user in reversed(created):
            with admin.cursor() as c:c.execute('DROP USER '+user+' CASCADE')
        admin.close();result['cleaned']=True
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(result['checks']),'cleaned':result['cleaned']}))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
