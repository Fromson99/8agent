"""Opt-in R12 data connector preview. No existing module or global is patched.

The maintained source/catalogue/fulltext readers consume read-only SQL
projections. This is not the production Dataiku publisher or service factory.
"""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re


class GoldError(ValueError):
    pass


class GoldConflict(GoldError):
    pass


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}', value):
        raise GoldError('GOLD_IDENTIFIER')
    return value


def unique_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise GoldError('GOLD_DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(GoldError('GOLD_JSON_NUMBER')))


# Preserve logical keys/hashes consumed by the existing runtime.
READ_COLUMNS = {
    'document': ('DOC_VER', dict(zip(
        'DATASET_VERSION DOCUMENT_ID NAME SOURCE_ARTIFACT_SHA256 SOURCE_JSON'.split(),
        'MNFST_HASH_VALU DOC_ID DOC_NAME DOC_HASH_VALU DOC_ADDN_IFMN_CTNT'.split()))),
    'source_unit': ('DOC_UNIT', dict(zip(
        'DATASET_VERSION DOCUMENT_ID UNIT_ID PARENT_ID SOURCE_JSON'.split(),
        'MNFST_HASH_VALU DOC_ID STRC_UNIT_ID UPPR_STRC_UNIT_ID STRC_UNIT_ADDN_IFMN_CTNT'.split()))),
    'block_payload': ('DOC_BLK', dict(zip(
        'DATASET_VERSION DOCUMENT_ID BLOCK_ID UNIT_ID TEXT SOURCE_ARTIFACT_SHA256 SOURCE_JSON JSON_TEXT_ELIDED'.split(),
        'MNFST_HASH_VALU DOC_ID BODY_SLC_ID STRC_UNIT_ID BODY_CTNT DOC_HASH_VALU BODY_SLC_ADDN_IFMN_CTNT ADD_INFO_TEXT_OMIT_YN'.split()))),
    'source_release': ('SRC_POST', dict(zip(
        'RELEASE_ID DATASET_VERSION RELEASE_JSON CREATED_AT'.split(),
        'DOC_POST_HASH_VALU MNFST_HASH_VALU DOC_POST_IFMN_CTNT RGSN_AITM'.split()))),
    'query_release': ('SRCH_POST', {'RELEASE_ID': 'RFRN_POST_HASH_VALU', 'MANIFEST_JSON': 'RFRN_POST_IFMN_CTNT'}),
    'query_row': ('SRCH_ROW', dict(zip(
        'RELEASE_ID KIND ROW_ID DOCUMENT_ID LOOKUP_ID OWNER_ID TARGET_ID ROW_SHA256 VALUE_JSON'.split(),
        'RFRN_POST_HASH_VALU RFRN_DTA_TYPE_VALU RFRN_DTA_ID DOC_ID RFRN_DTA_IDNF_CTNT BLNG_DTA_IDNF_CTNT TAGT_DTA_IDNF_CTNT SRCH_DATA_HASH_VALU SRCH_DATA_CTNT'.split()))),
    'query_active': ('SRCH_CHNL', dict(zip(
        'CHANNEL RELEASE_ID REVISION'.split(), 'RFRN_CHNL_NAME RFRN_POST_HASH_VALU CHAN_NO'.split()))),
}


@dataclass(frozen=True)
class ReadNames:
    table: str
    columns: tuple

    def c(self, name):
        if name not in self.columns:
            raise GoldError('GOLD_LOGICAL_COLUMN')
        return identifier(name)

    def select(self, *columns):
        return ','.join(self.c(column) for column in columns)


@dataclass(frozen=True)
class GoldConfig:
    owner: str
    variant: str
    model: dict
    model_sha256: str

    @classmethod
    def load(cls, path, root, *, example_owner=None):
        value = unique_json(Path(path).read_text())
        if set(value) != {'schema_version', 'owner', 'variant', 'model_path', 'model_sha256'}:
            raise GoldError('GOLD_CONFIG_FIELDS')
        if value['schema_version'] != 'gold-connection-r12-preview-v1' or value['variant'] not in ('B03', 'B05'):
            raise GoldError('GOLD_CONFIG_VERSION')
        root = Path(root).resolve()
        model_path = (root/value['model_path']).resolve()
        model_path.relative_to(root)
        raw = model_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != value['model_sha256']:
            raise GoldError('GOLD_MODEL_HASH')
        model = unique_json(raw)
        if len(model['tables']) != 13 or sum(len(t['columns']) for t in model['tables']) != 60:
            raise GoldError('GOLD_MODEL_SHAPE')
        return cls(identifier(example_owner or value['owner']), value['variant'], model, value['model_sha256'])

    def table(self, suffix):
        if suffix not in {t['suffix'] for t in self.model['tables']}:
            raise GoldError('GOLD_TABLE')
        return self.owner+'.'+identifier('IDD_'+self.variant+'_LGL_'+suffix)

    def names(self, key):
        # Agent journals/asset archives deliberately have no Gold fallback.
        if key not in READ_COLUMNS:
            raise GoldError('GOLD_UNSUPPORTED_PORT: '+key)
        suffix, columns = READ_COLUMNS[key]
        expressions = []
        for logical, physical in columns.items():
            expression = physical
            if key == 'document' and logical == 'NAME':
                expression = 'TO_CLOB('+physical+')'
            if logical == 'JSON_TEXT_ELIDED':
                expression = ("CASE WHEN "+physical+" IS NULL THEN NULL WHEN "+physical+
                              "='Y' THEN 1 WHEN "+physical+"='N' THEN 0 ELSE 2 END")
            expressions.append(expression+' AS '+logical)
        return ReadNames('(SELECT '+','.join(expressions)+' FROM '+self.table(suffix)+')', tuple(columns))

    def ddl(self):
        # This is generated from the exact hash-pinned R12 model, not a relaxed mock.
        statements = []
        for table in self.model['tables']:
            qualified = self.table(table['suffix'])
            name = qualified.split('.')[1]
            fields = []
            for column in table['columns']:
                fields.append(column['name']+' '+column['type']+
                              (' DEFAULT '+column['default'] if column.get('default') else '')+
                              (' NOT NULL' if column['required'] else ''))
            pk = [c['name'] for c in sorted(table['columns'], key=lambda c: c['pk']) if c['pk']]
            fields.append('CONSTRAINT X0_'+name+' PRIMARY KEY ('+','.join(pk)+')')
            statements.append('CREATE TABLE '+qualified+' (\n  '+',\n  '.join(fields)+'\n)')
            for number, columns in enumerate(table['indexes'], 1):
                statements.append('CREATE INDEX '+self.owner+'.X'+str(number)+'_'+name+
                                  ' ON '+qualified+' ('+','.join(columns)+')')
        return statements


class LocalReadTransport:
    """Local DB-API bridge for existing read-only ORDS readers; no network API mock SQL."""
    SQL_PATH = '/local-r12-contract'

    def __init__(self, connection, config):
        self.connection, self.schema_map = connection, config
        self.statements = []

    def request(self, method, path, json):
        import oracledb
        if (method, path) != ('POST', self.SQL_PATH) or not json['statementText'].lstrip().upper().startswith('SELECT '):
            raise GoldError('GOLD_READ_ONLY')
        self.statements.append(json['statementText'])
        types = {'CLOB': oracledb.DB_TYPE_CLOB, 'VARCHAR2': oracledb.DB_TYPE_VARCHAR, 'NUMBER': oracledb.DB_TYPE_NUMBER}
        binds = json.get('binds', [])
        with self.connection.cursor() as cursor:
            cursor.setinputsizes(**{b['name']: types[b['data_type']] for b in binds})
            cursor.execute(json['statementText'], {b['name']: b['value'] for b in binds})
            names = [c[0] for c in cursor.description]
            rows = cursor.fetchmany(json['limit']+1)
            values = [{k: v.read() if isinstance(v, oracledb.LOB) else v for k, v in zip(names, row)} for row in rows[:json['limit']]]
            return {'items': [{'resultSet': {'offset': 0, 'hasMore': len(rows) > json['limit'], 'items': values}}]}


def rewrite_reads(statement, config):
    """Replace only known FROM/JOIN tokens; retain Oracle JSON_TABLE syntax exactly.

    sqlglot's Oracle parser in the local runtime rejects ERROR ON ERROR in
    JSON_TABLE. Its tokenizer still recognizes the immutable table tokens.
    This is a narrow port for maintained SQL, not a general user-SQL endpoint.
    """
    from sqlglot import tokenize
    from semantic_runtime.oracle_silver_reads import LEGACY
    tokens = tokenize(statement, read='oracle')
    replacements = []
    for index in range(1, len(tokens)-2):
        token, dot, table = tokens[index:index+3]
        name = token.text.upper()+'.'+table.text.upper()
        if dot.text != '.' or name not in LEGACY:
            continue
        if tokens[index-1].text.upper() not in ('FROM', 'JOIN', ','):
            raise GoldError('GOLD_UNSUPPORTED_SQL_REFERENCE')
        replacements.append((token.start, table.end+1, config.names(LEGACY[name]).table))
    for start, end, value in reversed(replacements):
        statement = statement[:start]+value+statement[end:]
    return statement


def open_gold_request(connection, config, *, document_ids, channel='demo', seconds=60):
    """Use an isolated client; the existing module and service defaults are untouched."""
    import time
    from semantic_runtime.oracle_query_request import _request
    from semantic_runtime.oracle_query import QuerySQL, Snapshot
    from semantic_runtime.oracle_query_catalog import select_release
    from semantic_runtime.oracle_dp_io import digest, SQL
    class GoldSQL(QuerySQL):
        def query(self, statement, binds=(), *, limit=100):
            return SQL.query(self, rewrite_reads(statement, config), binds, limit=limit)
    client = LocalReadTransport(connection, config)
    sql = GoldSQL(client, binding=digest({'owner': config.owner, 'variant': config.variant,
                  'model': config.model_sha256}), deadline=time.monotonic()+seconds)
    selected = select_release(sql, channel=channel)
    manifest = selected['manifest']
    snapshot = Snapshot.open(sql, manifest['source_release_id'])
    if (manifest['dataset_version'] != snapshot.dataset_version or manifest['source_manifest'] != snapshot.manifest or
        'source.integrity' not in manifest['tables']):
        raise GoldError('GOLD_SOURCE_BINDING')
    request = _request(sql, selected['release_id'], selected['revision'], snapshot, manifest, document_ids)
    return request, client


class VectorReader:
    """R12 native exact vector retrieval over a pinned query and authorized documents."""
    def __init__(self, request, config):
        self.request, self.config = request, config

    def active(self):
        rows = self.request.sql.query('SELECT VCTR_POST_ID,CHAN_NO FROM '+self.config.table('VCTR_HEAD')+
                                      ' WHERE RFRN_POST_HASH_VALU=:q', [('q', self.request.release_id, 'VARCHAR2')], limit=1)
        if not rows or rows[0]['VCTR_POST_ID'] is None:
            return None
        row = rows[0]
        if type(row['CHAN_NO']) is not int or row['CHAN_NO'] < 1:
            raise GoldError('GOLD_VECTOR_REVISION')
        return row

    def metadata(self, publication_id):
        from semantic_runtime.oracle_dp_io import digest
        rows = self.request.sql.query('SELECT VCTR_POST_IFMN_CTNT FROM '+self.config.table('VCTR_POST')+
                                      ' WHERE VCTR_POST_ID=:p', [('p', publication_id, 'VARCHAR2')], limit=1)
        if len(rows) != 1:
            raise GoldError('GOLD_VECTOR_UNSEALED')
        envelope = unique_json(rows[0]['VCTR_POST_IFMN_CTNT'])
        if set(envelope) != {'manifest', 'completion'}:
            raise GoldError('GOLD_VECTOR_ENVELOPE')
        manifest, completion = envelope['manifest'], envelope['completion']
        if (digest(manifest) != publication_id or manifest['query_id'] != self.request.release_id or
            manifest['source_release_id'] != self.request.snapshot.release_id or
            manifest['dataset_version'] != self.request.snapshot.dataset_version or
            completion['profile_sha256'] != digest(manifest['profile']) or completion['status'] != 'READY' or
            type(completion['count']) is not int or completion['count'] < 1):
            raise GoldError('GOLD_VECTOR_BINDING')
        return envelope

    def search(self, vector, *, profile_sha256, documents=None, limit=20):
        from semantic_runtime.oracle_dp_io import digest
        active = self.active()
        if active is None:
            raise GoldError('GOLD_VECTOR_DISABLED')
        envelope = self.metadata(active['VCTR_POST_ID'])
        profile = envelope['manifest']['profile']
        if (digest(profile) != profile_sha256 or profile['metric'] != 'COSINE' or
            profile['normalization'] != 'l2' or len(vector) != profile['dimensions'] or
            any(type(x) not in (int, float) or not math.isfinite(x) for x in vector)):
            raise GoldError('GOLD_VECTOR_PROFILE')
        norm = math.sqrt(sum(x*x for x in vector))
        if not math.isfinite(norm) or norm <= 0:
            raise GoldError('GOLD_VECTOR_VALUE')
        if type(limit) is not int or not 1 <= limit <= 100:
            raise GoldError('GOLD_VECTOR_LIMIT')
        allowed = self.request.sources.allowed
        selected = allowed if documents is None else frozenset(documents)
        if not selected <= allowed:
            raise GoldError('GOLD_VECTOR_SCOPE')
        if not selected:
            return []
        parameters = [('p', active['VCTR_POST_ID'], 'VARCHAR2'),
                      ('v', json.dumps([x/norm for x in vector]), 'CLOB'),
                      ('docs', json.dumps(sorted(selected)), 'CLOB')]
        # Group before top-k; the SQL returns only caller-authorized documents.
        statement = ('SELECT DOC_ID,SRC_UNIT_ID,MIN(VECTOR_DISTANCE(EMBD_VCTR_VALU,TO_VECTOR(:v),COSINE)) AS DISTANCE FROM '+
                     self.config.table('VCTR_ITEM')+" WHERE VCTR_POST_ID=:p AND DOC_ID IN (SELECT j.did FROM "
                     "JSON_TABLE(:docs,'$[*]' COLUMNS(did VARCHAR2(1000) PATH '$')) j) GROUP BY DOC_ID,SRC_UNIT_ID "
                     'ORDER BY DISTANCE,DOC_ID,SRC_UNIT_ID FETCH FIRST '+str(limit)+' ROWS ONLY')
        return self.request.sql.query(statement, parameters, limit=limit)


def change_vector_head(connection, config, reader, publication_id, *, previous, revision):
    """Short CAS for this preview. A production publisher still needs writer fencing."""
    if type(revision) is not int or revision < 0:
        raise GoldError('GOLD_HEAD_REVISION')
    if publication_id is not None:
        reader.metadata(publication_id)
    table = config.table('VCTR_HEAD')
    import oracledb
    try:
        with connection.cursor() as cursor:
            if revision == 0:
                if previous is not None:
                    raise GoldConflict('GOLD_HEAD_CONFLICT')
                cursor.execute('INSERT INTO '+table+' VALUES(:q,:p,1)', q=reader.request.release_id, p=publication_id)
            else:
                cursor.execute('UPDATE '+table+' SET VCTR_POST_ID=:p,CHAN_NO=CHAN_NO+1 WHERE RFRN_POST_HASH_VALU=:q '
                               'AND CHAN_NO=:r AND (VCTR_POST_ID=:old OR (VCTR_POST_ID IS NULL AND :old IS NULL))',
                               p=publication_id, q=reader.request.release_id, r=revision, old=previous)
                if cursor.rowcount != 1:
                    raise GoldConflict('GOLD_HEAD_CONFLICT')
        connection.commit()
    except oracledb.DatabaseError as exc:
        connection.rollback()
        if exc.args[0].code == 1:
            raise GoldConflict('GOLD_HEAD_CONFLICT') from exc
        raise
    except BaseException:
        connection.rollback()
        raise
