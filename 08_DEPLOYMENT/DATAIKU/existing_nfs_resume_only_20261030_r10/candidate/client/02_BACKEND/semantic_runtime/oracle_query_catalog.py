"""SQL-queryable release catalogue and atomic active pointers.

Only Dataiku publishes rows/releases and changes active pointers. Serving pins
one COMPLETE release and reads bounded pages. SQLite asset blobs are never a
query source. The active pointer is an explicitly revisioned deployment choice.
"""
from __future__ import annotations

import json
import re

from .oracle_dp_io import DPError, digest
from .oracle_dp_assets import clob_text
from .physical_mapping import names as physical_names

SCHEMA = 'oracle-query-release-v1'
RELEASE = 'SIDDA.LEGAL_RAG_QUERY_RELEASE_A'
ROW = 'SIDDA.LEGAL_RAG_QUERY_ROW_A'
ACTIVE = 'SIDDA.LEGAL_RAG_QUERY_ACTIVE_A'
STATE = 'SIDDA.LEGAL_RAG_QUERY_STATE_A'
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_WRITE_BATCH_ROWS = 500

# Deliberately separate from the legacy asset tables. Creation is a Dataiku
# operation, never an application-startup side effect.
DDL = (
    f'''CREATE TABLE {RELEASE} (
        RELEASE_ID VARCHAR2(64 BYTE) PRIMARY KEY,
        MANIFEST_JSON CLOB NOT NULL,
        CONSTRAINT LEGAL_Q_RELEASE_JSON CHECK (MANIFEST_JSON IS JSON))''',
    f'''CREATE TABLE {ROW} (
        RELEASE_ID VARCHAR2(64 BYTE) NOT NULL, KIND VARCHAR2(64 BYTE) NOT NULL,
        ROW_ID VARCHAR2(64 BYTE) NOT NULL, DOCUMENT_ID VARCHAR2(512 BYTE),
        LOOKUP_ID VARCHAR2(512 BYTE), OWNER_ID VARCHAR2(512 BYTE),
        TARGET_ID VARCHAR2(512 BYTE), ROW_SHA256 VARCHAR2(64 BYTE) NOT NULL,
        VALUE_JSON CLOB NOT NULL,
        CONSTRAINT LEGAL_Q_ROW_PK PRIMARY KEY (RELEASE_ID,KIND,ROW_ID),
        CONSTRAINT LEGAL_Q_ROW_JSON CHECK (VALUE_JSON IS JSON))''',
    f'CREATE INDEX SIDDA.LEGAL_Q_ROW_LOOKUP ON {ROW}(RELEASE_ID,KIND,LOOKUP_ID)',
    f'CREATE INDEX SIDDA.LEGAL_Q_ROW_OWNER ON {ROW}(RELEASE_ID,KIND,OWNER_ID)',
    f'CREATE INDEX SIDDA.LEGAL_Q_ROW_TARGET ON {ROW}(RELEASE_ID,KIND,TARGET_ID)',
    f'CREATE INDEX SIDDA.LEGAL_Q_ROW_DOCUMENT ON {ROW}(RELEASE_ID,KIND,DOCUMENT_ID)',
    f'''CREATE TABLE {ACTIVE} (
        CHANNEL VARCHAR2(64 BYTE) PRIMARY KEY, RELEASE_ID VARCHAR2(64 BYTE) NOT NULL,
        REVISION NUMBER(18) NOT NULL CHECK (REVISION>=1),
        CONSTRAINT LEGAL_Q_ACTIVE_RELEASE FOREIGN KEY (RELEASE_ID) REFERENCES {RELEASE}(RELEASE_ID))''',
    f'''CREATE TABLE {STATE} (
        SCOPE_HASH VARCHAR2(64 BYTE) NOT NULL, STATE_KEY VARCHAR2(128 BYTE) NOT NULL,
        REVISION NUMBER(18) NOT NULL CHECK (REVISION>=1),
        VALUE_SHA256 VARCHAR2(64 BYTE) NOT NULL, VALUE_JSON CLOB NOT NULL,
        CONSTRAINT LEGAL_Q_STATE_PK PRIMARY KEY (SCOPE_HASH,STATE_KEY),
        CONSTRAINT LEGAL_Q_STATE_JSON CHECK (VALUE_JSON IS JSON))''',
)


