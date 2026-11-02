"""Bounded original SQLite rows; no Oracle samples or repeated sample bodies."""
import base64
from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3
import time
from g19diag_common import canonical, error

MAX_ROWS = 2000
MAX_BYTES = 8*1024**2


@contextmanager
def source_db(ctx, asset, seconds):
    root = Path(ctx['root']).resolve(strict=True)
    path = (root/asset).resolve(strict=True)
    if root not in path.parents or asset not in ctx['state']['binding']['files']:
        raise ValueError('SOURCE_ASSET_BINDING')
    def signature():
        st = path.stat()
        with path.open('rb') as stream: header=stream.read(100)
        return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, header
    def sidecars():
        return any(Path(str(path)+s).exists() and Path(str(path)+s).stat().st_size
                   for s in ('-wal', '-journal'))
    if sidecars(): raise ValueError('SOURCE_ACTIVE_JOURNAL')
    before = signature(); end = time.monotonic()+seconds
    db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=min(seconds, .5))
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA cache_size=-8192')
    db.execute('PRAGMA temp_store=MEMORY')
    data_version = db.execute('PRAGMA data_version').fetchone()[0]
    db.set_progress_handler(lambda: int(time.monotonic()>end), 1000)
    try:
        yield db, end
        if signature()!=before or sidecars() or db.execute('PRAGMA data_version').fetchone()[0]!=data_version:
            raise ValueError('SOURCE_CHANGED_DURING_SAMPLE')
    finally:
        db.close()


def ordinary(db, pub, asset, table):
    columns = [r[1] for r in db.execute('PRAGMA table_info('+pub._name(table)+')')]
    if not columns: raise ValueError('SOURCE_TABLE_MISSING')
    query = 'SELECT '+','.join(pub._name(c) for c in columns)+' FROM '+pub._name(table)+' LIMIT 2000'
    for ordinal, raw in enumerate(db.execute(query)):
        value = dict(raw)
        if table=='source_request' and value.get('response') is not None:
            if not isinstance(value['response'], bytes): raise ValueError('SOURCE_BINARY_TYPE')
            value['response'] = base64.b64encode(value['response']).decode('ascii')
        if any(isinstance(v,bytes) for v in value.values()): raise ValueError('SOURCE_UNSUPPORTED_BLOB')
        yield pub.record(pub._kind(asset,table),value,key=[ordinal,value],**pub._lookups(value))


def postings(db, pub, asset, table, end, meta):
    declaration = db.execute('SELECT sql FROM sqlite_master WHERE name=?',(table,)).fetchone()
    if not declaration or not re.search(r'USING\s+fts5\s*\(',declaration[0] or '',re.I):
        raise ValueError('SOURCE_FTS5_REQUIRED')
    db.execute('CREATE VIRTUAL TABLE temp.g19_diag_vocab USING fts5vocab(main,'+pub._name(table)+',instance)')
    first = db.execute('PRAGMA table_info('+pub._name(table)+')').fetchone()[1]
    unit = table=='unit_fts' and first=='key'
    logical = 'f.'+pub._name(first) if unit else 'CAST(f.rowid AS TEXT)'
    join = ' LEFT JOIN unit u ON u.key=f.key' if unit else ''
    owner = 'u.document_id,u.source_id' if unit else 'NULL AS document_id,NULL AS source_id'
    # Bound term lookup and complete term groups. Never export truncated positions.
    last = None; emitted = 0
    for _ in range(64):
        if time.monotonic()>end: break
        found = db.execute('SELECT term FROM temp.g19_diag_vocab'+(' WHERE term>?' if last is not None else '')+' LIMIT 1',
                           (last,) if last is not None else ()).fetchone()
        if found is None: break
        last = found[0]
        values = db.execute('SELECT term,doc,col,offset FROM temp.g19_diag_vocab WHERE term=? LIMIT 4097',(last,)).fetchall()
        if len(values)>4096:
            meta['oversize_terms_skipped'] = meta.get('oversize_terms_skipped',0)+1
            continue
        groups = {}
        for row in values:
            groups.setdefault((row['doc'],row['col'],row['term']),[]).append(row['offset'])
        for (doc,col,term), offsets in sorted(groups.items()):
            if time.monotonic()>end: return
            row = db.execute('SELECT '+logical+' AS logical_id,'+owner+' FROM '+pub._name(table)+' f'+join+' WHERE f.rowid=?',(doc,)).fetchone()
            if row is None: continue
            offsets.sort(key=lambda n: -1 if n is None else n)
            value = {'key':str(row['logical_id']),'column':col,'token':term,'positions':offsets,'tf':len(offsets)}
            yield pub.record(pub._kind(asset,table+'_posting'),value,key=[doc,col,term],
                             document_id=row['document_id'],lookup_id=term,owner_id=str(row['logical_id']),target_id=col)
            emitted += 1
            if emitted>=MAX_ROWS: return


