"""One physical-name mapping for the existing Gold reader and publisher ports.

Logical row/JSON keys and their hashes are unchanged. Simple Oracle projections
also cover legacy vector/packed-query SQL, which does not use names(). No SQL
text replacement, persisted views, schema mutation or import-time connection.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType


class MappingError(ValueError):
    pass


CONTRACT = {
    'DOC_VER': 'MNFST_HASH_VALU DOC_ID DOC_NAME DOC_HASH_VALU DOC_ADDN_IFMN_CTNT',
    'DOC_UNIT': 'MNFST_HASH_VALU DOC_ID STRC_UNIT_ID UPPR_STRC_UNIT_ID STRC_UNIT_ADDN_IFMN_CTNT',
    'DOC_BLK': 'MNFST_HASH_VALU DOC_ID BODY_SLC_ID STRC_UNIT_ID BODY_CTNT DOC_HASH_VALU BODY_SLC_ADDN_IFMN_CTNT ADD_INFO_TEXT_OMIT_YN',
    'SRC_POST': 'DOC_POST_HASH_VALU MNFST_HASH_VALU DOC_POST_IFMN_CTNT RGSN_AITM',
    'SRCH_POST': 'RFRN_POST_HASH_VALU RFRN_POST_IFMN_CTNT',
    'SRCH_ROW': 'RFRN_POST_HASH_VALU RFRN_DTA_TYPE_VALU RFRN_DTA_ID DOC_ID RFRN_DTA_IDNF_CTNT BLNG_DTA_IDNF_CTNT TAGT_DTA_IDNF_CTNT SRCH_DATA_HASH_VALU SRCH_DATA_CTNT',
    'SRCH_CHNL': 'RFRN_CHNL_NAME RFRN_POST_HASH_VALU CHAN_NO',
    'ONTL_POST': 'ONTL_POST_ID CNCP_GROP_ID WORK_VER_NO POST_CTNT_HASH_VALU POST_KNWL_CTNT',
    'ONTL_HEAD': 'CNCP_GROP_ID ONTL_POST_ID CHAN_NO',
    'ONTL_ANC': 'ONTL_POST_ID DOC_LCT_HASH_VALU DOC_ID DOC_HASH_VALU STRC_UNIT_ID',
    'VCTR_POST': 'VCTR_POST_ID VCTR_POST_IFMN_CTNT',
    'VCTR_ITEM': 'VCTR_POST_ID VCTR_SEG_ID DOC_ID SRC_UNIT_ID VCTR_META_CTNT EMBD_VCTR_VALU',
    'VCTR_HEAD': 'RFRN_POST_HASH_VALU VCTR_POST_ID CHAN_NO',
}
ONTOLOGY = {
    'publication': ('ONTL_POST', 'PUB_ID BNDL_ID REV_NO PKG_HASH_VAL PKG_JSON_CN'),
    'head': ('ONTL_HEAD', 'BNDL_ID PUB_ID CHG_SEQ_NO'),
    'anchor': ('ONTL_ANC', 'PUB_ID ANC_HASH_VAL DOC_ID SRC_VER_ID UNIT_ID'),
}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}', value):
        raise MappingError('GOLD_MAP_IDENTIFIER')
    return value


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise MappingError('GOLD_MAP_DUPLICATE_KEY')
        out[key] = value
    return out


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(x) for x in value)
    return value


def _exact(value, keys, code):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise MappingError('GOLD_MAP_' + code)


class GoldMapping:
    def __setattr__(self, name, value):
        if getattr(self, '_sealed', False):
            raise MappingError('GOLD_MAP_IMMUTABLE_REQUEST_TARGET')
        object.__setattr__(self, name, value)

    @classmethod
    def load(cls, path, *, owner=None, expected_sha256=None):
        raw = Path(path).read_bytes()
        if len(raw) > 1024 * 1024:
            raise MappingError('GOLD_MAP_SIZE')
        sha = hashlib.sha256(raw).hexdigest()
        if expected_sha256 is not None and sha != expected_sha256:
            raise MappingError('GOLD_MAP_HASH')
        value = json.loads(raw, object_pairs_hook=_pairs)
        return cls(value, owner=owner, file_sha256=sha)

    def __init__(self, value, *, owner=None, file_sha256=None):
        value = deepcopy(value)
        _exact(value, ('schema_version', 'revision', 'owner', 'variant', 'tables'), 'ROOT')
        if value['schema_version'] != 'gold-physical-map-v1' or value['variant'] not in ('B03', 'B05', 'B003'):
            raise MappingError('GOLD_MAP_VERSION')
        self.owner = identifier(owner if owner is not None else value['owner'])
        self.variant = value['variant']
        _exact(value['tables'], CONTRACT, 'TABLES')
        names = set()
        for key, table in value['tables'].items():
            _exact(table, ('name', 'columns', 'primary_key', 'indexes'), 'TABLE')
            name = identifier(table['name'])
            # Leave room for the X0_/X1_ index identifiers used by ddl().
            if name in names or len(name) > 27:
                raise MappingError('GOLD_MAP_TABLE_COLLISION_OR_LENGTH')
            names.add(name)
            _exact(table['columns'], CONTRACT[key].split(), 'COLUMNS')
            seen = set()
            for column in table['columns'].values():
                _exact(column, ('name', 'type', 'required', 'default'), 'COLUMN')
                physical = identifier(column['name'])
                if physical in seen:
                    raise MappingError('GOLD_MAP_COLUMN_COLLISION')
                seen.add(physical)
                if not re.fullmatch(r'(?:VARCHAR2\([1-9][0-9]{0,3} BYTE\)|CHAR\(1 BYTE\)|NUMBER\([1-9][0-9]?,0\)|CLOB|TIMESTAMP\(6\) WITH TIME ZONE|VECTOR\(\*,FLOAT32\))', column['type']):
                    raise MappingError('GOLD_MAP_TYPE')
                if type(column['required']) is not bool or column['default'] not in (None, 'SYSTIMESTAMP'):
                    raise MappingError('GOLD_MAP_CONSTRAINT')
                if column['default'] and column['type'] != 'TIMESTAMP(6) WITH TIME ZONE':
                    raise MappingError('GOLD_MAP_DEFAULT')
            for columns in [table['primary_key'], *table['indexes']]:
                if not columns or len(columns) != len(set(columns)) or not set(columns) <= table['columns'].keys():
                    raise MappingError('GOLD_MAP_KEY')
        self.tables = _freeze(value['tables'])
        self.revision = value['revision']
        self.file_sha256 = file_sha256
        self.model_sha256 = hashlib.sha256(json.dumps(value['tables'], sort_keys=True).encode()).hexdigest()
        self.target_sha256 = hashlib.sha256((self.owner + ':' + self.model_sha256).encode()).hexdigest()
        self._sealed = True

    @property
    def model(self):
        """Legacy loader contract; logical names and mapped size constraints."""
        return {'tables': [{'suffix': key, 'columns': [dict(c, name=old) for old, c in t['columns'].items()]}
                           for key, t in self.tables.items()]}

    def physical_table(self, key):
        return self.owner + '.' + self.tables[key]['name']

    def column(self, key, logical):
        return self.tables[key]['columns'][logical]['name']

    def projection(self, key, aliases=None):
        columns = CONTRACT[key].split()
        aliases = columns if aliases is None else aliases
        if len(aliases) != len(columns):
            raise MappingError('GOLD_MAP_ALIAS_SHAPE')
        fields = [self.column(key, old) + ' AS ' + identifier(alias) for old, alias in zip(columns, aliases)]
        return '(SELECT ' + ','.join(fields) + ' FROM ' + self.physical_table(key) + ')'

    def table(self, key):
        # Maintained legacy SQL uses R12 column names, including native VECTOR.
        return self.projection(key)

    def names(self, key):
        from gold_connection import READ_COLUMNS, ReadNames
        if key not in READ_COLUMNS:
            raise MappingError('GOLD_UNSUPPORTED_PORT: ' + key)
        suffix, columns = READ_COLUMNS[key]
        expressions = []
        for logical, old in columns.items():
            expression = self.column(suffix, old)
            if key == 'document' and logical == 'NAME':
                expression = 'TO_CLOB(' + expression + ')'
            if logical == 'JSON_TEXT_ELIDED':
                expression = ('CASE WHEN ' + expression + ' IS NULL THEN NULL WHEN ' + expression +
                              "='Y' THEN 1 WHEN " + expression + "='N' THEN 0 ELSE 2 END")
            expressions.append(expression + ' AS ' + logical)
        return ReadNames('(SELECT ' + ','.join(expressions) + ' FROM ' + self.physical_table(suffix) + ')', tuple(columns))

    def ddl(self):
        """Explicit review/test output; loading a mapping never executes DDL."""
        statements = []
        for key, table in self.tables.items():
            fields = [c['name'] + ' ' + c['type'] + (' DEFAULT ' + c['default'] if c['default'] else '') +
                      (' NOT NULL' if c['required'] else '') for c in table['columns'].values()]
            fields.append('CONSTRAINT X0_' + table['name'] + ' PRIMARY KEY (' +
                          ','.join(self.column(key, c) for c in table['primary_key']) + ')')
            statements.append('CREATE TABLE ' + self.physical_table(key) + ' (' + ','.join(fields) + ')')
            for number, columns in enumerate(table['indexes'], 1):
                statements.append('CREATE INDEX ' + self.owner + '.X' + str(number) + '_' + table['name'] +
                                  ' ON ' + self.physical_table(key) + ' (' +
                                  ','.join(self.column(key, c) for c in columns) + ')')
        return statements

    def preflight(self, connection):
        """Read actual columns, types, sizes and nullability before corpus access."""
        with connection.cursor() as cursor:
            cursor.execute('SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE,DATA_LENGTH,CHAR_USED,DATA_PRECISION,DATA_SCALE,NULLABLE '
                           'FROM ALL_TAB_COLUMNS WHERE OWNER=:owner', owner=self.owner)
            rows = {}
            for row in cursor:
                if row[0] in {t['name'] for t in self.tables.values()}:
                    rows.setdefault(row[0], {})[row[1]] = row[2:]
        errors = []
        for key, table in self.tables.items():
            found = rows.get(table['name'], {})
            expected = {c['name'] for c in table['columns'].values()}
            if set(found) != expected:
                errors.append({'table': table['name'], 'missing': sorted(expected-set(found)), 'extra': sorted(set(found)-expected)})
            for c in table['columns'].values():
                if c['name'] not in found:
                    continue
                datatype, length, char_used, precision, scale, nullable = found[c['name']]
                typ = c['type']
                if typ.startswith(('VARCHAR2', 'CHAR')):
                    good = datatype == typ.split('(')[0] and length == int(re.search(r'\((\d+)', typ)[1]) and char_used == 'B'
                elif typ.startswith('NUMBER'):
                    good = datatype == 'NUMBER' and precision == int(re.search(r'\((\d+)', typ)[1]) and scale == 0
                elif typ.startswith('TIMESTAMP'):
                    good = datatype == 'TIMESTAMP(6) WITH TIME ZONE'
                else:
                    good = datatype == ('VECTOR' if typ.startswith('VECTOR') else typ)
                if not good or nullable != ('N' if c['required'] else 'Y'):
                    errors.append({'table': table['name'], 'column': c['name'], 'expected': typ, 'actual': list(found[c['name']])})
        if errors:
            raise MappingError('GOLD_MAP_TARGET_MISMATCH: ' + json.dumps(errors, ensure_ascii=False))
        return {'tables': len(self.tables), 'columns': sum(len(t['columns']) for t in self.tables.values()),
                'mapping_sha256': self.file_sha256, 'target_sha256': self.target_sha256}

    def ontology_repository(self, connect, *, agent_owner=None, read_only=True):
        """Reuse approval/hash/ACL/CAS logic against the three mapped Gold tables.

        Work and event records stay in the separately configured Agent owner.
        Oracle's simple updatable projection preserves the logical INSERT order
        even when DBA column order differs. No knowledge is auto-approved.
        """
        from semantic_runtime.ontology_work.repository import Repository
        mapping = self

        class MappedRepository(Repository):
            def initialize(self):
                raise MappingError('GOLD_MAP_PRECREATED_TABLES_REQUIRED')

            @contextmanager
            def session(self, write=False):
                if write and (read_only or not agent_owner):
                    raise MappingError('GOLD_MAP_ONTOLOGY_READ_ONLY')
                with super().session(write) as cursor:
                    yield cursor

        repo = MappedRepository(connect, dialect='oracle', owner=identifier(agent_owner) if agent_owner else self.owner)
        for key, (suffix, aliases) in ONTOLOGY.items():
            repo.tables[key] = mapping.projection(suffix, aliases.split())
        return repo

    def request_ontology_repository(self, request):
        """Route source-arrival lookups through the same ACL/budget-bound SQL port."""
        repository = self.ontology_repository(lambda: None)

        class Cursor:
            def setinputsizes(self, *args, **kwargs):
                pass

            def execute(self, sql, params):
                if not sql.lstrip().upper().startswith('SELECT '):
                    raise MappingError('GOLD_MAP_ONTOLOGY_READ_ONLY')
                binds = [(str(i+1), value, 'NUMBER' if isinstance(value, (int, float)) else 'CLOB' if isinstance(value, str) and len(value.encode()) > 4000 else 'VARCHAR2')
                         for i, value in enumerate(params)]
                selected = sql.split(' FROM ', 1)[0].removeprefix('SELECT ').split(',')
                self.columns = [identifier(c.strip().rsplit('.', 1)[-1]) for c in selected]
                self.sql, self.binds, self.consumed = sql, binds, False
                return self

            def fetchone(self):
                rows = self.fetchmany(1)
                return rows[0] if rows else None

            def fetchmany(self, count):
                if self.consumed:
                    return []
                if type(count) is not int or not 1 <= count <= 1025:
                    raise MappingError('GOLD_MAP_ONTOLOGY_RESULT_BOUND')
                self.consumed = True
                limited = self.sql + ' FETCH FIRST ' + str(count) + ' ROWS ONLY'
                if count <= 100:
                    rows = request.sql.query(limited, self.binds, limit=count)
                    return [tuple(row[c] for c in self.columns) for row in rows]
                # The request port allows 100 rows per call. Preserve the
                # ontology's 1024-anchor bound in ONE consistent SQL statement,
                # using a bounded JSON array rather than 11 round trips.
                sql = ('SELECT JSON_ARRAYAGG(JSON_ARRAY(' + ','.join(self.columns) +
                       ' NULL ON NULL RETURNING CLOB) RETURNING CLOB) AS ROWS_JSON FROM (' + limited + ')')
                response = request.sql.query(sql, self.binds, limit=1)
                raw = response[0]['ROWS_JSON'] if response else None
                rows = [] if raw is None else json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(rows, list) or len(rows) > count or any(not isinstance(row, list) or len(row) != len(self.columns) for row in rows):
                    raise MappingError('GOLD_MAP_ONTOLOGY_RESULT_SHAPE')
                return [tuple(row) for row in rows]

        @contextmanager
        def session(write=False):
            if write:
                raise MappingError('GOLD_MAP_ONTOLOGY_READ_ONLY')
            yield Cursor()

        repository.session = session
        return repository

    def source_reader(self, store, request):
        """Authoring uses the same verified Oracle originals as the RAG reader."""
        def read(anchor):
            from semantic_runtime.legal_agent.errors import ContractError
            did = anchor['document_id']
            if did not in request.sources.allowed:
                raise ContractError('source outside operator scope')
            document = request.sources.document(did)
            if document['source_artifact_sha256'] != anchor['version']:
                raise ContractError('source version changed')
            rows = store.db.execute('SELECT block_id FROM source_block WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER) LIMIT 4097',
                                    (did, anchor['unit_id'])).fetchall()
            if not rows or len(rows) > 4096:
                raise ContractError('source extent missing or oversized')
            texts = []
            length = 0
            for offset in range(0, len(rows), 100):
                batch = request.sources.sources(did, [str(r[0]) for r in rows[offset:offset+100]])
                for row in batch:
                    if str(row['unit_id']) != str(anchor['unit_id']):
                        raise ContractError('source unit changed')
                    texts.append(row['text'])
                    length += len(row['text']) + 1
                    if length > 160001:
                        raise ContractError('source text limit')
            return '\n'.join(texts)
        return read

    def glossary_binding(self, request):
        from engine_glossary import Glossary
        from semantic_runtime.ontology_work.glossary_binding import GlossaryBinding
        return GlossaryBinding(Glossary(request, {}), snapshot=request.snapshot.dataset_version)
