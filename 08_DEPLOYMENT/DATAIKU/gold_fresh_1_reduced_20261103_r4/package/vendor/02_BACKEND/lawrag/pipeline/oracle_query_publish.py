"""Dataiku-side projection of verified assets into SQL-queryable Oracle rows.

Local generation files are read only by the publisher, never by code-serving.
No original/legacy asset rows are deleted or updated. Activation is a separate
CAS operation after publication, enabling a scheduled batch to keep the prior
release active on any failure.
"""
from __future__ import annotations

from collections import defaultdict
import base64
from .oracle_transfer_progress import report, sqlite_work
import json
from pathlib import Path
import re
import sqlite3
import time

from semantic_runtime.oracle_dp_io import DPError, SQL, atomic_json, digest, file_sha
from semantic_runtime.oracle_dp_assets import get_release, inventory, checked_path
from semantic_runtime.physical_mapping import names
from semantic_runtime.oracle_query_catalog import (
    SCHEMA, RELEASE, ROW, DDL, record, insert_records, json_body, read_release, activate,
    LOOKUP_ENCODING, lookup_key,
)


def source_records(path, source_release):
    """Publish row digests, not a duplicate source body, for selective verification."""
    from .oracle_migration import source_open, source_batch, extend_chain
    from semantic_runtime.oracle_dp_io import KEYS, TABLES
    version = source_release['dataset_version']
    db = source_open(path)
    try:
        for kind in TABLES:
            cursor, count, chain = None, 0, '0'*64
            columns={'DATASET_VERSION':None,'DOCUMENT_ID':'document_id','UNIT_ID':'unit_id','PARENT_ID':'parent_id',
                     'NAME':'name','SOURCE_ARTIFACT_SHA256':'source_artifact_sha256','SOURCE_JSON':'json',
                     'BLOCK_ID':'block_id','TEXT':'text','JSON_TEXT_ELIDED':None}
            from semantic_runtime.oracle_dp_io import COLUMNS
            shape={'table':'source_block' if kind=='block_payload' else kind,
                   'columns':{columns[c]:{'type':'null','max_bytes':0,'has_null':False,'has_empty':False}
                              for c in COLUMNS[kind] if columns[c]},
                   'primary_key':[columns[c] for c in KEYS[kind] if columns[c]],'rows':0}
            while batch := source_batch(db, kind, version, cursor):
                for row in batch:
                    logical={columns[c]:v for c,v in row.items() if columns[c]}
                    if kind=='block_payload' and row['JSON_TEXT_ELIDED']:
                        body=json.loads(logical['json']);body['text']=row['TEXT']
                        logical['json']=json.dumps(body,ensure_ascii=False,separators=(',',':'))
                    _column_shapes(shape,logical)
                    if kind=='block_payload':
                        from semantic_runtime.folder_navigation import normalized
                        yield record('native.block_literal',{'text':normalized(row['TEXT'] or '')},
                                     key=[row['DOCUMENT_ID'],row['BLOCK_ID']],document_id=row['DOCUMENT_ID'],owner_id=str(row['BLOCK_ID']))
                    key = [row[c] for c in KEYS[kind]]
                    value = {'source_kind': kind, 'source_key': key, 'source_sha256': digest(row)}
                    yield record('source.integrity', value, key=[kind,key],
                                 document_id=row['DOCUMENT_ID'], lookup_id=digest([kind,key]), owner_id=kind)
                count += len(batch)
                chain = extend_chain(chain, batch)
                cursor = [batch[-1][c] for c in KEYS[kind] if c != 'DATASET_VERSION']
            if source_release['source_rows'][kind] != {'rows': count, 'chain': chain}:
                raise DPError('QUERY_SOURCE_CHAIN: original source differs from completed transfer')
            shape['rows']=count
            yield record('source.schema',shape,key=kind,lookup_id=shape['table'],owner_id=kind)
    finally:
        db.close()


def projected_rows(path, relative, source_release, *, excluded_tables=()):
    report('SOURCE_ROWS' if relative=='store.sqlite' else 'ASSET_ROWS',asset=relative)
    if relative == 'store.sqlite' and excluded_tables:
        raise DPError('QUERY_SOURCE_EXCLUSION_FORBIDDEN')
    yield from (source_records(path, source_release) if relative == 'store.sqlite' else asset_rows(path, relative, excluded_tables=excluded_tables))
    from .oracle_query_navigation_publish import records
    report('NATIVE_NAVIGATION',asset=relative)
    yield from records(path,relative,source_release)


def _name(value):
    if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', value):
        raise DPError('QUERY_EXPORT_SCHEMA: unsupported SQLite identifier')
    return '"'+value+'"'


