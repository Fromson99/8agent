"""Load immutable rows first; publish serving manifests only after explicit verification.

Load checkpoints acknowledge writes, never certify remote contents. Verification always
reads the source, assets and projected rows afresh; it never repairs missing rows.
"""
import base64
import hashlib
import time
import zlib

from semantic_runtime import oracle_dp_io as io, oracle_dp_assets as assets, oracle_query_catalog as q
from semantic_runtime.physical_mapping import names
from . import oracle_migration as migration, oracle_query_publish as query, oracle_query_package as transport


def prepared_descriptor(root, source, files, logs):
    """Reuse completed local preparation only; never certify Oracle contents."""
    from . import oracle_query_navigation_publish as nav
    from semantic_runtime import navigation_match, structure_navigation, inherited_navigation
    components = (query, transport, nav, navigation_match, structure_navigation, inherited_navigation)
    binding = {'source':io.digest(source), 'files':files,
               'components':{m.__name__:io.file_sha(m.__file__) for m in components},
               'executor':io.file_sha(__file__)}
    path = logs/'projection-descriptor-r7.json'
    if path.exists():
        saved = transport.bounded_json(path)
        body = {k:v for k,v in saved.items() if k != 'checksum'}
        if saved.get('checksum') != io.digest(body):
            raise io.DPError('PROJECTION_DESCRIPTOR_CHECKSUM')
        if body.get('binding') == binding:
            print('PROJECTION_PREPARATION_REUSED: 완료된 로컬 준비 계산 재사용', flush=True)
            return body['paths'], body['tables']
        # Preserve the previous descriptor, including its failure/debug lineage.
        old = path.with_name('projection-descriptor-r7-'+io.file_sha(path)+'.json')
        if not old.exists():
            old.write_bytes(path.read_bytes())
    _, paths, tables = query.describe(root, source)
    body = {'binding':binding, 'paths':paths, 'tables':tables}
    io.atomic_json(path, dict(body, checksum=io.digest(body)))
    return paths, tables


