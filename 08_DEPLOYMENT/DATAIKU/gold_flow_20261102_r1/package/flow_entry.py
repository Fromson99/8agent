"""Stage boundaries around the byte-identical FRESH_1 engine."""
import fcntl
import json
import os
from pathlib import Path
import sys
import time
from flow_spec import ENGINE, STAGES
sys.path.insert(0, str(ENGINE))
import run as loader
from flow_inputs import install_inputs
install_inputs(loader)

def emit(phase, **fields):
    print(loader.canonical(dict(phase=phase, **fields)), flush=True)

def job_dir(old_job):
    return old_job.parent / ('gold-shape-' + loader.Contract(ENGINE/'contract.json').sha256[:12])

def source_complete(state, source):
    return all(state.get('source', {}).get(k, {}) == dict(v, cursor=state.get('source', {}).get(k, {}).get('cursor'))
               for k, v in source['source_rows'].items())

def stage_db(stage, old_job):
    import dataiku
    from jdbc_transport import install
    install(loader)
    contract = loader.Contract(ENGINE/'contract.json')
    directory = job_dir(old_job); directory.mkdir(exist_ok=True)
    progress = loader.Progress(); progress.thread.start()
    job = None
    try:
        with (directory/'job.lock').open('a') as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise RuntimeError('EXISTING_LOAD_RUNNING: 기존 노트북 종료 후 Flow 실행') from None
            loader.resource_check(directory)
            db = loader.Database(dataiku.SQLExecutor2(connection='AIDP'))
            identity = db.query("SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER, SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME, SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME FROM DUAL")
            if len(identity)!=1 or identity[0]['LOGIN_USER']!='PIDD2APP': raise ValueError('EXPECTED_PIDD2APP_CONNECTION')
            if stage == 'schema':
                contract.create(db, progress.emit)
                if not (directory/'state.json').exists():
                    for key in contract.tables:
                        if db.query('SELECT COUNT(*) AS N FROM '+contract.table(key)) != [{'N': 0}]:
                            raise ValueError('NEW_SUFFIX_TABLE_ALREADY_HAS_ROWS:'+contract.table(key))
                for key in contract.tables:
                    seconds = contract.probe(db, key)
                    progress.emit('INSERT_ROLLBACK_PASS', table=contract.table(key), seconds=seconds)
            else:
                for key in contract.tables: contract.preflight(db, key)
            root, files, source, query, paths = loader.inputs(old_job, progress)
            binding = {'code': loader.verify_code(), 'contract': contract.sha256, 'database': identity,
                       'objects': loader.object_binding(db, contract), 'generation': str(root), 'files': files,
                       'source_release': loader.digest(source), 'query_release': loader.digest(query)}
            if stage!='schema' and not (directory/'state.json').exists(): raise ValueError('RUN_02_TABLES_FIRST')
            job = loader.Job(db, contract, directory, binding, progress, retry_missing=False)
            if stage=='schema': return {'tables': len(contract.tables), 'state': job.state['status']}
            if job.state['status']=='SOURCE_QUERY_VERIFIED':
                return {'reuse': 'VERIFIED_CHECKPOINT', 'current_database_reverified': False}
            if stage=='source':
                if source_complete(job.state, source): return {'reuse': 'SOURCE_CHECKPOINT', 'current_database_reverified': False}
                loader.load_sources(job, root, source)
                job.state['status']='SOURCE_LOADED'; job.save()
            elif stage=='query':
                if not source_complete(job.state, source): raise ValueError('RUN_03_SOURCE_FIRST')
                if job.state['status']=='LOADED_UNVERIFIED': return {'reuse': 'QUERY_CHECKPOINT', 'current_database_reverified': False}
                loader.load_query(job, root, files, source, query, paths)
                job.state['status']='LOADED_UNVERIFIED'; job.save()
            elif stage=='verify':
                if job.state['status'] not in {'LOADED_UNVERIFIED','VERIFYING','VERIFY_FAILED','WRITE_UNCONFIRMED'}:
                    raise ValueError('RUN_04_SEARCH_FIRST')
                if not job.state.get('verification_finished'):
                    loader.load_sources(job, root, source, verify_only=True)
                    loader.load_query(job, root, files, source, query, paths, verify_only=True)
                    job.state['verification_finished']=True; job.save()
                loader.publish(job, root, files, source, query)
            else: raise ValueError('FLOW_DB_STAGE')
            return {'state': job.state['status']}
    except BaseException as exc:
        if job:
            job.state['last_error']={'type':type(exc).__name__, 'codes':loader.error_codes(exc), 'phase':stage, 'time':time.time()}
            if job.state.get('pending'): job.state['status']='WRITE_UNCONFIRMED'
            job.save()
        raise
    finally:
        progress.stop.set(); progress.thread.join(timeout=2)