def _kind(path, table):
    # Stable short namespace; the manifest maps it back to its exact asset path.
    return 'asset_'+digest(path)[:12]+'.'+table.lower()


def _lookups(value):
    def first(*names):
        for name in names:
            result = value.get(name)
            if result is not None and str(result):
                return str(result)
        return None
    return dict(document_id=first('document_id'), lookup_id=lookup_key(first('id','key','term_id','node_id')),
                owner_id=lookup_key(first('source_id','reference_id','definition_id')),
                target_id=lookup_key(first('target_id','target','parent_id')))


def asset_schema(path, relative):
    """Declare empty tables too; readers must not discover a different schema."""
    db = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        entries = list(db.execute("SELECT name,type,sql FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"))
        virtual = {name for name,_,sql in entries if 'CREATE VIRTUAL TABLE' in (sql or '').upper()}
        result = {}
        for name,typ,_ in entries:
            if name.startswith('sqlite_') or name in virtual or any(name.startswith(v+'_') for v in virtual):
                continue
            columns = list(db.execute('PRAGMA table_info('+_name(name)+')'))
            result[_kind(relative,name)] = {'asset':relative,'table':name,'storage':typ,'rows':0,'chain':'0'*64,
                'lookup_encoding':LOOKUP_ENCODING,
                'columns':{r[1]:{'type':'null','max_bytes':0,'has_null':False,'has_empty':False} for r in columns},
                'primary_key':[r[1] for r in sorted(columns,key=lambda r:r[5]) if r[5]]}
            if name == 'source_request' and 'response' in result[_kind(relative,name)]['columns']:
                result[_kind(relative,name)]['columns']['response'].update(
                    source_storage='blob', transport_encoding='base64-v1')
        return result
    finally:
        db.close()


def _column_shapes(state, value):
    """The publisher infers bounded SQL types without silently truncating text."""
    if 'columns' not in state:
        return  # Special integrity and FTS posting ports have their own contracts.
    if set(value) != set(state['columns']):
        raise DPError('QUERY_EXPORT_SCHEMA: logical row columns changed')
    for column,v in value.items():
        spec=state['columns'][column]
        if v is None:
            spec['has_null']=True
            continue
        typ='integer' if type(v) is int else 'real' if type(v) is float else 'text' if isinstance(v,str) else None
        if typ is None:
            raise DPError('QUERY_EXPORT_SCHEMA: unsupported logical scalar')
        if spec['type'] not in ('null',typ):
            if {spec['type'],typ} <= {'integer','real'}:
                typ='real'
            else:
                raise DPError('QUERY_EXPORT_SCHEMA: mixed SQLite storage classes require an explicit projection')
        spec['type']=typ
        if isinstance(v,str):
            spec['max_bytes']=max(spec['max_bytes'],len(v.encode()))
            spec['has_empty'] = spec['has_empty'] or v==''
            if column=='json' and v:
                _json_shapes(spec.setdefault('json_paths',{}),json.loads(v))


def _json_shapes(paths,value,path='$'):
    typ=('null' if value is None else 'boolean' if type(value) is bool else 'integer' if type(value) is int else
         'real' if type(value) is float else 'text' if isinstance(value,str) else 'object' if isinstance(value,dict) else 'array')
    spec=paths.setdefault(path,{'types':[],'max_bytes':0})
    if typ not in spec['types']:
        spec['types']=sorted([*spec['types'],typ])
    if isinstance(value,str):
        spec['max_bytes']=max(spec['max_bytes'],len(value.encode()))
    if isinstance(value,dict) and path.count('.')<8:
        for key,child in value.items():
            if re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',key):
                _json_shapes(paths,child,path+'.'+key)


def asset_metadata(generation, assets):
    """Small verified descriptors; source-ID catalogues stay in Oracle rows."""
    result={}
    for asset in assets:
        if not asset['path'].endswith('.json'):
            continue
        path=checked_path(generation,asset['path'])
        if file_sha(path)!=asset['sha256']:
            raise DPError('QUERY_SOURCE_CHANGED: metadata file changed')
        value=json.loads(path.read_text())
        if isinstance(value.get('scope'),dict) and 'source_ids' in value['scope']:
            value['scope']={**value['scope'],'source_count':len(value['scope']['source_ids'])}
            del value['scope']['source_ids']
        result[asset['path']]={'sha256':asset['sha256'],'value':value}
    return result


def selection_proof(generation,manifest):
    from semantic_runtime.search_selection import Selection
    from .oracle_migration import source_open
    selector=Selection(generation,manifest)
    db=source_open(Path(generation)/'store.sqlite')
    try:
        selector.verify_documents(db)
    finally:
        db.close()
    return {'fingerprint':selector.fingerprint,'native_latest_verified':selector.native_latest_verified}