def put_staged_part(sql, item, number, raw):
    """Idempotent write + transaction-local conflict check; no client body readback."""
    p = names(sql, 'asset_part', assets.PART_TABLE)
    columns = ','.join(p.c(c) for c in ('ASSET_SHA256','PART_NO','RAW_BYTES','PART_SHA256','DATA_B64'))
    key = f'{p.c("ASSET_SHA256")}=:a AND {p.c("PART_NO")}=:p'
    statement = (f'DECLARE n NUMBER; BEGIN SELECT COUNT(*) INTO n FROM {p.table} WHERE {key}; '
        f'IF n=0 THEN INSERT INTO {p.table} ({columns}) VALUES (:a,:p,:n,:s,:body); END IF; '
        f'SELECT COUNT(*) INTO n FROM {p.table} WHERE {key} AND {p.c("RAW_BYTES")}=:n '
        f'AND {p.c("PART_SHA256")}=:s AND DBMS_LOB.COMPARE({p.c("DATA_B64")},:body)=0; '
        "IF n<>1 THEN RAISE_APPLICATION_ERROR(-20002,'DP_ASSET_VERIFY'); END IF; "
        'COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
    sql.request(statement, [('a',item['sha256'],'VARCHAR2'),('p',number,'NUMBER'),
        ('n',len(raw),'NUMBER'),('s',hashlib.sha256(raw).hexdigest(),'VARCHAR2'),
        ('body',base64.b64encode(zlib.compress(raw,6)).decode(),'CLOB')], write=True)


def batches(root, paths, source):
    for relative, expected_sha in paths.items():
        path = assets.checked_path(root, relative)
        if io.file_sha(path) != expected_sha: raise io.DPError('QUERY_SOURCE_CHANGED')
        batch, size = [], 0
        for row in query.projected_rows(path, relative, source):
            n = len(q.json_body(row))
            if batch and (len(batch) == 20 or size+n > 4*1024**2):
                yield relative, batch
                batch, size = [], 0
            batch.append(row); size += n
        if batch: yield relative, batch
        if io.file_sha(path) != expected_sha: raise io.DPError('QUERY_SOURCE_CHANGED')


def put_query_release(sql, release_id, value):
    p = names(sql, 'query_release', q.RELEASE)
    existing = sql.query(f'SELECT {p.select("RELEASE_ID")} FROM {p.table} WHERE {p.c("RELEASE_ID")}=:release',
                         [('release',release_id,'VARCHAR2')], limit=1)
    if not existing:
        statement = (f'DECLARE n NUMBER; BEGIN SELECT COUNT(*) INTO n FROM {p.table} WHERE {p.c("RELEASE_ID")}=:release; '
            f'IF n=0 THEN INSERT INTO {p.table} ({p.c("RELEASE_ID")},{p.c("MANIFEST_JSON")}) VALUES(:release,:body); END IF; '
            f'SELECT COUNT(*) INTO n FROM {p.table} WHERE {p.c("RELEASE_ID")}=:release '
            f'AND DBMS_LOB.COMPARE({p.c("MANIFEST_JSON")},:body)=0; '
            "IF n<>1 THEN RAISE_APPLICATION_ERROR(-20032,'QUERY_RELEASE_CONFLICT'); END IF; "
            'COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
        sql.request(statement, [('release',release_id,'VARCHAR2'),('body',q.json_body(value),'CLOB')], write=True)
    if q.read_release(sql, release_id) != value: raise io.DPError('QUERY_RELEASE_READBACK')


def execute(client, *, root, folder, info, state, receipt, logs, target_binding,
            action, remaining, stage, sql, schema):
    from .oracle_full_package import immutable_inputs, verify_restored
    publisher = io.file_sha(query.__file__)
    if state.get('deferred') and state.get('query_projection_publisher') != publisher:
        raise io.DPError('DEFERRED_BINDING: existing query plan requires review before R7 preparation')
    root, manifest, items, files, selected = immutable_inputs(root)
    remaining()
    print('PREPARING_LOCAL_PROJECTION: 기존 구조화 자료의 게시 명세 계산', flush=True)
    expected_source = transport.offline_source(root, manifest, items, selected, remaining)
    paths, tables = prepared_descriptor(root, expected_source, files, logs)
    expected_query = transport.query_manifest(root, expected_source, paths, tables, items)
    sid, rid = io.digest(expected_source), io.digest(expected_query)
    plan = {'source_release_id':sid, 'query_release_id':rid, 'files':files}
    deferred = state.setdefault('deferred', {'plan':plan, 'loaded_parts':{}, 'loaded_query_batches':0})
    if deferred['plan'] != plan:
        raise io.DPError('DEFERRED_BINDING: immutable plan changed; preserve previous query release and receipt')
    state['query_projection_publisher'] = publisher
    def save(): io.atomic_json(receipt, state)
    save()

    if action in {'load_only', 'publish'}:
        def source_load():
            return migration.transfer(client, root/'store.sqlite', target_binding=target_binding,
                directory=logs/'source', action='stage', seconds=remaining())
        # Existing completed source cursors skip the entire body reread. Counts and
        # source/target binding are still checked, including an unfinished write.
        stage('source_load', source_load)
        if not deferred.get('load_finished'):
            state['status'] = 'LOADING_UNVERIFIED'; save()
            write = sql('deferred_load')
            for item in items:
                remaining()
                path = assets.checked_path(root, item['path'])
                start = deferred['loaded_parts'].get(item['path'], 0)
                if type(start) is not int or not 0 <= start <= item['parts']:
                    raise io.DPError('DEFERRED_PART_CURSOR')
                with path.open('rb') as f:
                    f.seek(start*assets.PART_BYTES)
                    for number in range(start, item['parts']):
                        raw = f.read(assets.PART_BYTES)
                        if len(raw) != min(assets.PART_BYTES,item['bytes']-number*assets.PART_BYTES):
                            raise io.DPError('ASSET_CHANGED')
                        put_staged_part(write, item, number, raw)
                        deferred['loaded_parts'][item['path']] = number+1; save()
                if io.file_sha(path) != item['sha256']: raise io.DPError('ASSET_CHANGED')
            done = deferred['loaded_query_batches']
            if type(done) is not int or done < 0: raise io.DPError('DEFERRED_QUERY_CURSOR')
            seen = 0
            for relative, batch in batches(root, paths, expected_source):
                remaining(); seen += 1
                if seen <= done: continue
                q.insert_records(write, rid, batch)
                deferred['loaded_query_batches'] = seen; save()
                if seen == 1 or seen % 100 == 0:
                    print(f'QUERY_LOADED batches={seen}; asset={relative}; full_verification=pending', flush=True)
            if seen < done: raise io.DPError('DEFERRED_QUERY_CURSOR')
            verify_restored(folder)
            deferred['load_finished'] = True
        result = {'status':'LOADED_UNVERIFIED', 'source_release_id':sid, 'query_release_id':rid,
            'source_counts':info['source_counts'], 'asset_files':len(items),
            'verification_pending':True, 'serving_manifests_written':False,
            'active_changed':False, 'serving_switched':False}
        state.update(status='LOADED_UNVERIFIED', result=result); save()
        if action == 'load_only': return result

    if not deferred.get('load_finished'):
        raise io.DPError('LOAD_FIRST: run load_only; verify never inserts missing data')
    state['status'] = 'VERIFYING'; save()
    # This is the only full source validation in this invocation, even after load.
    verified = stage('verify', lambda: migration.transfer(client, root/'store.sqlite',
        target_binding=target_binding, directory=logs/'source', action='verify', seconds=remaining()))
    read = sql('deferred_verify')
    for item in items:
        remaining(); h = hashlib.sha256(); size = 0
        for number in range(item['parts']):
            raw = assets.get_part(read, item['sha256'], number)
            if raw is None: raise io.DPError('ASSET_MISSING')
            h.update(raw); size += len(raw)
        if h.hexdigest() != item['sha256'] or size != item['bytes']: raise io.DPError('ASSET_READBACK')
    total = 0
    for relative, batch in batches(root, paths, expected_source):
        remaining(); query._verify_batch(read, rid, batch); total += len(batch)
        if total == len(batch) or total % 2000 == 0:
            print(f'QUERY_VERIFIED rows={total}; asset={relative}', flush=True)
    p = names(read, 'query_row', q.ROW)
    count = read.query(f'SELECT COUNT(*) AS N FROM {p.table} WHERE {p.c("RELEASE_ID")}=:release',
                      [('release',rid,'VARCHAR2')], limit=1)
    if count != [{'N':total}]: raise io.DPError('QUERY_TOTAL_COUNT')
    verify_restored(folder)
    # No COMPLETE release is written until all remote content checks have passed.
    # Idempotent release writes allow explicit recovery if a commit ACK is lost.
    assets.put_release(read, expected_source)
    put_query_release(read, rid, expected_query)
    state['stages'].update(source=state['stages']['source_load'],
        assets={'status':'COMPLETE','release_id':sid}, query={'status':'COMPLETE','release_id':rid})
    deferred['verified_at'] = time.time()
    result = {'status':'FULL_DATA_VERIFIED', 'source_release_id':sid, 'query_release_id':rid,
        'source_counts':info['source_counts'], 'asset_files':len(items), 'query_rows':total,
        'deferred_indexes':schema['deferred_indexes'], 'active_changed':False,
        'state_migrated':False, 'serving_switched':False}
    state.update(status='COMPLETE', result=result); save()
    return result