def pin(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise DPError('QUERY_PIN: expected sha256')
    return value


def channel_name(value):
    if not isinstance(value, str) or not re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}', value):
        raise DPError('QUERY_CHANNEL: invalid channel')
    return value


def json_body(value):
    # ASCII is intentional: ORDS CLOB fallback has a lossless byte/character
    # boundary even on servers limiting each result-field length.
    text = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(text.encode()) > MAX_JSON_BYTES:
        raise DPError('QUERY_VALUE_SIZE: split the object; no truncation')
    return text


def read_release(sql, release_id):
    p=physical_names(sql,'query_release',RELEASE)
    release_id = pin(release_id)
    text = clob_text(sql, p.table, p.c('MANIFEST_JSON'), p.c('RELEASE_ID')+'=:release',
                     [('release', release_id, 'VARCHAR2')], max_chars=MAX_JSON_BYTES)
    if text is None:
        raise DPError('QUERY_RELEASE_MISSING: SQL-queryable publication is required')
    value = json.loads(text)
    if (digest(value) != release_id or value.get('schema_version') != SCHEMA or
            value.get('status') != 'COMPLETE'):
        raise DPError('QUERY_RELEASE_BINDING: incomplete or changed query release')
    pin(value.get('source_release_id'))
    pin(value.get('dataset_version'))
    return value


def active(sql, channel):
    p=physical_names(sql,'query_active',ACTIVE)
    rows = sql.query(f'SELECT {p.select("RELEASE_ID","REVISION")} FROM {p.table} WHERE {p.c("CHANNEL") }=:channel',
                     [('channel', channel_name(channel), 'VARCHAR2')], limit=1)
    if not rows:
        return None
    row = rows[0]
    if type(row['REVISION']) is not int or row['REVISION'] < 1:
        raise DPError('QUERY_ACTIVE: invalid active revision')
    return {'release_id': pin(row['RELEASE_ID']), 'revision': row['REVISION']}


def select_release(sql, *, release_id=None, channel=None):
    """Call once at request start; all subsequent reads use the returned pin."""
    if bool(release_id) == bool(channel):
        raise DPError('QUERY_CONFIG: choose DP_QUERY_RELEASE_ID or DP_QUERY_CHANNEL, exactly one')
    selected = {'release_id': release_id, 'revision': None} if release_id else active(sql, channel)
    if selected is None:
        raise DPError('QUERY_ACTIVE_MISSING: no completed release selected for channel')
    return {**selected, 'manifest': read_release(sql, selected['release_id'])}