def asset_rows(path, relative, *, excluded_tables=()):
    """Stream logical rows; scan FTS vocabulary once for document lengths."""
    db = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA cache_size=-16384');db.execute('PRAGMA temp_store=FILE')
        with sqlite_work(db):
            yield from _asset_rows(db, relative, excluded_tables=excluded_tables)
    finally:db.close()


def _asset_rows(db, relative, *, excluded_tables=()):
    entries = list(db.execute("SELECT name,type,sql FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"))
    virtual = {r['name'] for r in entries if 'CREATE VIRTUAL TABLE' in (r['sql'] or '').upper()}
    # FTS virtual rows/shadows are represented by token positions below.
    shadow = {r['name'] for r in entries if any(r['name'].startswith(v+'_') for v in virtual)}
    for entry in entries:
        table = entry['name']
        if table.startswith('sqlite_') or table in virtual or table in shadow or table in excluded_tables:
            continue
        columns = [r[1] for r in db.execute('PRAGMA table_info('+_name(table)+')')]
        if not columns:
            raise DPError('QUERY_EXPORT_SCHEMA: table has no columns')
        # Immutable file bytes determine row enumeration. Include all values
        # in row identity for views lacking a primary key.
        report('TABLE_SCAN',asset=relative,table=table)
        rows = db.execute('SELECT '+','.join(_name(c) for c in columns)+' FROM '+_name(table))
        for ordinal, row in enumerate(rows):
            value = dict(row)
            # The glossary retains compressed collection responses as evidence.
            # Encode the exact bytes, never decompress, discard or stringify them.
            # This column is explicitly marked in the query schema; text/NULL and
            # every other logical row keep their existing representation.
            if table == 'source_request' and 'response' in value:
                response = value['response']
                if response is not None and not isinstance(response, bytes):
                    raise DPError('QUERY_EXPORT_BINARY_TYPE: source_request.response must be BLOB or NULL')
                if response is not None:
                    value['response'] = base64.b64encode(response).decode('ascii')
            if any(isinstance(v, bytes) for v in value.values()):
                raise DPError('QUERY_EXPORT_BLOB: binary table needs an explicit projection: '+table)
            try:
                yield record(_kind(relative, table), value, key=[ordinal, value], **_lookups(value))
            except DPError as exc:
                if not str(exc).startswith('QUERY_RECORD_KEY:'):
                    raise
                raise DPError(f'{exc}; asset={relative} table={table} ordinal={ordinal}') from exc
    for table in sorted(virtual):
        declaration = next(r['sql'] for r in entries if r['name'] == table)
        if not re.search(r'USING\s+fts5\s*\(', declaration, re.I):
            raise DPError('QUERY_EXPORT_VIRTUAL: unsupported virtual table')
        db.execute('DROP TABLE IF EXISTS temp.query_export_vocab')
        db.execute('CREATE VIRTUAL TABLE temp.query_export_vocab USING fts5vocab(main,'+_name(table)+',instance)')
        first = db.execute('PRAGMA table_info('+_name(table)+')').fetchone()[1]
        unit_index = table == 'unit_fts' and first == 'key'
        logical_field='f.'+_name(first) if unit_index else 'CAST(f.rowid AS TEXT)'
        owner_join = ' LEFT JOIN unit u ON u.key=f.key' if unit_index else ''
        owner_fields = 'u.document_id,u.source_id' if unit_index else 'NULL AS document_id,NULL AS source_id'
        count = db.execute('SELECT COUNT(*) FROM '+_name(table)).fetchone()[0]
        report('FTS_LENGTH_AGGREGATE',asset=relative,table=table)
        db.execute('DROP TABLE IF EXISTS temp.query_export_lengths')
        db.execute('CREATE TEMP TABLE query_export_lengths(doc INTEGER PRIMARY KEY,n INTEGER NOT NULL,tokens INTEGER NOT NULL)')
        # fts5vocab indexes terms, not doc. Joining it separately for every
        # document scans all occurrences repeatedly. Materialize compact counts
        # once, then use the INTEGER PRIMARY KEY for each document lookup.
        db.execute('INSERT INTO temp.query_export_lengths SELECT doc,COUNT(offset),COUNT(*) FROM temp.query_export_vocab GROUP BY doc')
        tokens = db.execute('SELECT COALESCE(SUM(tokens),0) FROM temp.query_export_lengths').fetchone()[0]
        yield record(_kind(relative,table+'_stats'),{'documents':count,'tokens':tokens},key='stats',lookup_id='stats')
        report('FTS_LENGTH_ROWS',asset=relative,table=table)
        lengths = db.execute('SELECT f.rowid,'+logical_field+' AS logical_id,'+owner_fields+',COALESCE(SUM(v.n),0) AS n '
            'FROM '+_name(table)+' f'+owner_join+' LEFT JOIN temp.query_export_lengths v ON v.doc=f.rowid '
            'GROUP BY f.rowid,f.'+_name(first)+(','+owner_fields if unit_index else '')+' ORDER BY f.rowid')
        for row in lengths:
            value = {'key':str(row['logical_id']),'document_id':row['document_id'],
                     'source_id':row['source_id'],'length':row['n']}
            yield record(_kind(relative,table+'_length'),value,key=row['rowid'],lookup_id=str(row['logical_id']),
                         document_id=row['document_id'],owner_id=row['source_id'])
        if table=='words' and any(r['name']=='label' for r in entries):
            for row in db.execute('SELECT rowid AS fts_row_id,source,node_id FROM label ORDER BY rowid'):
                yield record(_kind(relative,table+'_content'),dict(row),key=row['fts_row_id'],lookup_id=str(row['fts_row_id']))
        # Preserve the existing tokenizer's actual positions, including
        # repeated terms and phrases. Do not retokenize with another model.
        report('FTS_POSTINGS_SORT',asset=relative,table=table)
        # Sort token positions only. Repeated logical/document/source identifiers
        # used to be carried through the sorter for every token occurrence.
        # Attach identical metadata once per doc after sorting; one doc in RAM.
        stream = db.execute('SELECT doc,col,term,offset FROM temp.query_export_vocab '
                            'ORDER BY doc,col,term,offset')
        current_doc, metadata = object(), None
        previous, positions = None, []
        def posting(key, offsets):
            doc, column, token, logical_id, did, sid = key
            value = {'key': str(logical_id), 'column': column, 'token': token,
                     'positions': offsets, 'tf': len(offsets)}
            return record(_kind(relative, table+'_posting'), value, key=[doc,column,token],
                          document_id=did,lookup_id=token, owner_id=str(logical_id), target_id=column)
        for row in stream:
            if row['doc'] != current_doc:
                current_doc = row['doc']
                metadata = db.execute('SELECT '+logical_field+' AS logical_id,'+owner_fields+
                    ' FROM '+_name(table)+' f'+owner_join+' WHERE f.rowid=?', (current_doc,)).fetchone()
            # Match the former inner join for a malformed/missing content row.
            if metadata is None:
                continue
            key = (row['doc'], row['col'], row['term'], metadata['logical_id'],metadata['document_id'],metadata['source_id'])
            if previous is not None and key != previous:
                yield posting(previous, positions)
                positions = []
            previous = key
            positions.append(row['offset'])
        if previous is not None:
            yield posting(previous, positions)