def sample(ctx, loader, key, kind=None, seconds=5):
    """Return payloads in child memory and metadata safe to persist separately."""
    start = time.perf_counter(); rows = []; size = 0
    meta = {'table':key,'kind':kind,'sample_origin':'DATAIKU_SQLITE_DISTINCT',
            'status':'PREPARING','scope':'bounded source prefix/complete FTS term groups; no whole-file hash reread'}
    try:
        if key=='SRCH_ROW':
            from lawrag.pipeline import oracle_query_publish as pub
            spec = ctx['descriptor']['tables'][kind]; asset = spec['asset']
            table = spec.get('table') or kind.split('.',1)[-1]
            if asset=='store.sqlite' or pub._kind(asset,table)!=kind:
                raise ValueError('SOURCE_KIND_REQUIRES_SPECIAL_PROJECTION')
            meta.update(asset=asset,source_table=table)
            with source_db(ctx,asset,seconds) as (db,end):
                entry = db.execute('SELECT name,type,sql FROM sqlite_master WHERE name=?',(table,)).fetchone()
                if entry and 'CREATE VIRTUAL TABLE' not in (entry['sql'] or '').upper():
                    iterator = ordinary(db,pub,asset,table)
                elif table.endswith('_posting'):
                    meta['selection'] = 'complete bounded terms; common oversize terms skipped'
                    iterator = postings(db,pub,asset,table[:-8],end,meta)
                else: raise ValueError('SOURCE_DERIVED_KIND_UNSUPPORTED')
                try:
                    for record in iterator:
                        if time.monotonic()>end: meta['limit']='TIME'; break
                        row = loader.query_row(ctx['state']['binding']['query_release'],record)
                        n = len(canonical(row).encode())
                        if n>1024**2: raise ValueError('SOURCE_ROW_OVER_1MIB')
                        if size+n>MAX_BYTES: meta['limit']='MEMORY'; break
                        rows.append(row); size+=n
                        if len(rows)>=MAX_ROWS: break
                finally: iterator.close()
        else:
            from lawrag.pipeline import oracle_migration as migration
            from semantic_runtime.oracle_dp_io import KEYS
            source_kind = next(k for k,v in loader.SOURCE_MAP.items() if v[0]==key)
            meta.update(asset='store.sqlite',source_table=source_kind)
            with source_db(ctx,'store.sqlite',seconds) as (db,end):
                cursor = None; stop = False
                while len(rows)<MAX_ROWS and time.monotonic()<end and not stop:
                    part = migration.source_batch(db,source_kind,ctx['state']['binding']['files']['manifest.json'],cursor,batch_rows=100)
                    if not part: break
                    for raw in part:
                        mapped_key,row = loader.source_row(source_kind,raw)
                        if mapped_key!=key: raise ValueError('SOURCE_MAPPING_TARGET')
                        n=len(canonical(row).encode())
                        if n>1024**2: raise ValueError('SOURCE_ROW_OVER_1MIB')
                        if size+n>MAX_BYTES: meta['limit']='MEMORY'; stop=True; break
                        rows.append(row);size+=n
                        if len(rows)>=MAX_ROWS: break
                    cursor=[part[-1][c] for c in KEYS[source_kind] if c!='DATASET_VERSION']
                if time.monotonic()>=end: meta['limit']='TIME'
        meta.update(status='OK' if rows else 'NO_SOURCE_SAMPLE',sample_rows=len(rows),sample_bytes=size)
    except Exception as exc:
        # Reject partial rows on interruption/schema/mutation; never insert unverified source.
        rows=[];meta.update(status='SOURCE_SAMPLE_UNMEASURED',sample_rows=0,error=error(exc))
    meta['read_map_seconds']=time.perf_counter()-start
    return rows,meta
