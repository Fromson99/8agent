"""Explicit G19 suffix-1 read/record ports for the existing Oracle DP.

The immutable ingestion contract is code, not a SQL/DDL instruction source.
Original row keys, hashes and publication identities remain unchanged.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from .physical_mapping import Names, MappingError, identifier, _freeze, digest

PORTS = {
    'document': ('DOC_VER', 'DATASET_VERSION DOCUMENT_ID NAME SOURCE_ARTIFACT_SHA256 SOURCE_JSON'),
    'source_unit': ('DOC_UNIT', 'DATASET_VERSION DOCUMENT_ID UNIT_ID PARENT_ID SOURCE_JSON'),
    'block_payload': ('DOC_BLK', 'DATASET_VERSION DOCUMENT_ID BLOCK_ID UNIT_ID TEXT SOURCE_ARTIFACT_SHA256 SOURCE_JSON JSON_TEXT_ELIDED'),
    'source_release': ('SRC_POST', 'RELEASE_ID DATASET_VERSION RELEASE_JSON CREATED_AT'),
    'query_release': ('SRCH_POST', 'RELEASE_ID MANIFEST_JSON'),
    'query_row': ('SRCH_ROW', 'RELEASE_ID KIND ROW_ID DOCUMENT_ID LOOKUP_ID OWNER_ID TARGET_ID ROW_SHA256 VALUE_JSON'),
    'query_active': ('SRCH_CHNL', 'CHANNEL RELEASE_ID REVISION'),
}
LOGICAL = {'DOC_VER': 'MNFST_HASH_VALU DOC_ID DOC_NAME DOC_HASH_VALU DOC_ADDN_IFMN_CTNT', 'DOC_UNIT': 'MNFST_HASH_VALU DOC_ID STRC_UNIT_ID UPPR_STRC_UNIT_ID STRC_UNIT_ADDN_IFMN_CTNT', 'DOC_BLK': 'MNFST_HASH_VALU DOC_ID BODY_SLC_ID STRC_UNIT_ID BODY_CTNT DOC_HASH_VALU BODY_SLC_ADDN_IFMN_CTNT ADD_INFO_TEXT_OMIT_YN', 'SRC_POST': 'DOC_POST_HASH_VALU MNFST_HASH_VALU DOC_POST_IFMN_CTNT RGSN_AITM', 'SRCH_POST': 'RFRN_POST_HASH_VALU RFRN_POST_IFMN_CTNT', 'SRCH_ROW': 'RFRN_POST_HASH_VALU RFRN_DTA_TYPE_VALU RFRN_DTA_ID DOC_ID RFRN_DTA_IDNF_CTNT BLNG_DTA_IDNF_CTNT TAGT_DTA_IDNF_CTNT SRCH_DATA_HASH_VALU SRCH_DATA_CTNT', 'SRCH_CHNL': 'RFRN_CHNL_NAME RFRN_POST_HASH_VALU CHAN_NO'}
AGENTS = {'body': 'AGT_BODY', 'record': 'AGT_REC', 'run': 'AGT_RUN', 'state': 'EXEC_ST'}


@dataclass(frozen=True)
class DevelopmentMapping:
    tables: object
    file_sha256: str
    target_sha256: str
    profile: str = 'development_g19_1'

    @classmethod
    def load(cls, path=None):
        path = path or Path(__file__).resolve().parents[2] / '00_SYSTEM/ORACLE/development_g19_1.json'
        raw = Path(path).read_bytes()
        value = json.loads(raw)
        tables = value['tables']
        if value['version'] != 'gold-development-fresh-suffix-1-20261102-r1' or len(tables) != 17:
            raise MappingError('DEV_G19_CONTRACT')
        for key, table in tables.items():
            identifier(table['owner']); identifier(table['name'])
            if not table['name'].endswith('_1'):
                raise MappingError('DEV_G19_SUFFIX')
            for column in table['columns'].values():
                identifier(column['name'])
        for key, (table, aliases) in PORTS.items():
            if set(tables[table]['columns']) != set(LOGICAL[table].split()):
                raise MappingError('DEV_G19_COLUMNS: ' + key)
        return cls(_freeze(tables), hashlib.sha256(raw).hexdigest(), digest(tables))

    def physical_table(self, key):
        table = self.tables[key]
        return table['owner'] + '.' + table['name']

    @property
    def agent_tables(self):
        return MappingProxyType({name: self.physical_table(key) for name, key in AGENTS.items()})

    def names(self, key):
        if key == 'query_state':
            return Names(self.physical_table('EXEC_ST'), MappingProxyType(dict(zip(
                'SCOPE_HASH STATE_KEY REVISION VALUE_SHA256 VALUE_JSON'.split(),
                (self.tables['EXEC_ST']['columns'][name]['name'] for name in 'SCOPE_HASH_VAL ST_KEY_ID CHG_SEQ_NO ST_HASH_VAL ST_JSON_CN'.split())))))
        if key not in PORTS:
            raise MappingError('DEV_G19_UNSUPPORTED_PORT: ' + key)
        table, aliases = PORTS[key]
        fields = []
        for alias, logical in zip(aliases.split(), LOGICAL[table].split()):
            expression = self.tables[table]['columns'][logical]['name']
            if key == 'document' and alias == 'NAME':
                expression = 'TO_CLOB(' + expression + ')'
            if alias == 'JSON_TEXT_ELIDED':
                expression = (f"CASE WHEN {expression} IS NULL THEN NULL WHEN {expression}='Y' THEN 1 "
                              f"WHEN {expression}='N' THEN 0 ELSE 2 END")
            fields.append(expression + ' AS ' + alias)
        return Names('(SELECT ' + ','.join(fields) + ' FROM ' + self.physical_table(table) + ')')

    def preflight(self, sql):
        """Only metadata SELECTs; reject missing/changed columns before requests."""
        for key, table in self.tables.items():
            rows = sql.query('SELECT COLUMN_NAME,DATA_TYPE,DATA_LENGTH,CHAR_USED,DATA_PRECISION,DATA_SCALE,NULLABLE '
                             'FROM ALL_TAB_COLUMNS WHERE OWNER=:o AND TABLE_NAME=:t ORDER BY COLUMN_ID',
                             [('o', table['owner'], 'VARCHAR2'), ('t', table['name'], 'VARCHAR2')], limit=100)
            columns = {row['COLUMN_NAME']: row for row in rows}
            if set(columns) != {c['name'] for c in table['columns'].values()}:
                raise MappingError('DEV_G19_SCHEMA_COLUMNS: ' + self.physical_table(key))
            for column in table['columns'].values():
                row = columns[column['name']]; typ = column['type']
                import re
                if typ.startswith(('VARCHAR2', 'CHAR')):
                    good = row['DATA_TYPE'] == typ.split('(')[0] and row['DATA_LENGTH'] == int(re.search(r'\((\d+)', typ)[1]) and row['CHAR_USED'] == 'B'
                elif typ.startswith('NUMBER'):
                    good = row['DATA_TYPE'] == 'NUMBER' and row['DATA_PRECISION'] == int(re.search(r'\((\d+)', typ)[1]) and row['DATA_SCALE'] == 0
                elif typ.startswith('TIMESTAMP'):
                    good = row['DATA_TYPE'] in ('TIMESTAMP(6) WITH TIME ZONE', 'TIMESTAMP WITH TIME ZONE') and row['DATA_SCALE'] == 6
                else:
                    good = row['DATA_TYPE'] == ('VECTOR' if typ.startswith('VECTOR') else typ)
                if not good or row['NULLABLE'] != ('N' if column['required'] else 'Y'):
                    raise MappingError('DEV_G19_SCHEMA_TYPE: ' + self.physical_table(key) + '.' + column['name'])
        return {'profile': self.profile, 'tables': len(self.tables), 'mapping_sha256': self.file_sha256}