def describe(generation, source_release):
    generation = Path(generation).resolve()
    manifest, assets = inventory(generation)
    if (manifest != source_release['source_manifest'] or
            file_sha(generation/'manifest.json') != source_release['dataset_version']):
        raise DPError('QUERY_SOURCE_BINDING: publisher generation differs from Oracle source release')
    selected = [{'path':'store.sqlite', 'sha256':manifest['store_sha256']},
                *[a for a in assets if a['path'].endswith('.sqlite')]]
    tables, paths = {}, {}
    for asset_index, asset in enumerate(selected,1):
        report('DESCRIBE_ASSET',asset=asset['path'],asset_index=asset_index,
               asset_total=len(selected),rows_prepared=0)
        path = checked_path(generation, asset['path'])
        if file_sha(path) != asset['sha256']:
            raise DPError('QUERY_SOURCE_CHANGED: input digest differs from source release')
        paths[asset['path']] = asset['sha256']
        if asset['path'] != 'store.sqlite':
            tables.update(asset_schema(path,asset['path']))
        prepared_rows=0
        for row in projected_rows(path, asset['path'], source_release):
            state = tables.setdefault(row['kind'], {'asset': asset['path'], 'rows': 0, 'chain': '0'*64})
            state['rows'] += 1
            state['chain'] = digest([state['chain'], row['row_id'], row['sha256']])
            _column_shapes(state,row['value'])
            prepared_rows+=1
            if prepared_rows%1000==0:report(rows_prepared=prepared_rows)
        report(rows_prepared=prepared_rows)
        if file_sha(path) != asset['sha256']:
            raise DPError('QUERY_SOURCE_CHANGED: asset changed during projection')
    return manifest, paths, tables