def activate(sql, channel, release_id, *, expected_revision, expected_release_id=None):
    """Atomic compare-and-swap; response loss is resolved by explicit readback.

    No retry/last-writer-wins update is performed. An uncertain write retains
    its target and expected revision so the same operation can be reconciled.
    """
    p=physical_names(sql,'query_active',ACTIVE)
    channel, release_id = channel_name(channel), pin(release_id)
    if type(expected_revision) is not int or expected_revision < 0:
        raise DPError('QUERY_ACTIVE: invalid expected revision')
    if bool(expected_release_id) != bool(expected_revision):
        raise DPError('QUERY_ACTIVE: existing revision requires its release pin')
    if expected_release_id is not None:
        pin(expected_release_id)
    read_release(sql, release_id)
    target = {'release_id': release_id, 'revision': expected_revision + 1}
    current = active(sql, channel)
    if current == target:
        return {**target, 'reconciled': True}
    expected = None if expected_revision == 0 else {'release_id': expected_release_id, 'revision': expected_revision}
    if current != expected:
        raise DPError('QUERY_ACTIVE_CONFLICT: pointer moved; retain existing active release')
    binds = [('channel', channel, 'VARCHAR2'), ('release', release_id, 'VARCHAR2')]
    if current is None:
        operation = f'INSERT INTO {p.table}({p.c("CHANNEL")},{p.c("RELEASE_ID")},{p.c("REVISION")}) VALUES(:channel,:release,1);'
    else:
        operation = (f'UPDATE {p.table} SET {p.c("RELEASE_ID") }=:release,{p.c("REVISION") }={p.c("REVISION")}+1 '
                     f'WHERE {p.c("CHANNEL") }=:channel AND {p.c("REVISION") }=:revision AND {p.c("RELEASE_ID") }=:previous; '
                     "IF SQL%ROWCOUNT<>1 THEN RAISE_APPLICATION_ERROR(-20031,'QUERY_ACTIVE_CONFLICT'); END IF;")
        binds += [('revision', expected_revision, 'NUMBER'), ('previous', expected_release_id, 'VARCHAR2')]
    sql.request('BEGIN '+operation+' COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;', binds, write=True)
    if active(sql, channel) != target:
        raise DPError('QUERY_ACTIVE_UNCONFIRMED: active pointer readback differs')
    return {**target, 'reconciled': False}


LOOKUP_ENCODING = 'sha256-overflow-v1'


def lookup_key(value):
    """Bound an auxiliary index; the complete logical value stays in VALUE_JSON.

    Not for DOCUMENT_ID: that field is an authorization boundary. Consumers
    must retain their original-value predicate when using this candidate key.
    """
    if value is None or len(value.encode()) <= 512:
        return value
    return 'sha256:'+digest(value)


def record(kind, value, *, key, document_id=None, lookup_id=None, owner_id=None, target_id=None):
    if not isinstance(kind, str) or not re.fullmatch('[a-z][a-z0-9_.]{0,63}', kind):
        raise DPError('QUERY_KIND: invalid published row kind')
    for name, field in (('document_id',document_id),('lookup_id',lookup_id),
                        ('owner_id',owner_id),('target_id',target_id)):
        if field is not None and (not isinstance(field, str) or not field or len(field.encode()) > 512):
            size = len(field.encode()) if isinstance(field,str) else None
            raise DPError(f'QUERY_RECORD_KEY: field={name} utf8_bytes={size} limit=512')
    json_body(value)
    result = {'kind': kind, 'row_id': digest(key), 'document_id': document_id,
              'lookup_id': lookup_id, 'owner_id': owner_id, 'target_id': target_id, 'value': value}
    return {**result, 'sha256': digest(result)}


