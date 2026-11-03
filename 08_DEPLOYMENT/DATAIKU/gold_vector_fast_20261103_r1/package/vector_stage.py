"""R6/R7 vector INSERT/COMMIT. Only uncertain writes check their primary keys."""
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import run_full as loader
from fast_insert import Contract
from fast_inputs import inputs
from gold_io import Stop, canonical, digest, error_codes
from mesh_embedding import settings, encode

MAX_ROWS = 128
MAX_BYTES = 2 * 1024**2
COMPLETE = 'VECTORS_STORED_INSERT_ACK_NOT_ACTIVATED'


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


def segments(store, navigation, version, migration, cursor=None):
    """Use the reader's actual source IDs and resume its block/window directly."""
    from semantic_runtime.oracle_dp_io import COLUMNS
    after = cursor['source_id'] if cursor else None
    inclusive = bool(cursor)
    while True:
        where = (' WHERE id '+('>=' if inclusive else '>')+' ?') if after is not None else ''
        rows = navigation.execute('SELECT id,json FROM source'+where+' ORDER BY id LIMIT 16',
                                  (after,) if after is not None else ()).fetchall()
        if not rows:
            return
        if inclusive and rows[0][0] != after:
            raise Stop('VECTOR_RESUME_SOURCE_MISSING')
        for sid, raw in rows:
            source = json.loads(raw)
            if source['id'] != sid:
                raise Stop('VECTOR_SOURCE_ID_MISMATCH')
            blocks = source['blocks']
            current = cursor if cursor and cursor['source_id'] == sid else None
            first_block = current['block_index'] if current else 0
            if first_block > len(blocks):
                raise Stop('VECTOR_RESUME_BLOCK_MISSING')
            source_hash = digest(source)
            for off in range(first_block, len(blocks), 100):
                ids = [str(b['block_id']) for b in blocks[off:off+100]]
                fetched = store.execute('SELECT * FROM block_payload WHERE document_id=? AND block_id IN ('+
                                       ','.join('?' for _ in ids)+')', (source['document_id'], *ids)).fetchall()
                records = {str(r['block_id']): r for r in fetched}
                if len(records) != len(ids):
                    raise Stop('VECTOR_SOURCE_BLOCK_MISSING_OR_DUPLICATE')
                for index, bid in enumerate(ids, off):
                    record = records[bid]
                    row = {c: version if c == 'DATASET_VERSION' else record['json' if c == 'SOURCE_JSON' else c.lower()]
                           for c in COLUMNS['block_payload']}
                    migration.validate_row('block_payload', row)
                    body = row['TEXT']
                    body_hash = hashlib.sha256(body.encode()).hexdigest()
                    start_at = current['next_start'] if current and index == first_block else 0
                    for start in range(start_at, len(body), 700):
                        text = body[start:start+800]
                        last = start+800 >= len(body)
                        if text.strip():
                            meta = {'document_id': source['document_id'], 'source_id': sid,
                                    'unit_id': source['unit_id'], 'block_id': bid, 'start': start,
                                    'end': start+len(text), 'source_sha256': source_hash,
                                    'block_sha256': body_hash, 'input_sha256': hashlib.sha256(text.encode()).hexdigest()}
                            yield {'id': digest([version, meta]), 'meta': meta, 'text': text,
                                   'cursor': {'source_id': sid, 'block_index': index+1 if last else index,
                                              'next_start': 0 if last else start+700}}
                        if last:
                            break
        after = rows[-1][0]
        inclusive = False


def rows_for(publication, items, vectors):
    return [{'VCTR_POST_ID': publication, 'VCTR_SEG_ID': i['id'], 'DOC_ID': i['meta']['document_id'],
             'SRC_UNIT_ID': i['meta']['source_id'], 'VCTR_META_CTNT': canonical(i['meta']),
             'EMBD_VCTR_VALU': canonical(v)} for i, v in zip(items, vectors, strict=True)]


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

    def save(self):
        loader.atomic(self.path, self.state)

    def guard(self):
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
                return
        self.state.update(pending=marker, status='WRITE_UNCONFIRMED')
        self.state['insert_requests'] += 1
        self.save()
        sql, binds = vector_sql(self.contract, rows, dimensions) if key == 'VCTR_ITEM' else self.contract.batch(key, rows)
        seconds = self.db.block(sql, binds, transaction_managed=True)
        self.ack(next_state)
        self.progress.emit('VECTOR_INSERT_ACK', table=self.contract.table(key), batch_rows=len(rows),
                           rows=self.state['rows'], sdk_calls=self.state['embedding_calls'], request_s=round(seconds,3))

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
    for item in segments(store, navigation, source['dataset_version'], migration, job.state['cursor']):
        items.append(item)
        if len(items) == 16:
            append(items); items = []
    if items:
        append(items)
    flush()
    job.guard()
    if job.state['rows'] == 0:
        raise Stop('VECTOR_EMPTY_CORPUS')
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
            subset.tables = {k: subset.tables[k] for k in ('VCTR_ITEM', 'VCTR_POST')}
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
                        'profile': config, 'segment_profile': 'navigation-source-block-text-window800-step700-v1'}
            binding = {'code': code, 'parent_code': prior['binding']['code'], 'contract': contract.sha256,
                       'generation': str(root), 'files': files, 'database': identity, 'objects': expected,
                       'manifest': manifest, 'navigation_path': navigation_path,
                       'signatures': signatures(root, navigation_path)}
            progress.emit('VECTOR_TARGET', model=config['model'], dimensions=config['dimensions'],
                          query_release=digest(query), checkpoint=str(directory), action=action)
            if action == 'check':
                progress.emit('VECTOR_CHECK_PASS', model_calls=0, table_writes=0)
                return
            work = directory/'vectors-fast-r1'/digest(manifest)
            work.mkdir(parents=True, exist_ok=True)
            job = VectorJob(db, contract, work, binding, progress)
            if job.state['status'] == COMPLETE:
                progress.emit(COMPLETE, rows=job.state['rows'], repeated=True, model_calls=0, table_writes=0)
                return
            job.guard(); job.save()
            for cache in work.glob('embed-*.json'):
                if re.fullmatch(r'embed-\d{8}\.json', cache.name) and int(cache.stem[6:]) < job.state['next_batch']:
                    cache.unlink()
            store = migration.source_open(root/'store.sqlite'); stack.callback(store.close)
            navigation = migration.source_open(root/navigation_path); stack.callback(navigation.close)
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
    try:
        execute(Path(os.environ.get('G19_OLD_JOB_DIR') or loader.DEFAULT_OLD_JOB).resolve(strict=True),
                sys.argv[1] if len(sys.argv)>1 else 'vector')
    except BaseException as exc:
        from error_diagnostics import event, banner
        value = event(exc, {'stage': 'VECTOR_FAST_R1'})
        output = os.environ.get('G19_DIAGNOSTIC_FILE')
        if output:
            with open(output, 'a', encoding='utf-8') as stream:
                stream.write(canonical(value)+'\n'); stream.flush(); os.fsync(stream.fileno())
        print(canonical(value), flush=True); print(banner(value), flush=True)
        raise SystemExit(1)