def _verify_batch(sql, release_id, batch):
    """Read back the full indexed envelope, not just an untrusted checksum."""
    from semantic_runtime.oracle_dp_assets import clob_text
    from semantic_runtime.physical_mapping import names
    p=names(sql,'query_row',ROW)
    binds = [('release', release_id, 'VARCHAR2')]
    predicates = []
    for i, row in enumerate(batch):
        predicates.append(f'({p.c("KIND") }=:kind{i} AND {p.c("ROW_ID") }=:id{i})')
        binds += [(f'kind{i}',row['kind'],'VARCHAR2'),(f'id{i}',row['row_id'],'VARCHAR2')]
    result = sql.query(f'SELECT {p.select("KIND","ROW_ID","DOCUMENT_ID","LOOKUP_ID","OWNER_ID","TARGET_ID","ROW_SHA256")},TO_CLOB({p.c("VALUE_JSON")}) AS VALUE,'
                       f'DBMS_LOB.GETLENGTH({p.c("VALUE_JSON")}) AS N FROM {p.table} WHERE {p.c("RELEASE_ID") }=:release AND ('+
                       ' OR '.join(predicates)+')', binds, limit=len(batch))
    actual = {(r['KIND'],r['ROW_ID']): r for r in result}
    if len(actual) != len(result) or set(actual) != {(r['kind'],r['row_id']) for r in batch}:
        raise DPError('QUERY_READBACK: stored row set differs')
    for row in batch:
        stored = actual[(row['kind'],row['row_id'])]
        body = stored['VALUE']
        if not isinstance(body,str) or len(body.encode('utf-16-le'))//2 != stored['N']:
            body = clob_text(sql, p.table, p.c('VALUE_JSON'), f'{p.c("RELEASE_ID") }=:release AND {p.c("KIND") }=:kind AND {p.c("ROW_ID") }=:id',
                             [('release',release_id,'VARCHAR2'),('kind',row['kind'],'VARCHAR2'),('id',row['row_id'],'VARCHAR2')])
        expected = {column: row[key] for column,key in [('DOCUMENT_ID','document_id'),('LOOKUP_ID','lookup_id'),
                    ('OWNER_ID','owner_id'),('TARGET_ID','target_id'),('ROW_SHA256','sha256')]}
        if {k:stored[k] for k in expected} != expected or body is None or json.loads(body) != row['value']:
            raise DPError('QUERY_READBACK: stored query row differs')


