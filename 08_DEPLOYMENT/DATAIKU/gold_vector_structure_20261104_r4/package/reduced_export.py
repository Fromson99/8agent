"""Reduced export only; preserve the legacy preparation producer byte-for-byte.

The pinned legacy source/schema/FTS helpers remain shared. _asset_rows differs
only by an exclusion argument and the pre-SELECT skip; a structural regression
test enforces that boundary. This module never creates preparation descriptors.
"""
import base64
from pathlib import Path
import re
import sqlite3
from lawrag.pipeline.oracle_transfer_progress import report, sqlite_work
from lawrag.pipeline.oracle_query_publish import source_records, _name, _kind, _lookups
from semantic_runtime.oracle_dp_io import DPError
from semantic_runtime.oracle_query_catalog import record

def projected_rows(path, relative, source_release, *, excluded_tables=()):
    report('SOURCE_ROWS' if relative=='store.sqlite' else 'ASSET_ROWS',asset=relative)
    if relative == 'store.sqlite' and excluded_tables:
        raise DPError('QUERY_SOURCE_EXCLUSION_FORBIDDEN')
    yield from (source_records(path, source_release) if relative == 'store.sqlite' else asset_rows(path, relative, excluded_tables=excluded_tables))
    from lawrag.pipeline.oracle_query_navigation_publish import records
    report('NATIVE_NAVIGATION',asset=relative)
    yield from records(path,relative,source_release)


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