def insert_records(sql, release_id, rows):
    """An immutable bounded batch. Existing unequal rows abort the transaction."""
    p=physical_names(sql,'query_row',ROW)
    release_id = pin(release_id)
    if not 1 <= len(rows) <= MAX_WRITE_BATCH_ROWS:
        raise DPError('QUERY_BATCH: expected 1..500 rows')
    statements, binds = ['DECLARE n NUMBER; BEGIN'], [('release', release_id, 'VARCHAR2')]
    for i, row in enumerate(rows):
        # Revalidate the entire producer record at the boundary.
        if digest({k:v for k,v in row.items() if k != 'sha256'}) != pin(row['sha256']):
            raise DPError('QUERY_RECORD_HASH: changed row')
        pin(row['row_id'])
        suffix = str(i)
        names = {'kind': row['kind'], 'id': row['row_id'], 'doc': row['document_id'],
                 'lookup': row['lookup_id'], 'owner': row['owner_id'], 'target': row['target_id'],
                 'hash': row['sha256'], 'body': json_body(row['value'])}
        for name, value in names.items():
            binds.append((name+suffix, value, 'CLOB' if name == 'body' else 'VARCHAR2'))
        key = f'{p.c("RELEASE_ID") }=:release AND {p.c("KIND") }=:kind{suffix} AND {p.c("ROW_ID") }=:id{suffix}'
        columns=','.join(p.c(c) for c in ('RELEASE_ID','KIND','ROW_ID','DOCUMENT_ID','LOOKUP_ID','OWNER_ID','TARGET_ID','ROW_SHA256','VALUE_JSON'))
        statements += [f'SELECT COUNT(*) INTO n FROM {p.table} WHERE {key};',
            f'IF n=0 THEN INSERT INTO {p.table} '
            f'({columns}) '
            f'VALUES(:release,:kind{suffix},:id{suffix},:doc{suffix},:lookup{suffix},:owner{suffix},:target{suffix},:hash{suffix},:body{suffix}); END IF;',
            f'SELECT COUNT(*) INTO n FROM {p.table} WHERE {key} AND {p.c("ROW_SHA256") }=:hash{suffix} '
            f'AND DBMS_LOB.COMPARE({p.c("VALUE_JSON")},:body{suffix})=0 AND '
            + ' AND '.join(f'({p.c(column)}=:{name}{suffix} OR ({p.c(column)} IS NULL AND :{name}{suffix} IS NULL))'
                           for column,name in [('DOCUMENT_ID','doc'),('LOOKUP_ID','lookup'),('OWNER_ID','owner'),('TARGET_ID','target')]) + ';',
            "IF n<>1 THEN RAISE_APPLICATION_ERROR(-20032,'QUERY_ROW_CONFLICT'); END IF;"]
    statements += ['COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;']
    sql.request('\n'.join(statements), binds, write=True)


