"""Build development Gold vectors after R1 verification; never changes serving HEAD."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from mesh_embedding import settings, encode
from progress_display import duration


def windows(text):
    for start in range(0, len(text), 700):
        part = text[start:start+800]
        if part.strip():
            yield start, part
        if start + 800 >= len(text):
            break


def segments(store, version, migration, digest):
    cursor = None
    while True:
        rows = migration.source_batch(store, 'block_payload', version, cursor, batch_rows=100)
        if not rows:
            return
        for row in rows:
            for start, text in windows(row['TEXT']):
                meta = {'document_id': row['DOCUMENT_ID'], 'source_id': row['DOCUMENT_ID']+':'+row['UNIT_ID'],
                        'unit_id': row['UNIT_ID'], 'block_id': row['BLOCK_ID'], 'start': start,
                        'end': start+len(text), 'source_sha256': digest(row),
                        'block_sha256': hashlib.sha256(row['TEXT'].encode()).hexdigest(),
                        'input_sha256': hashlib.sha256(text.encode()).hexdigest()}
                yield {'id': digest([version, meta]), 'meta': meta, 'text': text}
        cursor = [rows[-1]['DOCUMENT_ID'], rows[-1]['BLOCK_ID']]


def vector_sql(contract, publication, items, vectors, canonical, *, verify=False):
    table = contract.table('VCTR_ITEM')
    col = lambda n: contract.col('VCTR_ITEM', n)
    p, sid, doc, src, meta, vec = [col(n) for n in
        ('VCTR_POST_ID', 'VCTR_SEG_ID', 'DOC_ID', 'SRC_UNIT_ID', 'VCTR_META_CTNT', 'EMBD_VCTR_VALU')]
    payload = []
    for item, vector in zip(items, vectors, strict=True):
        m = item['meta']
        for value, name in [(m['document_id'], 'DOC_ID'), (m['source_id'], 'SRC_UNIT_ID')]:
            import re
            limit = int(re.search(r'\((\d+)', contract.tables['VCTR_ITEM']['columns'][name]['type'])[1])
            if not value or len(value.encode()) > limit:
                raise ValueError('VECTOR_COORDINATE_TOO_LONG:'+name)
        payload.append({'id': item['id'], 'doc': m['document_id'], 'src': m['source_id'],
                        'meta': canonical(m), 'vec': canonical(vector)})
    source = "JSON_TABLE(:payload,'$[*]' ERROR ON ERROR COLUMNS (id VARCHAR2(100) PATH '$.id',doc VARCHAR2(50) PATH '$.doc',src VARCHAR2(50) PATH '$.src',meta CLOB PATH '$.meta',vec CLOB PATH '$.vec')) j"
    sql = 'DECLARE n NUMBER; BEGIN '
    if not verify:
        sql += f'INSERT INTO {table} ({p},{sid},{doc},{src},{meta},{vec}) SELECT :pub,j.id,j.doc,j.src,j.meta,TO_VECTOR(j.vec,:dim,FLOAT32) FROM {source} WHERE NOT EXISTS (SELECT 1 FROM {table} t WHERE t.{p}=:pub AND t.{sid}=j.id); '
    sql += f'SELECT COUNT(*) INTO n FROM {source} JOIN {table} t ON (t.{p}=:pub AND t.{sid}=j.id) WHERE t.{doc}=j.doc AND t.{src}=j.src AND DBMS_LOB.COMPARE(t.{meta},j.meta)=0 AND VECTOR_DIMENSION_COUNT(t.{vec})=:dim AND VECTOR_DISTANCE(t.{vec},TO_VECTOR(j.vec,:dim,FLOAT32),EUCLIDEAN)<0.000001; IF n<>:expected THEN RAISE_APPLICATION_ERROR(-20042,\'VECTOR_MISSING_OR_CONFLICT\'); END IF; '
    sql += ('ROLLBACK;' if verify else 'COMMIT;') + ' EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;'
    return sql, [('pub', publication, 'VARCHAR2'), ('payload', canonical(payload), 'CLOB'),
                 ('dim', len(vectors[0]), 'NUMBER'), ('expected', len(items), 'NUMBER')]


def execute(package, old_job):
    # R1 imports resolve in a fresh subprocess, never the notebook's old module cache.
    sys.path.insert(0, str(package))
    import run as loader
    from jdbc_transport import install as install_transport
    install_transport(loader)
    from error_diagnostics import install
    install(loader, os.environ['G19_DIAGNOSTIC_FILE'])
    from gold_io import Contract, Database, canonical, digest, literal
    from lawrag.pipeline import oracle_migration as migration
    import dataiku
    config = settings()
    contract = Contract(package/'contract.json')
    directory = old_job.parent/('gold-shape-'+contract.sha256[:12])
    code = loader.verify_code()
    with (directory/'job.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = loader.read(directory/'state.json')
        if state['status'] != 'SOURCE_QUERY_VERIFIED' or state['binding']['code'] != code:
            raise ValueError('VERIFIED_R1_REQUIRED')
        db = Database(dataiku.SQLExecutor2(connection='AIDP'))
        identity = db.query("SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER, SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME, SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME FROM DUAL")
        if identity != state['binding']['database'] or loader.object_binding(db, contract) != state['binding']['objects']:
            raise ValueError('VECTOR_DATABASE_BINDING_CHANGED')
        for key in ('VCTR_POST', 'VCTR_ITEM'):
            contract.preflight(db, key)
        class Notices:
            def emit(self, phase, **details): print(phase, flush=True)
        root, files, source, query, paths = loader.inputs(old_job, Notices())
        if (files != state['binding']['files'] or digest(source) != state['binding']['source_release'] or
                digest(query) != state['binding']['query_release']):
            raise ValueError('VECTOR_SOURCE_BINDING_CHANGED')
        binding, _ = migration.source_binding(root/'store.sqlite')
        manifest = {'schema_version': 'gold-vector-manifest-preview-v1', 'query_id': digest(query),
                    'source_release_id': digest(source), 'dataset_version': source['dataset_version'],
                    'documents': sorted(source['source_manifest']['scope']['document_version_ids']),
                    'profile': config, 'segment_profile': 'block-text-window800-step700-v1'}
        pub = digest(manifest)
        work = directory/'vectors'/pub
        work.mkdir(parents=True, exist_ok=True)
        checkpoint = work/'state.json'
        helper_hashes = {p.name: loader.file_hash(p) for p in (Path(__file__), Path(__file__).with_name('mesh_embedding.py'))}
        job_binding = {'loader': state['binding'], 'manifest': manifest, 'helper': helper_hashes}
        progress = loader.read(checkpoint) if checkpoint.exists() else {
            'binding': job_binding, 'deadline': state['deadline'], 'calls': 0, 'completed_batches': 0,
            'rows': 0, 'status': 'PREPARING'}
        if progress['binding'] != job_binding:
            raise ValueError('VECTOR_JOB_BINDING_CHANGED')
        def save(): loader.atomic(checkpoint, progress)
        def guard():
            loader.resource_check(work)
            migration.unchanged(binding)
            if time.time() >= progress['deadline']:
                raise ValueError('ORIGINAL_DEADLINE_EXPIRED')
        guard(); save()
        store = migration.source_open(root/'store.sqlite')
        started, initial_rows = time.monotonic(), progress['rows']
        print('벡터 준비: 전체 구간 수 계산 중 / 모델='+config['model'], flush=True)
        total = 0
        for item in segments(store, source['dataset_version'], migration, digest):
            # Fail before the first model call if coordinates cannot fit the Gold schema.
            vector_sql(contract, pub, [item], [[1.0]], canonical, verify=True)
            if item['meta']['document_id'] not in manifest['documents']:
                raise ValueError('VECTOR_DOCUMENT_OUTSIDE_MANIFEST')
            total += 1
            if total % 10000 == 0:
                guard(); print('벡터 대상 계산:', total, '구간', flush=True)
        if total == 0:
            raise ValueError('VECTOR_EMPTY_CORPUS')
        project = dataiku.api_client().get_default_project()
        chain = '0'*64
        batch = []
        index = 0
        try:
            def flush(items, number):
                guard()
                marker = digest(items)
                cache = work/(f'batch-{number:08d}.json')
                if cache.exists():
                    response = loader.read(cache)
                    if response['input'] != marker or response['sha256'] != digest(response['vectors']):
                        raise ValueError('VECTOR_RESPONSE_CACHE_CONFLICT')
                    vectors = response['vectors']
                else:
                    if number < progress['completed_batches']:
                        raise ValueError('VECTOR_COMPLETED_CACHE_MISSING')
                    if progress.get('pending') is not None:
                        raise ValueError('EMBEDDING_OUTCOME_UNKNOWN_NO_AUTOMATIC_RETRY')
                    progress.update(pending={'batch': number, 'input': marker}, status='EMBEDDING_IN_FLIGHT')
                    progress['calls'] += 1; save()
                    vectors = encode(project, config, [i['text'] for i in items])
                    loader.atomic(cache, {'input': marker, 'vectors': vectors, 'sha256': digest(vectors)})
                completed = number < progress['completed_batches']
                if not completed and progress.get('pending') not in (None, {'batch': number, 'input': marker}):
                    raise ValueError('VECTOR_PENDING_INPUT_CONFLICT')
                guard()
                sql, binds = vector_sql(contract, pub, items, vectors, canonical,
                                        verify=number < progress['completed_batches'])
                db.block(sql, binds, rollback=number < progress['completed_batches'])
                if number >= progress['completed_batches']:
                    progress['rows'] += len(items)
                    progress['completed_batches'] = number+1
                if not completed:
                    progress.update(pending=None, status='STORING'); save()
                elapsed = time.monotonic()-started
                rate = (progress['rows']-initial_rows)/elapsed if elapsed and progress['rows']>initial_rows else 0
                eta = (total-progress['rows'])/rate if rate else None
                print(f"벡터 {progress['rows']:,}/{total:,}행 ({progress['rows']/total:.2%}) | 경과 {duration(elapsed)} | 예상 잔여 {duration(eta)} | SDK 호출 {progress['calls']:,}", flush=True)
            for item in segments(store, source['dataset_version'], migration, digest):
                chain = digest([chain, item['id'], item['meta']])
                batch.append(item)
                if len(batch) == 16:
                    flush(batch, index); batch=[]; index+=1
            if batch:
                flush(batch, index)
            guard()
            actual = db.query('SELECT COUNT(*) AS N FROM '+contract.table('VCTR_ITEM')+' WHERE '+contract.col('VCTR_ITEM','VCTR_POST_ID')+'='+literal(pub))
            if actual != [{'N': total}] or progress['rows'] != total:
                raise ValueError('VECTOR_FINAL_COUNT_MISMATCH')
            envelope = {'manifest': manifest, 'completion': {'status': 'READY', 'count': total,
                        'chain': chain, 'profile_sha256': digest(config)}}
            sql, binds = contract.batch('VCTR_POST', [{'VCTR_POST_ID': pub, 'VCTR_POST_IFMN_CTNT': canonical(envelope)}])
            db.block(sql, binds)
            progress.update(status='VECTORS_STORED_VERIFIED_NOT_ACTIVATED', publication_id=pub, total=total)
            save()
            print(progress['status']+' | '+str(total)+'행 | 서비스 전환 안 함', flush=True)
        except BaseException as exc:
            progress.update(status='FAILED', error_type=type(exc).__name__)
            save()
            raise
        finally:
            store.close()


if __name__ == '__main__':
    try:
        execute(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
    except Exception as exc:
        from error_diagnostics import event, banner
        print(banner(event(exc,{'stage':'VECTOR'})),flush=True)
        raise SystemExit(1)
