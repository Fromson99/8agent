"""R6/R7 vector INSERT/COMMIT. Only uncertain writes check their primary keys."""
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sys
import time
import run_full as loader
from fast_insert import Contract
from fast_inputs import inputs
from gold_io import Stop, canonical, digest, error_codes
from mesh_embedding import settings, encode
from structure_segments import POLICY, segments

MAX_ROWS = 512
MAX_BYTES = 16 * 1024**2
COMPLETE = 'VECTORS_STORED_INSERT_ACK_NOT_ACTIVATED'
STOP_REQUESTED = False


def request_stop(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def check_stop():
    if STOP_REQUESTED:
        raise Stop('VECTOR_USER_STOPPED_RESUME_AVAILABLE')


def select_parent(old_job, package):
    contract = Contract(package/'contract.json')
    parent = old_job.parent/('gold-shape-'+contract.sha256[:12])
    reduced = parent.with_name(parent.name+'-reduced-r4')
    directory = reduced if (reduced/'state.json').is_file() else parent
    prior = loader.read(directory/'state.json')
    allowed = {x['code_binding'] for x in loader.read(package/'VECTOR_PARENTS.json')['parents']}
    if prior['binding']['code'] not in allowed:
        raise Stop('VECTOR_COMPLETED_R6_OR_R7_REQUIRED')
    if ('projection_policy' in prior['binding']) != (directory == reduced):
        raise Stop('VECTOR_PARENT_MODE_MISMATCH')
    if prior.get('pending') or prior.get('status') not in {'LOADED_INSERT_ACK', 'SOURCE_QUERY_PUBLISHED'}:
        raise Stop('VECTOR_FINISH_SOURCE_QUERY_LOAD_FIRST')
    if prior['binding']['contract'] != contract.sha256:
        raise Stop('VECTOR_PARENT_CONTRACT_CHANGED')
    return parent, directory, prior


def signatures(root, navigation_path):
    result = {}
    for name in ('store.sqlite', 'manifest.json', navigation_path):
        path = (root/name).resolve(strict=True)
        if root not in path.parents:
            raise Stop('VECTOR_SOURCE_PATH')
        st = path.stat()
        result[name] = [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]
    if any((root/(name+suffix)).exists() for name in ('store.sqlite', navigation_path) for suffix in ('-wal', '-journal')):
        raise Stop('VECTOR_SOURCE_NOT_SEALED')
    return result


def rows_for(publication, items, vectors):
    # Both inputs are bounded lists, including when restored from the cache.
    # Keep strict pairing without the Python 3.10-only zip keyword.
    if len(items) != len(vectors):
        raise Stop('VECTOR_EMBED_COUNT_MISMATCH')
    return [{'VCTR_POST_ID': publication, 'VCTR_SEG_ID': i['id'], 'DOC_ID': i['meta']['document_id'],
             'SRC_UNIT_ID': i['meta']['source_id'], 'VCTR_META_CTNT': canonical(i['meta']),
             'EMBD_VCTR_VALU': canonical(v)} for i, v in zip(items, vectors)]


def check_coordinates(contract, items, allowed):
    for item in items:
        m = item['meta']
        if m['document_id'] not in allowed:
            raise Stop('VECTOR_DOCUMENT_OUTSIDE_MANIFEST')
        for value, name in ((m['document_id'], 'DOC_ID'), (m['source_id'], 'SRC_UNIT_ID')):
            limit = int(re.search(r'\((\d+)', contract.tables['VCTR_ITEM']['columns'][name]['type'])[1])
            if not value or '\0' in value or len(value.encode()) > limit:
                raise Stop('VECTOR_COORDINATE_TOO_LONG:'+name)


def vector_sql(contract, rows, dimensions):
    if not rows or len(rows) > MAX_ROWS or type(dimensions) is not int or not 1 <= dimensions <= 4096:
        raise Stop('VECTOR_BATCH_SHAPE')
    names = ('VCTR_POST_ID', 'VCTR_SEG_ID', 'DOC_ID', 'SRC_UNIT_ID', 'VCTR_META_CTNT', 'EMBD_VCTR_VALU')
    specs = [alias+' '+typ+" PATH '$."+name+"' ERROR ON ERROR" for alias, typ, name in zip(
        ('p','s','d','u','m','v'), ('VARCHAR2(100)','VARCHAR2(100)','VARCHAR2(50)','VARCHAR2(50)','CLOB','CLOB'), names)]
    sql = ('BEGIN INSERT INTO '+contract.table('VCTR_ITEM')+' ('+
           ','.join(contract.col('VCTR_ITEM', n) for n in names)+') '
           'SELECT j.p,j.s,j.d,j.u,j.m,TO_VECTOR(j.v,:dim,FLOAT32) '
           "FROM JSON_TABLE(:payload,'$[*]' ERROR ON ERROR COLUMNS("+','.join(specs)+')) j; '
           'COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
    return sql, [('payload', canonical(rows), 'CLOB'), ('dim', dimensions, 'NUMBER')]


class VectorJob:
    def __init__(self, db, contract, work, binding, progress):
        self.db, self.contract, self.work, self.progress = db, contract, work, progress
        self.path = work/'state.json'
        self.state = loader.read(self.path) if self.path.exists() else {
            'binding': binding, 'status': 'NEW', 'deadline': time.time()+7*86400, 'max_calls': 1000000,
            'embedding_calls': 0, 'next_batch': 0, 'rows': 0, 'cursor': None, 'chain': '0'*64,
            'pending': None, 'embedding_pending': None, 'insert_requests': 0, 'pending_key_queries': 0}
        if self.state['binding'] != binding:
            raise Stop('VECTOR_JOB_BINDING_CHANGED')
        self.next_guard = 0
        self.plan = None
        self.total = None
        self.started = time.monotonic()
        self.initial_rows = self.state['rows']

    def save(self):
        loader.atomic(self.path, self.state)

    def guard(self):
        check_stop()
        if time.time() >= self.state['deadline']:
            raise Stop('VECTOR_ORIGINAL_DEADLINE_EXPIRED')
        if time.monotonic() >= self.next_guard:
            loader.resource_check(self.work)
            self.next_guard = time.monotonic()+60
        b = self.state['binding']
        if signatures(Path(b['generation']), b['navigation_path']) != b['signatures']:
            raise Stop('VECTOR_SOURCE_CHANGED')

    def cache_path(self, number):
        return self.work/('embed-%08d.json' % number)

    def report(self):
        if self.total is None: return
        elapsed = time.monotonic()-self.started
        added = self.state['rows']-self.initial_rows
        rate = added/elapsed if elapsed >= 3 and added > 0 else None
        remaining = max(0,self.total-self.state['rows'])
        eta = remaining/rate if rate else (0 if remaining == 0 else None)
        self.progress.emit('VECTOR_PROGRESS',rows=self.state['rows'],total_rows=self.total,
                           rows_per_second=round(rate,2) if rate else None,
                           remaining_seconds=round(eta) if eta is not None else None,
                           run_seconds=round(elapsed),sdk_calls=self.state['embedding_calls'])

    def embed(self, number, items, project, config):
        self.guard()
        marker = {'batch': number, 'input': digest(items)}
        path = self.cache_path(number)
        pending = self.state['embedding_pending']
        if path.exists():
            cached = loader.read(path)
            if cached['input'] != marker['input'] or cached['sha256'] != digest(cached['vectors']):
                raise Stop('VECTOR_RESPONSE_CACHE_CONFLICT')
            if pending == marker:
                self.state['embedding_pending'] = None
                self.save()
            elif pending is not None and pending['batch'] <= number:
                raise Stop('VECTOR_EMBED_PENDING_CONFLICT')
            return cached['vectors']
        if pending is not None:
            if pending != marker:
                raise Stop('VECTOR_EMBED_PENDING_CONFLICT')
            raise Stop('EMBEDDING_OUTCOME_UNKNOWN_NO_AUTOMATIC_RETRY')
        if self.state['embedding_calls'] >= self.state['max_calls']:
            raise Stop('VECTOR_EMBEDDING_BUDGET_EXHAUSTED')
        self.state.update(embedding_pending=marker, status='EMBEDDING_IN_FLIGHT')
        self.state['embedding_calls'] += 1
        self.save()
        self.progress.set('VECTOR_EMBEDDING', rows=self.state['rows'], sdk_calls=self.state['embedding_calls'])
        vectors = encode(project, config, [i['text'] for i in items])
        loader.atomic(path, {'input': marker['input'], 'vectors': vectors, 'sha256': digest(vectors)})
        self.state.update(embedding_pending=None, status='EMBEDDING_CACHED')
        self.save()
        return vectors

    def write(self, key, rows, next_state, dimensions):
        self.guard()
        marker = {'key': key, 'sha256': digest(rows), 'rows': len(rows), 'next': next_state}
        pending = self.state['pending']
        if pending is not None:
            if pending != marker:
                raise Stop('VECTOR_PENDING_BATCH_BINDING_MISMATCH')
            self.state['pending_key_queries'] += 1
            self.save()
            present = self.contract.pending_count(self.db, key, rows)
            if present not in (0, len(rows)):
                raise Stop('VECTOR_PENDING_PARTIAL_KEYS_REVIEW_REQUIRED')
            if present == len(rows):
                self.ack(next_state)
                self.progress.emit('VECTOR_PENDING_KEYS_ACKNOWLEDGED', rows=len(rows))
                self.report()
                return
        self.state.update(pending=marker, status='WRITE_UNCONFIRMED')
        self.state['insert_requests'] += 1
        self.save()
        sql, binds = vector_sql(self.contract, rows, dimensions) if key == 'VCTR_ITEM' else self.contract.batch(key, rows)
        seconds = self.db.block(sql, binds, transaction_managed=True)
        self.ack(next_state)
        self.progress.emit('VECTOR_INSERT_ACK', table=self.contract.table(key), batch_rows=len(rows),
                           rows=self.state['rows'], sdk_calls=self.state['embedding_calls'], request_s=round(seconds,3),
                           payload_bytes=sum(len(value.encode()) for _,value,_ in binds if isinstance(value,str)))
        self.report()

    def ack(self, next_state):
        self.state.update(next_state)
        self.state['pending'] = None
        self.save()


def build(job, store, navigation, source, query, config, project, migration):
    manifest = job.state['binding']['manifest']
    publication = digest(manifest)
    allowed = set(manifest['documents'])
    number = job.state['next_batch']
    buffer, caches, size, chain, last_cursor = [], [], 0, job.state['chain'], job.state['cursor']
    def flush():
        nonlocal buffer, caches, size
        if not buffer:
            return
        nxt = {'rows': job.state['rows']+len(buffer), 'next_batch': caches[-1]+1,
               'cursor': last_cursor, 'chain': chain, 'status': 'LOADING'}
        job.write('VCTR_ITEM', buffer, nxt, config['dimensions'])
        for index in caches:
            job.cache_path(index).unlink(missing_ok=True)
        buffer, caches, size = [], [], 0
    def append(part):
        nonlocal number, buffer, size, chain, last_cursor
        check_coordinates(job.contract, part, allowed)
        vectors = job.embed(number, part, project, config)
        rows = rows_for(publication, part, vectors)
        n = len(canonical(rows).encode())
        if n > MAX_BYTES:
            raise Stop('VECTOR_SINGLE_EMBED_BATCH_TOO_LARGE')
        if buffer and (len(buffer)+len(rows)>MAX_ROWS or size+n>MAX_BYTES):
            flush()
        buffer.extend(rows); caches.append(number); size += n
        for item in part:
            chain = digest([chain, item['id'], item['meta']])
        last_cursor = part[-1]['cursor']
        number += 1
        if len(buffer) == MAX_ROWS:
            flush()
    items = []
    for item in segments(store, navigation, source['dataset_version'], migration, job.state['cursor'], plan=job.plan):
        items.append(item)
        if len(items) == 16:
            append(items); items = []
    if items:
        append(items)
    flush()
    job.guard()
    if job.state['rows'] == 0:
        raise Stop('VECTOR_EMPTY_CORPUS')
    if job.total is not None and job.state['rows'] != job.total:
        raise Stop('VECTOR_PLANNED_COUNT_MISMATCH')
    envelope = {'manifest': manifest, 'completion': {'status': 'READY', 'count': job.state['rows'],
                'chain': job.state['chain'], 'profile_sha256': digest(config),
                'integrity_mode': 'INSERT_ACK_ONLY', 'full_values_verified': False}}
    job.write('VCTR_POST', [{'VCTR_POST_ID': publication, 'VCTR_POST_IFMN_CTNT': canonical(envelope)}],
              {'status': COMPLETE, 'publication_id': publication, 'full_values_verified': False}, config['dimensions'])
    job.progress.emit(COMPLETE, rows=job.state['rows'], publication_id=publication, serving='NOT_SWITCHED')


def execute(old_job, action='vector'):
    if action not in {'check', 'vector'}:
        raise Stop('VECTOR_ACTION')
    from jdbc_transport import install
    from lawrag.pipeline import oracle_migration as migration
    import dataiku
    install(loader)
    code = loader.verify_code()
    config = settings()
    contract = Contract(loader.HERE/'contract.json')
    parent, directory, prior = select_parent(old_job, loader.HERE)
    progress = loader.Progress(); progress.thread.start()
    job = db = None
    try:
        with ExitStack() as stack:
            for folder in dict.fromkeys((parent, directory)):
                lock = stack.enter_context((folder/'job.lock').open('a'))
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            _, selected, current = select_parent(old_job, loader.HERE)
            if selected != directory or current != prior:
                raise Stop('VECTOR_PARENT_CHANGED')
            root, files, source, query, paths = inputs(loader, old_job, directory, prior, progress)
            if digest(source) != prior['binding']['source_release'] or digest(query) != prior['binding']['query_release']:
                raise Stop('VECTOR_INPUT_RELEASE_CHANGED')
            from fast_loader import ready
            if not ready(type('Parent', (), {'state': prior})(), source, query, paths):
                raise Stop('VECTOR_PARENT_LOAD_INCOMPLETE')
            db = loader.Database(dataiku.SQLExecutor2(connection='AIDP'))
            identity = db.query("SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER, SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME, SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME FROM DUAL")
            subset = Contract(loader.HERE/'contract.json')
            subset.tables = {k: subset.tables[k] for k in ('VCTR_ITEM', 'VCTR_POST', 'VCTR_HEAD')}
            target_names = {(v['owner'], v['name']) for v in subset.tables.values()}
            expected = [r for r in prior['binding']['objects'] if (r['OWNER'],r['OBJECT_NAME']) in target_names]
            if identity != prior['binding']['database'] or loader.object_binding(db, subset) != expected:
                raise Stop('VECTOR_DATABASE_OR_TABLES_CHANGED')
            navigation_path = source['source_manifest']['navigation']['path']+'/navigation.sqlite'
            if navigation_path not in files:
                raise Stop('VECTOR_NAVIGATION_NOT_IN_PARENT_MANIFEST')
            manifest = {'schema_version': 'gold-vector-manifest-preview-v1', 'query_id': digest(query),
                        'source_release_id': digest(source), 'dataset_version': source['dataset_version'],
                        'documents': sorted(source['source_manifest']['scope']['document_version_ids']),
                        'profile': config, 'segment_profile': POLICY}
            binding = {'code': code, 'parent_code': prior['binding']['code'], 'contract': contract.sha256,
                       'batch_policy': {'embed_rows':16, 'db_rows':MAX_ROWS, 'db_bytes':MAX_BYTES},
                       'generation': str(root), 'files': files, 'database': identity, 'objects': expected,
                       'manifest': manifest, 'navigation_path': navigation_path,
                       'signatures': signatures(root, navigation_path)}
            progress.emit('VECTOR_TARGET', model=config['model'], dimensions=config['dimensions'],
                          query_release=digest(query), checkpoint=str(directory), action=action,
                          segment_policy=POLICY, db_batch_rows=MAX_ROWS, db_batch_bytes=MAX_BYTES)
            if action == 'check':
                progress.emit('VECTOR_CHECK_PASS', model_calls=0, table_writes=0)
                return
            work = directory/'vectors-structure-r4'/digest(manifest)
            work.mkdir(parents=True, exist_ok=True)
            job = VectorJob(db, contract, work, binding, progress)
            from vector_upgrade import inherit_preparation
            inherit_preparation(job, directory, loader)
            if job.state['status'] == COMPLETE:
                progress.emit(COMPLETE, rows=job.state['rows'], repeated=True, model_calls=0, table_writes=0)
                return
            job.guard(); job.save()
            for cache in work.glob('embed-*.json'):
                if re.fullmatch(r'embed-\d{8}\.json', cache.name) and int(cache.stem[6:]) < job.state['next_batch']:
                    cache.unlink()
            store = migration.source_open(root/'store.sqlite'); stack.callback(store.close)
            navigation = migration.source_open(root/navigation_path); stack.callback(navigation.close)
            from vector_plan import prepare
            job.plan, plan_meta = prepare(job, store, navigation, source, migration)
            stack.callback(job.plan.close)
            job.total = plan_meta['rows']
            job.state['planned_total_rows'] = job.total
            job.save()
            from vector_reset import reset_previous
            reset_previous(job, directory, loader)
            job.started = time.monotonic()
            job.report()
            project = dataiku.api_client().get_default_project()
            build(job, store, navigation, source, query, config, project, migration)
    except BaseException as exc:
        if job is not None:
            job.state['last_error'] = {'type': type(exc).__name__, 'codes': error_codes(exc),
                                       'phase': progress.phase, 'time': time.time()}
            job.save()
        raise
    finally:
        if db is not None:
            db.close()
        progress.stop.set(); progress.thread.join(timeout=2)


if __name__ == '__main__':
    signal.signal(signal.SIGUSR1, request_stop)
    try:
        execute(Path(os.environ.get('G19_OLD_JOB_DIR') or loader.DEFAULT_OLD_JOB).resolve(strict=True),
                sys.argv[1] if len(sys.argv)>1 else 'vector')
    except BaseException as exc:
        from error_diagnostics import event, banner
        value = event(exc, {'stage': 'VECTOR_STRUCTURE_R4'})
        output = os.environ.get('G19_DIAGNOSTIC_FILE')
        if output:
            with open(output, 'a', encoding='utf-8') as stream:
                stream.write(canonical(value)+'\n'); stream.flush(); os.fsync(stream.fileno())
        print(canonical(value), flush=True); print(banner(value), flush=True)
        raise SystemExit(1)