class Records:
    """Bounded indexed row lookup for navigation, glossary and relation ports."""
    def __init__(self, sql, release_id, manifest, *, document_ids=None):
        self.sql, self.release_id, self.manifest = sql, pin(release_id), manifest
        if digest(manifest) != release_id:
            raise DPError('QUERY_RELEASE_BINDING: reader manifest differs')
        self.document_ids = None if document_ids is None else frozenset(document_ids)

    def page(self, kind, *, document_id=None, lookup_id=None, lookup_ids=None, owner_id=None, target_id=None, after=None, limit=50):
        if kind not in self.manifest['tables']:
            raise DPError('QUERY_KIND: undeclared table')
        if type(limit) is not int or not 1 <= limit <= 100:
            raise DPError('QUERY_PAGE: expected 1..100 rows')
        where = ['RELEASE_ID=:release', 'KIND=:kind']
        binds = [('release', self.release_id, 'VARCHAR2'), ('kind', kind, 'VARCHAR2')]
        if self.document_ids is not None:
            if document_id is not None and document_id not in self.document_ids:
                raise DPError('QUERY_SCOPE: query row document outside authorized request scope')
            # Corpus-independent glossary rows have no document owner. Source,
            # definition, integrity and navigation rows retain their owner.
            where.append("(DOCUMENT_ID IS NULL OR DOCUMENT_ID IN (SELECT jt.did FROM "
                         "JSON_TABLE(:authorized_documents,'$[*]' COLUMNS(did VARCHAR2(512) PATH '$' ERROR ON ERROR)) jt))")
            binds.append(('authorized_documents',json_body(sorted(self.document_ids)),'CLOB'))
        if lookup_ids is not None:
            if lookup_id is not None or not isinstance(lookup_ids, (list,tuple)) or not 1 <= len(lookup_ids) <= 100:
                raise DPError('QUERY_FILTER: expected 1..100 lookup IDs without lookup_id')
            if any(not isinstance(v,str) or not v or len(v.encode()) > 512 for v in lookup_ids):
                raise DPError('QUERY_FILTER: invalid lookup ID')
            where.append('LOOKUP_ID IN ('+','.join(':lookup'+str(i) for i in range(len(lookup_ids)))+')')
            binds.extend(('lookup'+str(i),value,'VARCHAR2') for i,value in enumerate(lookup_ids))
        for column, value in [('DOCUMENT_ID', document_id), ('LOOKUP_ID', lookup_id),
                              ('OWNER_ID', owner_id), ('TARGET_ID', target_id)]:
            if value is not None:
                if not isinstance(value, str) or not value or len(value.encode()) > 512:
                    raise DPError('QUERY_FILTER: invalid lookup key')
                name = column.lower()
                where.append(column+'=:'+name)
                binds.append((name, value, 'VARCHAR2'))
        scope = digest({'release': self.release_id, 'kind': kind, 'filters': binds})
        if after:
            if not isinstance(after, dict) or after.get('scope') != scope:
                raise DPError('QUERY_CURSOR: cursor belongs to another query')
            where.append("NLSSORT(ROW_ID,'NLS_SORT=BINARY')>NLSSORT(:after,'NLS_SORT=BINARY')")
            binds.append(('after', pin(after['row_id']), 'VARCHAR2'))
        rows = self.sql.query(f'SELECT ROW_ID,ROW_SHA256,DOCUMENT_ID,LOOKUP_ID,OWNER_ID,TARGET_ID,TO_CLOB(VALUE_JSON) AS VALUE,DBMS_LOB.GETLENGTH(VALUE_JSON) AS N FROM {ROW} WHERE '+ ' AND '.join(where) +
                              f" ORDER BY NLSSORT(ROW_ID,'NLS_SORT=BINARY') FETCH FIRST {limit} ROWS ONLY", binds, limit=limit)
        ids = [pin(row['ROW_ID']) for row in rows]
        if ids != sorted(set(ids)) or (after and any(i <= after['row_id'] for i in ids)):
            raise DPError('QUERY_PAGE_ORDER: invalid catalogue page')
        values = []
        for row in rows:
            if self.document_ids is not None and row['DOCUMENT_ID'] is not None and row['DOCUMENT_ID'] not in self.document_ids:
                raise DPError('QUERY_SCOPE: returned row outside authorized request scope')
            body = row['VALUE']
            if type(row['N']) is not int or not 0 <= row['N'] <= MAX_JSON_BYTES:
                raise DPError('QUERY_VALUE_SIZE: invalid row size')
            if not isinstance(body, str) or len(body.encode('utf-16-le'))//2 != row['N']:
                body = clob_text(self.sql, ROW, 'VALUE_JSON', 'RELEASE_ID=:release AND KIND=:kind AND ROW_ID=:id',
                                 [('release', self.release_id, 'VARCHAR2'), ('kind', kind, 'VARCHAR2'),
                                  ('id', row['ROW_ID'], 'VARCHAR2')], max_chars=MAX_JSON_BYTES)
            if body is None:
                raise DPError('QUERY_ROW_MISSING: row disappeared within pinned release')
            value = json.loads(body)
            envelope = {'kind': kind, 'row_id': row['ROW_ID'], 'document_id': row['DOCUMENT_ID'],
                        'lookup_id': row['LOOKUP_ID'], 'owner_id': row['OWNER_ID'], 'target_id': row['TARGET_ID'],
                        'value': value}
            if digest(envelope) != row['ROW_SHA256']:
                raise DPError('QUERY_ROW_HASH: row changed within pinned release')
            if any(value is not None and row[column] != value for column,value in
                   [('DOCUMENT_ID',document_id),('LOOKUP_ID',lookup_id),('OWNER_ID',owner_id),('TARGET_ID',target_id)]):
                raise DPError('QUERY_ROW_FILTER: returned row differs from requested scope')
            if lookup_ids is not None and row['LOOKUP_ID'] not in lookup_ids:
                raise DPError('QUERY_ROW_FILTER: unexpected lookup ID')
            values.append(value)
        return {'rows': values, 'next': {'scope': scope, 'row_id': ids[-1]} if len(rows) == limit else None,
                'release_id': self.release_id}