def publish(client, *, generation, source_release_id, target_binding, directory, seconds=3600):
    """Resumable Dataiku publication; does not change any active pointer."""
    import fcntl
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/'publish.lock').open('a') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise DPError('QUERY_IN_PROGRESS: another query publication owns this directory') from None
        receipt = directory/'state.json'
        identity = {'source_release_id': source_release_id, 'target_binding': target_binding,
                    'generation': str(Path(generation).resolve())}
        state = json.loads(receipt.read_text()) if receipt.is_file() else {
            'identity': identity, 'deadline': time.time()+7*86400, 'status': 'PREPARING', 'verified_rows': {}}
        if state['identity'] != identity:
            raise DPError('QUERY_RESUME_BINDING: publication identity changed')
        atomic_json(receipt, state)
        sql = SQL(client, journal=directory/'calls.jsonl', binding=digest(identity),
                  seconds=max(0, min(seconds, state['deadline']-time.time())))
        try:
            source = get_release(sql, source_release_id)
            manifest, assets, tables = describe(generation, source)
            _, inventory_assets = inventory(generation)
            value = {'schema_version': SCHEMA, 'status': 'COMPLETE', 'source_release_id': source_release_id,
                     'dataset_version': source['dataset_version'], 'source_manifest': manifest,
                     'search_selection': source.get('search_selection'), 'assets': assets, 'tables': tables,
                     'projection': 'sqlite-logical-rows-and-fts5-positions-v1',
                     'metadata':asset_metadata(generation,inventory_assets),
                     'selection_proof':selection_proof(generation,manifest),
                     'publisher_sha256': file_sha(__file__)}
            from . import oracle_query_navigation_publish
            from semantic_runtime import navigation_match, structure_navigation, inherited_navigation
            value['navigation_compilers']={module.__name__:file_sha(module.__file__) for module in (
                oracle_query_navigation_publish,navigation_match,structure_navigation,inherited_navigation)}
            release_id = digest(value)
            if state.get('release_id', release_id) != release_id:
                raise DPError('QUERY_RESUME_BINDING: query projection changed')
            state.update(release_id=release_id, status='UPLOADING')
            atomic_json(receipt, state)
            for relative, expected_sha in assets.items():
                path = checked_path(generation, relative)
                if file_sha(path) != expected_sha:
                    raise DPError('QUERY_SOURCE_CHANGED: projection input changed')
                batch, seen, size = [], defaultdict(int), 0
                def flush():
                    if not batch:
                        return
                    # Reconcile prior rows as well. A checkpoint is not proof
                    # that an Oracle value has remained unchanged since then.
                    insert_records(sql, release_id, batch)
                    _verify_batch(sql, release_id, batch)
                    for kind in {r['kind'] for r in batch}:
                        state['verified_rows'][kind] = seen[kind]
                    atomic_json(receipt, state)
                for row in projected_rows(path, relative, source):
                    length = len(json_body(row))
                    if batch and (len(batch) == 20 or size+length > 4*1024*1024):
                        flush()
                        batch, size = [], 0
                    seen[row['kind']] += 1
                    batch.append(row)
                    size += length
                flush()
                if file_sha(path) != expected_sha:
                    raise DPError('QUERY_SOURCE_CHANGED: input changed during upload')
            for kind, expected in tables.items():
                row_names = names(sql, 'query_row', ROW)
                result = sql.query(f'SELECT COUNT(*) AS N FROM {row_names.table} WHERE {row_names.c("RELEASE_ID")}=:release AND {row_names.c("KIND")}=:kind',
                                   [('release',release_id,'VARCHAR2'),('kind',kind,'VARCHAR2')], limit=1)
                if result != [{'N': expected['rows']}]:
                    raise DPError('QUERY_ROW_COUNT: remote table differs')
            release_names = names(sql, 'query_release', RELEASE)
            statement = (f'DECLARE n NUMBER; BEGIN SELECT COUNT(*) INTO n FROM {release_names.table} WHERE {release_names.c("RELEASE_ID")}=:release; '
                         f'IF n=0 THEN INSERT INTO {release_names.table}({release_names.c("RELEASE_ID")},{release_names.c("MANIFEST_JSON")}) VALUES(:release,:body); END IF; '
                         'COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
            sql.request(statement, [('release', release_id, 'VARCHAR2'), ('body', json_body(value), 'CLOB')], write=True)
            if read_release(sql, release_id) != value:
                raise DPError('QUERY_RELEASE_READBACK: query release differs')
            state.update(status='COMPLETE', completed_at=time.time(), active_changed=False)
            atomic_json(receipt, state)
            return {'status': 'COMPLETE', 'release_id': release_id, 'receipt': str(receipt), 'active_changed': False}
        except Exception as exc:
            from semantic_runtime.oracle_dp_io import BudgetPause
            state.update(status='PAUSED' if isinstance(exc, BudgetPause) else 'FAILED',
                         error=str(exc) if isinstance(exc, DPError) else type(exc).__name__)
            atomic_json(receipt, state)
            raise


def from_notebook(desk, *, generation, source_release_id, seconds=3600):
    """Continue the existing authenticated R6 desk; no second auth/config flow."""
    check = desk.require_connection()
    if desk.recovery_required or getattr(check.client, 'deadline', None) is not None:
        raise DPError('R6_STATE: prior hold or another cell is active')
    return publish(check.client, generation=generation, source_release_id=source_release_id,
                   target_binding=desk.binding(), seconds=seconds,
                   directory=Path(desk.settings.get('log_dir') or './ords_notebook_logs')/'legal_query_publish'/source_release_id)


DEFERABLE_LOOKUP_INDEXES = frozenset({
    'LEGAL_Q_ROW_LOOKUP', 'LEGAL_Q_ROW_OWNER', 'LEGAL_Q_ROW_TARGET', 'LEGAL_Q_ROW_DOCUMENT',
})


def schema(sql, *, create=False, allow_missing_lookup_indexes=False):
    """Check/create only the dedicated query objects; never alter/drop tables.

    Oracle DDL commits independently. An uncertain response remains a failure;
    the next explicit invocation inspects the dictionary before attempting DDL.
    """
    if type(allow_missing_lookup_indexes) is not bool:
        raise DPError('QUERY_INDEX_POLICY: expected a boolean')
    physical=getattr(sql.client,'schema_map',None)
    if physical:
        if create:raise DPError('MAPPED_DDL_SEPARATE: execute generated creation SQL first')
        result = physical.preflight(sql,keys=['query_release','query_row','query_active','query_state'])
        # Mapped preflight requires every declared index. Nothing was deferred;
        # expose the same result contract consumed by full/clean importers.
        return {**result, 'missing': [], 'deferred_indexes': []}
    expected = {}
    indexes = {}
    for statement in DDL:
        match = re.match(r'CREATE TABLE SIDDA\.(\w+)', statement)
        if match:
            name = match[1]
            fields = {}
            for col, typ, width, tail in re.findall(r'(\w+)\s+(VARCHAR2|NUMBER|CLOB)(?:\((\d+)(?: BYTE)?\))?([^,\n]*)', statement):
                fields[col] = {'type': typ, 'width': int(width) if width else None,
                               'nullable': 'N' if 'NOT NULL' in tail or 'PRIMARY KEY' in tail else 'Y'}
            expected[name] = (statement, fields)
        else:
            match = re.fullmatch(r'CREATE INDEX SIDDA\.(\w+) ON SIDDA\.(\w+)\(([^)]+)\)', statement)
            if not match:
                raise DPError('QUERY_DDL_CONTRACT: unrecognized maintained DDL')
            indexes[match[1]] = (statement, match[2], match[3].split(','))
    def columns(name):
        return sql.query('SELECT COLUMN_NAME,DATA_TYPE,DATA_LENGTH,DATA_PRECISION,DATA_SCALE,NULLABLE,CHAR_USED FROM ALL_TAB_COLUMNS '
                         'WHERE OWNER=:owner AND TABLE_NAME=:name ORDER BY COLUMN_ID',
                         [('owner','SIDDA','VARCHAR2'),('name',name,'VARCHAR2')], limit=100)
    missing = []
    deferred = []
    for name, (statement, fields) in expected.items():
        current = columns(name)
        if not current:
            if not create:
                missing.append(name)
                continue
            sql.request(statement, write=True)
            current = columns(name)
        actual = {r['COLUMN_NAME']: r for r in current}
        if set(actual) != set(fields):
            raise DPError('QUERY_DDL_COLUMNS: incompatible table '+name)
        for col, spec in fields.items():
            row = actual[col]
            if (row['DATA_TYPE'] != spec['type'] or row['NULLABLE'] != spec['nullable'] or
                    (spec['type']=='VARCHAR2' and (row['DATA_LENGTH'] != spec['width'] or row['CHAR_USED'] != 'B')) or
                    (spec['type']=='NUMBER' and (row['DATA_PRECISION'] != spec['width'] or row['DATA_SCALE'] != 0))):
                raise DPError('QUERY_DDL_TYPE: incompatible column '+name+'.'+col)
    for name, (statement, table, fields) in indexes.items():
        def inspect():
            return sql.query('SELECT TABLE_NAME,COLUMN_NAME,COLUMN_POSITION FROM ALL_IND_COLUMNS '
                             'WHERE INDEX_OWNER=:owner AND INDEX_NAME=:name ORDER BY COLUMN_POSITION',
                             [('owner','SIDDA','VARCHAR2'),('name',name,'VARCHAR2')], limit=100)
        current = inspect()
        if not current:
            if not create:
                if allow_missing_lookup_indexes and name in DEFERABLE_LOOKUP_INDEXES:
                    deferred.append(name)
                else:
                    missing.append(name)
                continue
            sql.request(statement, write=True)
            current = inspect()
        if current != [{'TABLE_NAME':table,'COLUMN_NAME':field,'COLUMN_POSITION':i} for i,field in enumerate(fields,1)]:
            raise DPError('QUERY_DDL_INDEX: incompatible query index '+name)
    # PK/FK/check validation is required for write concurrency, not just shape.
    primary = {'LEGAL_RAG_QUERY_RELEASE_A':['RELEASE_ID'],
               'LEGAL_RAG_QUERY_ROW_A':['RELEASE_ID','KIND','ROW_ID'],
               'LEGAL_RAG_QUERY_ACTIVE_A':['CHANNEL'],
               'LEGAL_RAG_QUERY_STATE_A':['SCOPE_HASH','STATE_KEY']}
    for name in expected:
        if name in missing:
            continue
        rows = sql.query('SELECT CONSTRAINT_TYPE,STATUS,VALIDATED,SEARCH_CONDITION_VC FROM ALL_CONSTRAINTS '
                          "WHERE OWNER=:owner AND TABLE_NAME=:name AND CONSTRAINT_TYPE IN ('P','R','C')",
                          [('owner','SIDDA','VARCHAR2'),('name',name,'VARCHAR2')], limit=100)
        if not any(r['CONSTRAINT_TYPE']=='P' for r in rows) or any(r['STATUS']!='ENABLED' or r['VALIDATED']!='VALIDATED' for r in rows):
            raise DPError('QUERY_DDL_CONSTRAINT: missing/disabled/unvalidated constraints on '+name)
        normalize = lambda text: re.sub(r'[\s"()]', '', text or '').upper()
        checks = {normalize(r.get('SEARCH_CONDITION_VC')) for r in rows if r['CONSTRAINT_TYPE']=='C'}
        required = {'LEGAL_RAG_QUERY_RELEASE_A':{'MANIFEST_JSONISJSON'},
                    'LEGAL_RAG_QUERY_ROW_A':{'VALUE_JSONISJSON'},
                    'LEGAL_RAG_QUERY_ACTIVE_A':{'REVISION>=1'},
                    'LEGAL_RAG_QUERY_STATE_A':{'VALUE_JSONISJSON','REVISION>=1'}}
        if not required[name] <= checks:
            raise DPError('QUERY_DDL_CONSTRAINT: required JSON/revision checks differ on '+name)
        if name == 'LEGAL_RAG_QUERY_ACTIVE_A':
            references = sql.query('SELECT fk.DELETE_RULE,child.COLUMN_NAME,parent.OWNER AS TARGET_OWNER,'
                'parent.TABLE_NAME AS TARGET_TABLE,parent.COLUMN_NAME AS TARGET_COLUMN '
                'FROM ALL_CONSTRAINTS fk JOIN ALL_CONS_COLUMNS child ON child.OWNER=fk.OWNER '
                'AND child.CONSTRAINT_NAME=fk.CONSTRAINT_NAME JOIN ALL_CONS_COLUMNS parent '
                'ON parent.OWNER=fk.R_OWNER AND parent.CONSTRAINT_NAME=fk.R_CONSTRAINT_NAME '
                'AND parent.POSITION=child.POSITION '
                "WHERE fk.OWNER=:owner AND fk.TABLE_NAME=:name AND fk.CONSTRAINT_TYPE='R' ORDER BY child.POSITION",
                [('owner','SIDDA','VARCHAR2'),('name',name,'VARCHAR2')], limit=100)
            if references != [{'DELETE_RULE':'NO ACTION','COLUMN_NAME':'RELEASE_ID','TARGET_OWNER':'SIDDA',
                               'TARGET_TABLE':'LEGAL_RAG_QUERY_RELEASE_A','TARGET_COLUMN':'RELEASE_ID'}]:
                raise DPError('QUERY_DDL_CONSTRAINT: active release foreign key differs')
        keys = sql.query('SELECT c.COLUMN_NAME,c.POSITION FROM ALL_CONSTRAINTS p JOIN ALL_CONS_COLUMNS c '
                          'ON c.OWNER=p.OWNER AND c.CONSTRAINT_NAME=p.CONSTRAINT_NAME '
                          "WHERE p.OWNER=:owner AND p.TABLE_NAME=:name AND p.CONSTRAINT_TYPE='P' ORDER BY c.POSITION",
                          [('owner','SIDDA','VARCHAR2'),('name',name,'VARCHAR2')], limit=100)
        if keys != [{'COLUMN_NAME':column,'POSITION':i} for i,column in enumerate(primary[name],1)]:
            raise DPError('QUERY_DDL_PRIMARY_KEY: incompatible primary key on '+name)
    return {'status': 'MISSING' if missing else 'READY', 'missing': missing,
            'deferred_indexes': deferred, 'objects': sorted([*expected,*indexes])}


def schema_from_notebook(desk, *, create=False):
    check = desk.require_connection()
    if desk.recovery_required or getattr(check.client, 'deadline', None) is not None:
        raise DPError('R6_STATE: prior hold or another cell is active')
    folder = Path(desk.settings.get('log_dir') or './ords_notebook_logs')/'legal_query_schema'
    folder.mkdir(parents=True, exist_ok=True)
    sql = SQL(check.client, journal=folder/'calls.jsonl', binding=desk.binding(), seconds=300)
    result = schema(sql, create=create)
    atomic_json(folder/'state.json', {**result, 'create_requested':create, 'checked_at':time.time()})
    return result


def main(argv=None):
    """Stable pipeline command; no new standalone runner or background scheduler."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('ddl', help='print the maintained query DDL; no connection or writes')
    for action in ('check-schema','create-schema','publish','activate'):
        p = sub.add_parser(action)
        p.add_argument('--log-dir', required=True, type=Path)
        if action == 'publish':
            p.add_argument('--generation', required=True, type=Path)
            p.add_argument('--source-release-id', required=True)
        if action == 'activate':
            p.add_argument('--channel', required=True)
            p.add_argument('--release-id', required=True)
            p.add_argument('--expected-revision', required=True, type=int)
            p.add_argument('--expected-release-id')
    args = parser.parse_args(argv)
    if args.action == 'ddl':
        print('-- DATAIKU ONLY. New query objects; does not switch code-serving.\n'+
              '\n\n'.join(statement+';' for statement in DDL))
        return 0
    from semantic_runtime.oracle_dp import client_from_environment, environment_binding
    client, binding = client_from_environment(), environment_binding()
    if args.action == 'publish':
        result = publish(client, generation=args.generation, source_release_id=args.source_release_id,
                         target_binding=binding, directory=args.log_dir)
    else:
        args.log_dir.mkdir(parents=True,exist_ok=True)
        sql = SQL(client, journal=args.log_dir/'calls.jsonl', binding=binding, seconds=300)
        result = (activate(sql, args.channel, args.release_id, expected_revision=args.expected_revision,
                           expected_release_id=args.expected_release_id) if args.action == 'activate'
                  else schema(sql, create=args.action == 'create-schema'))
        atomic_json(args.log_dir/'result.json', {'action':args.action,'result':result,'at':time.time()})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('status') != 'MISSING' else 2