def report_db(old_job):
    import dataiku
    from jdbc_transport import install
    install(loader)
    contract = loader.Contract(ENGINE/'contract.json')
    db = loader.Database(dataiku.SQLExecutor2(connection='AIDP'))
    records = []
    # Only this explicit final report performs all-table counts; heartbeat never scans DB.
    for key in contract.tables:
        rows=db.query('SELECT COUNT(*) AS N FROM '+contract.table(key))
        records.append({'key':key, 'table':contract.table(key), 'rows':int(rows[0]['N']), 'checked_at':time.time()})
        emit('DB_COUNT', **records[-1])
    state=loader.read(job_dir(old_job)/'state.json')
    if state['status']!='SOURCE_QUERY_VERIFIED': raise ValueError('SOURCE_QUERY_VERIFICATION_REQUIRED')
    root, files, source, query, paths=loader.inputs(old_job, loader.Progress())
    counts={r['key']:r['rows'] for r in records}
    for kind,(key,*_) in loader.SOURCE_MAP.items():
        if counts[key]!=source['source_rows'][kind]['rows']: raise ValueError('REPORT_SOURCE_COUNT:'+key)
    if counts['SRCH_ROW']!=sum(v['rows'] for v in query['tables'].values()): raise ValueError('REPORT_QUERY_COUNT')
    vector_states=[loader.read(p) for p in (job_dir(old_job)/'vectors').glob('*/state.json')]
    completed=[v for v in vector_states if v.get('status')=='VECTORS_STORED_VERIFIED_NOT_ACTIVATED']
    if not completed: raise ValueError('VECTOR_NOT_COMPLETE')
    for v in completed:
        row=db.query('SELECT COUNT(*) AS N FROM '+contract.table('VCTR_ITEM')+' WHERE '+contract.col('VCTR_ITEM','VCTR_POST_ID')+'='+loader.literal(v['publication_id']))
        if int(row[0]['N'])!=v['total']: raise ValueError('REPORT_VECTOR_COUNT')
    return {'tables':records, 'status':'DB_COUNTS_CONFIRMED', 'source_query':state['status'],
            'vectors':sum(v['total'] for v in completed), 'serving':'NOT_SWITCHED'}

def execute(stage, cfg, old_job):
    import dataiku
    old_job.parent.mkdir(parents=True, exist_ok=True)
    # Keep all Flow invocations serialized on the same scratch used by the existing loader.
    with (old_job.parent/'gold-flow-1.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('FLOW_ALREADY_RUNNING') from None
        loader.verify_code()
        if stage in {'receive','prepare'}:
            # Do not scan/rebuild input while the notebook is still writing the same job.
            directory=job_dir(old_job)
            directory.mkdir(exist_ok=True)
            with (directory/'job.lock').open('a') as input_lock:
                try: fcntl.flock(input_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError: raise RuntimeError('EXISTING_LOAD_RUNNING: 기존 노트북 종료 후 Flow 실행') from None
                import flow_inputs
                if stage=='receive':
                    ids=[cfg['folders']['receive']] + cfg.get('legacy_cache',[])
                    result=flow_inputs.receive(old_job, dataiku.get_custom_variables(), [dataiku.Folder(i) for i in ids], emit)
                else: result=flow_inputs.prepare(old_job, loader.Progress())
        elif stage=='vector':
            from vector_stage import execute as vector
            vector(ENGINE, old_job)
            result={'status':'VECTORS_STORED_VERIFIED_NOT_ACTIVATED'}
        elif stage=='report': result=report_db(old_job)
        else: result=stage_db(stage, old_job)
    emit('FLOW_STAGE_RESULT', stage=stage, result=result)

if __name__=='__main__':
    from error_diagnostics import install, event, banner
    install(loader, os.environ['G19_DIAGNOSTIC_FILE'])
    try:
        cfg=json.loads(Path(sys.argv[2]).read_text())
        execute(sys.argv[1], cfg, Path(os.environ['G19_OLD_JOB_DIR']).resolve())
    except BaseException as exc:
        diagnostic=event(exc, {'stage':sys.argv[1]})
        print(loader.canonical(diagnostic),flush=True)
        print(banner(diagnostic),flush=True)
        raise SystemExit(1)
