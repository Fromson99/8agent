"""R7 flow-recipe local check: real Oracle 23ai, disposable owner/login, exact R5 then exact R6 TXT.

R5 loads the synthetic 34-part Gold (no selection, like the field). R6 then adds the
latest-version selection; the selected local MAIN serving code checks the result.
DSS SDK and embedding are local substitutes. All schemas are dropped at the end.
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

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
R5 = HERE.parent/'gold_oneclick_prod_20261105_r5'
R6 = HERE.parent/'gold_selection_fix_20261109_r6'
CONNECT = REPO/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--output', required=True); args = ap.parse_args()
    out = Path(args.output).resolve(); out.mkdir(parents=True, exist_ok=False)
    import oracledb
    import pandas as pd
    oracledb.defaults.fetch_lobs = False
    result = {'status': 'RUNNING', 'checks': [], 'external_models': 0, 'dataiku_sdk': 'LOCAL_SUBSTITUTE',
              'field_execution': False, 'cleaned': False}
    container = json.loads(subprocess.check_output(['docker', 'inspect', 'a8-legal-mapped-20261023']))[0]
    port = container['HostConfig']['PortBindings']['1521/tcp'][0]['HostPort']
    dsn = '127.0.0.1:'+port+'/FREEPDB1'
    password = dict(s.split('=', 1) for s in container['Config']['Env'])['ORACLE_PASSWORD']
    suffix = secrets.token_hex(4).upper(); owner = 'A8_SO_'+suffix; login = 'A8_SL_'+suffix; secret = secrets.token_hex(24)
    admin = oracledb.connect(user='system', password=password, dsn=dsn); admin.call_timeout = 30000
    conn = None; created = []
    state = {'sql': 0, 'writes': 0, 'updates': 0, 'inject': set()}
    try:
        with admin.cursor() as c:
            for user in (owner, login):
                c.execute('CREATE USER '+user+' IDENTIFIED BY "'+secret+'" DEFAULT TABLESPACE USERS QUOTA 256M ON USERS')
                created.append(user); c.execute('GRANT CREATE SESSION TO '+user)
        conn = oracledb.connect(user=login, password=secret, dsn=dsn); conn.call_timeout = 60000

        class Injected(ConnectionError):
            pass

        class Executor:
            def query_to_df(self, query, pre_queries=(), post_queries=(), **kw):
                with conn.cursor() as c:
                    for sql in pre_queries:
                        assert not re.search(r'\b(CREATE|ALTER|DROP|TRUNCATE|DELETE)\b', sql, re.I), sql[:120]
                        c.execute(sql); state['sql'] += 1
                        if 'IF FALSE' not in sql:
                            if 'INSERT INTO' in sql: state['writes'] += 1
                            if re.search(r'\bUPDATE\b', sql): state['updates'] += 1
                        for tag in list(state['inject']):
                            if tag in sql and 'IF FALSE' not in sql:
                                state['inject'].discard(tag)
                                raise Injected('INJECTED_RESPONSE_LOST_AFTER_COMMIT:'+tag)
                    c.execute(query); state['sql'] += 1
                    frame = pd.DataFrame(c.fetchall(), columns=[d[0] for d in c.description])
                    for sql in post_queries: c.execute(sql)
                    return frame

        folder_root = out/'existing-upload-folder'; folder_root.mkdir()
        r5zip = 'DATAIKU_GOLD_ONECLICK_PROD_20261105_R5.zip'
        (folder_root/r5zip).write_bytes((R5/r5zip).read_bytes())
        fixture = REPO/'09_ARTIFACTS/AUDITS/20261104-gold-r5-code-integration/fixture/upload'
        archive = 'genos-rag-data-20261007T002029Z-7c0b050f.zip'
        for p in fixture.iterdir():
            if '.part' in p.name: (folder_root/p.name.replace('synthetic-gold.zip', archive)).write_bytes(p.read_bytes())
            elif p.suffix == '.sha256': (folder_root/p.name).write_text(p.read_text().replace('synthetic-gold.zip', archive))

        folder_in = out/'gold_selection_input'; folder_in.mkdir()
        folder_out = out/'gold_selection_result'; folder_out.mkdir()
        roots = {'existingFolder': folder_root, 'gold_selection_input': folder_in, 'gold_selection_result': folder_out}

        class Folder:
            def __init__(self, key, *a, **kw): self.root = roots[key]
            def list_paths_in_partition(self): return ['/'+p.relative_to(self.root).as_posix() for p in self.root.rglob('*') if p.is_file()]
            def get_download_stream(self, path): return (self.root/path.lstrip('/')).open('rb')
            def upload_stream(self, path, stream):
                if self.root != folder_root: raise AssertionError('RECIPE_WROTE_TO_BUCKET:'+path)
                p = self.root/path.lstrip('/'); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(stream.read())

        class Embedding:
            def __init__(self): self.texts = []
            def add_text(self, text): self.texts.append(text)
            def execute(self): return types.SimpleNamespace(get_embeddings=lambda: [[1., 0., 0., 0.] for _ in self.texts])

        class Project:
            project_key = 'EXISTING_PRODUCTION_PROJECT'
            def get_llm(self, name): return types.SimpleNamespace(new_embeddings=lambda **kw: Embedding())
        project = Project()
        shim = types.ModuleType('dataiku'); shim.Folder = Folder; shim.SQLExecutor2 = lambda **kw: Executor()
        shim.api_client = lambda: types.SimpleNamespace(get_default_project=lambda: project, get_project=lambda key: project)
        sys.modules['dataiku'] = shim
        common = {"'CODE_FOLDER_ID': ''": "'CODE_FOLDER_ID': 'existingFolder'",
                  "'ORACLE_CONNECTION': 'AIDP'": "'ORACLE_CONNECTION': 'synthetic'",
                  "'EXPECTED_DB_USER': 'PIDD2APP'": "'EXPECTED_DB_USER': "+repr(login),
                  "'WORK_DIR': ''": "'WORK_DIR': "+repr(str(out/'work-base')),
                  "'EMBED_MODEL': 'openai:genos-embedding:embedding-kure-v1'": "'EMBED_MODEL': 'SYNTHETIC_NO_EXTERNAL_MODEL'",
                  "'EMBED_DIMENSIONS': 1024": "'EMBED_DIMENSIONS': 4"}
        r5_text = (R5/'DATAIKU_GOLD_PROD_RUN_R5.txt').read_text()
        for a, b in {**common, "'GOLD_OWNER': 'SIDDS'": "'GOLD_OWNER': "+repr(owner)}.items():
            assert a in r5_text; r5_text = r5_text.replace(a, b)
        # The exact recipe code embedded in the delivered flow installer.
        installer = (HERE/'DATAIKU_CREATE_GOLD_FIX_FLOW_R7.txt').read_text()
        r7_source = eval(installer.split('RECIPE_CODE = ', 1)[1].split('\nif hashlib.sha256', 1)[0])
        assert r7_source == (HERE/'recipe_gold_selection_fix_r7.py').read_text()
        variables = {}
        shim.get_custom_variables = lambda: dict(variables)

        def r6(mode, **fix):
            # Mode and production values come from project variables, as in the delivered flow.
            variables.clear()
            variables.update({'GOLD_FIX_MODE': mode, 'GOLD_FIX_ORACLE_CONNECTION': 'synthetic',
                              'GOLD_FIX_EXPECTED_DB_USER': login, 'GOLD_FIX_GOLD_OWNER': owner})
            text = r7_source
            for k, v in fix.items():
                pattern = "'"+k+"': "
                line = next(l for l in text.splitlines() if l.strip().startswith(pattern))
                text = text.replace(line, "    "+pattern+repr(v)+",")
            ns = {}; exec(compile(text, '<exact-delivered-r7-recipe>', 'exec'), ns); return ns['RESULT']

        # 1) R5 load into disposable Gold (same as the field, no selection).
        ns = {}; exec(r5_text.split('import hashlib')[0], ns)
        # Prepare tables exactly as R5's own local check does.
        def r5_invoke():
            n = {}; exec(compile(r5_text, '<exact-delivered-r5>', 'exec'), n); return n
        try: r5_invoke()
        except Exception as exc: assert 'OBJECT_IDENTITY_INCOMPLETE' in str(exc), str(exc)
        import prod_run, prod_pipeline
        cfg, work = prod_run.configure(ns['PARAMS'], project.project_key)
        contract = prod_pipeline.Contract(work/'contract.json')
        with admin.cursor() as c:
            for key in contract.tables:
                ddl = contract.ddl(key)
                if key == 'VCTR_ITEM':
                    ddl = ('CREATE TABLE '+contract.table(key)+' (VCTR_POST_ID VARCHAR2(100 BYTE) NOT NULL, '
                           'VCTR_SCTN_ID VARCHAR2(100 BYTE) NOT NULL, RGLT_DOC_ID VARCHAR2(100 BYTE) NOT NULL, '
                           'BODY_UNIT_ID VARCHAR2(100 BYTE) NOT NULL, VCTR_DTLS_IFMN_CTNT CLOB NOT NULL, '
                           'EMBD_VCTR VECTOR(*,FLOAT32) NOT NULL, PRIMARY KEY (VCTR_POST_ID,VCTR_SCTN_ID))')
                c.execute(ddl)
                for statement in contract.indexes(key): c.execute(statement)
                c.execute('GRANT SELECT ON '+contract.table(key)+' TO '+login)
                if not key.startswith('ONTL'): c.execute('GRANT INSERT ON '+contract.table(key)+' TO '+login)
        loaded = r5_invoke()['RESULT']
        assert loaded['status'] == 'PRODUCTION_GOLD_LOADED', loaded
        report = json.loads((work/'report.json').read_text())
        q0 = report['query_release_id']; channel = report['channel']
        result['checks'].append('R5_synthetic_gold_loaded_without_selection')

        # 2) Selection file for this generation (exclude one of the two documents).
        generation = work/'restored/generation'
        manifest = json.loads((generation/'manifest.json').read_text())
        docs = sorted(manifest['scope']['document_version_ids']); assert len(docs) == 2
        keep, drop = docs
        selection = {'schema_version': 'filename-search-selection-v2', 'generation_id': manifest['generation_id'],
                     'generation_path': '/nfs/synthetic/generation',
                     'manifest_sha256': hashlib.sha256((generation/'manifest.json').read_bytes()).hexdigest(),
                     'store_sha256': manifest['store_sha256'], 'metadata_sha256': '0'*64,
                     'policy': 'user-approved-retained-set-latest-v2',
                     'excluded': [{'document_id': drop, 'source_artifact_sha256': 'f'*64, 'reason': 'older dated filename'}],
                     'latest_documents': [{'document_id': keep, 'is_latest': True}, {'document_id': drop, 'is_latest': False}]}
        sel_path = folder_in/'SEARCH_SELECTION_GENERATION.json'
        sel_path.write_text(json.dumps(selection, ensure_ascii=False, indent=2))

        # 3) Serving check with the selected local MAIN code (same Store as code serving).
        credentials = out/'credentials.json'; credentials.touch(mode=0o600)
        credentials.write_text(json.dumps({'dsn': dsn, 'user': login, 'password': secret}))
        def serving(documents):
            run = subprocess.run([sys.executable, '-I', str(HERE/'serving_check.py'), str(work), str(credentials),
                                  channel, json.dumps(documents)], capture_output=True, text=True, timeout=180)
            (out/'serving-calls.log').open('a').write(run.stdout+run.stderr+'\n----\n')
            value = json.loads(run.stdout.strip().splitlines()[-1])
            if not value['ok']: raise RuntimeError(value['error'])
            return value

        try: serving(docs)
        except Exception as exc: assert 'Dataiku must verify latest document selection' in str(exc), repr(exc)
        else: raise AssertionError('serving accepted release without selection')
        result['checks'].append('field_error_reproduced_QUERY_SELECTION_before_R6')

        def table_count(key):
            with admin.cursor() as c:
                c.execute('SELECT COUNT(*) FROM '+contract.table(key)); return c.fetchone()[0]
        def snapshot():
            with admin.cursor() as c:
                c.execute('SELECT RFRN_CHNL_NAME,RFRN_POST_HASH_VALU,CHAN_NO FROM '+contract.table('SRCH_CHNL'))
                chan = c.fetchall()
            return {'chan': chan, **{k: table_count(k) for k in ('SRC_POST', 'SRCH_POST', 'VCTR_POST', 'VCTR_HEAD')}}
        before = snapshot()

        # 4) No UPDATE privilege: stop before any write, print GRANT lines.
        w = (state['writes'], state['updates'])
        try: r6('CHECK')
        except Exception as exc:
            assert 'PRIVILEGE_REQUIRED' in str(exc) and 'GRANT UPDATE ON '+owner+'.IDD_B003_LGL_SRCH_ROW' in str(exc), str(exc)
        else: raise AssertionError('missing UPDATE privilege accepted')
        assert (state['writes'], state['updates']) == w and snapshot() == before
        result['checks'].append('missing_UPDATE_privilege_stops_before_writes_with_GRANT_lines')
        with admin.cursor() as c:
            for key in ('SRCH_ROW', 'VCTR_ITEM', 'VCTR_HEAD', 'SRCH_CHNL'):
                c.execute('GRANT UPDATE ON '+contract.table(key)+' TO '+login)

        # 5) CHECK changes nothing.
        checked = r6('CHECK')
        assert checked['status'] == 'CHECK_OK' and checked['plan']['excluded'] == 1 and checked['plan']['searchable'] == 1
        assert (state['writes'], state['updates']) == w and snapshot() == before
        result['checks'].append('CHECK_mode_read_only')

        # 6) Selection for another generation is refused.
        good = sel_path.read_bytes()
        wrong = dict(selection, manifest_sha256='0'*64); sel_path.write_text(json.dumps(wrong))
        try: r6('CHECK')
        except Exception as exc: assert 'SELECTION_BELONGS_TO_ANOTHER_GENERATION' in str(exc), str(exc)
        else: raise AssertionError('wrong generation selection accepted')
        sel_path.write_bytes(good)
        result['checks'].append('selection_for_other_generation_refused')

        # 7) APPLY with tiny batches and two lost responses after commit; rerun resumes.
        state['inject'] = {contract.table('SRCH_ROW')+' t SET', 'UPDATE '+contract.table('VCTR_HEAD')}
        for _ in range(2):
            try: r6('APPLY', UPDATE_BATCH_ROWS=7, UPDATE_BLOCK_SECONDS=1)
            except ConnectionError as exc: assert 'INJECTED' in str(exc)
            else: raise AssertionError('injection not reached')
        assert not state['inject']
        applied = r6('APPLY', UPDATE_BATCH_ROWS=7, UPDATE_BLOCK_SECONDS=1)
        assert applied['status'] == 'APPLIED', applied
        plan = applied['plan']; assert plan['q0'] == q0 and plan['q1'] != q0
        result['checks'].append('APPLY_resumed_after_lost_responses_SRCH_ROW_and_VCTR_HEAD')

        # 8) Same serving code now starts; excluded document is outside the request scope.
        served = serving([keep])
        assert served['release'] == plan['q1'] and served['excluded'] == [drop]
        assert served['vector_publication'] == plan['vector']['v1']
        try: serving(docs)
        except Exception as exc: assert 'QUERY_SCOPE' in str(exc), repr(exc)
        else: raise AssertionError('excluded older document still searchable')
        result['checks'].append('MAIN_serving_require_latest_and_vector_publication_pass_after_R6')
        result['checks'].append('excluded_document_removed_from_serving_scope')
        with admin.cursor() as c:
            c.execute('SELECT COUNT(*) FROM '+contract.table('SRCH_ROW')+' WHERE RFRN_POST_HASH_VALU=:q', q=q0)
            assert c.fetchone()[0] == 0
            c.execute('SELECT COUNT(*) FROM '+contract.table('SRCH_ROW')+' WHERE RFRN_POST_HASH_VALU=:q', q=plan['q1'])
            assert c.fetchone()[0] == plan['search_rows'] == 112

        # 9) Repeat APPLY is a no-op.
        u = state['updates']
        again = r6('APPLY'); assert again['status'] == 'ALREADY_APPLIED' and state['updates'] == u
        result['checks'].append('repeat_APPLY_no_writes')

        # 10) ROLLBACK restores the original state exactly (posts kept), then APPLY again.
        back = r6('ROLLBACK', UPDATE_BATCH_ROWS=5)
        assert back['status'] == 'ROLLED_BACK'
        after_back = snapshot()
        assert after_back['chan'][0][:2] == before['chan'][0][:2]
        try: serving(docs)
        except Exception as exc: assert 'Dataiku must verify latest document selection' in str(exc)
        else: raise AssertionError('rollback did not restore original')
        result['checks'].append('ROLLBACK_restores_original_release')
        reapplied = r6('APPLY')
        assert reapplied['status'] == 'APPLIED' and reapplied['plan'] == plan
        assert serving([keep])['release'] == plan['q1']
        result['checks'].append('APPLY_after_ROLLBACK_same_release_ids')
        credentials.unlink()
        result.update(status='PASS', q0=q0, q1=plan['q1'], plan=plan, sql_calls=state['sql'],
                      input_folder_files=sorted(p.name for p in folder_in.iterdir()), output_folder_files=sorted(p.name for p in folder_out.iterdir()))
        assert result['input_folder_files'] == ['SEARCH_SELECTION_GENERATION.json'] and result['output_folder_files'] == []
        result['checks'].append('no_folder_or_bucket_writes_by_recipe')
    except BaseException:
        result['status'] = 'FAIL'; result['error'] = traceback.format_exc()
        raise
    finally:
        if conn is not None: conn.close()
        with admin.cursor() as c:
            for user in reversed(created):
                c.execute('DROP USER '+user+' CASCADE')
        admin.close(); result['cleaned'] = True
        (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=1))
        print(json.dumps({k: result[k] for k in ('status', 'checks', 'cleaned')}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
