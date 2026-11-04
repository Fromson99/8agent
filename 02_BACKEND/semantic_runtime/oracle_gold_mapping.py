"""Explicit B003 R5 data tables over the existing GENOS ORDS transport.

Gold contains the thirteen published data tables. The existing four SIDDA
Agent A_1 tables continue to own mutable request records and state.
"""
import hashlib
import json
from pathlib import Path
import re

from .oracle_development_mapping import DevelopmentMapping, AGENTS
from .physical_mapping import MappingError, identifier, _freeze, digest
from .oracle_dp_io import DPError


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MappingError('GOLD_B003_DUPLICATE_KEY')
        result[key] = value
    return result


class GoldMapping(DevelopmentMapping):
    schema_error_prefix = 'GOLD_B003'

    @classmethod
    def load(cls, path=None, *, owner):
        if not isinstance(owner, str) or not owner.strip():
            raise DPError('DP_CONFIG: gold requires GENOS_ORACLE_GOLD_OWNER')
        try:
            owner = identifier(owner.strip())
        except MappingError as exc:
            raise DPError('DP_CONFIG: GENOS_ORACLE_GOLD_OWNER must be an uppercase Oracle schema identifier') from exc
        path = path or Path(__file__).resolve().parents[2] / '00_SYSTEM/ORACLE/gold_b003_r5.json'
        raw = Path(path).read_bytes()
        if len(raw) > 1024 * 1024:
            raise MappingError('GOLD_B003_SIZE')
        value = json.loads(raw, object_pairs_hook=unique_pairs)
        if (set(value) != {'schema_version', 'revision', 'owner', 'variant', 'tables'}
                or value['schema_version'] != 'gold-physical-map-v1'
                or value['revision'] != '20261104-b003-chan-no-registration-r5'
                or value['variant'] != 'B003' or value['owner'] is not None):
            raise MappingError('GOLD_B003_CONTRACT')
        development = DevelopmentMapping.load()
        gold_keys = set(development.tables) - set(AGENTS.values())
        if set(value['tables']) != gold_keys:
            raise MappingError('GOLD_B003_TABLES')
        tables = {}
        for key, table in value['tables'].items():
            if (set(table) != {'name', 'columns', 'primary_key', 'indexes'}
                    or table['name'] != 'IDD_B003_LGL_' + key
                    or set(table['columns']) != set(development.tables[key]['columns'])):
                raise MappingError('GOLD_B003_TABLE: ' + key)
            identifier(table['name'])
            names = set()
            for column in table['columns'].values():
                if set(column) != {'name', 'type', 'required', 'default'}:
                    raise MappingError('GOLD_B003_COLUMN')
                name = identifier(column['name'])
                if name in names:
                    raise MappingError('GOLD_B003_COLUMN_COLLISION')
                names.add(name)
                if (not re.fullmatch(r'(?:VARCHAR2\([1-9][0-9]{0,3} BYTE\)|CHAR\(1 BYTE\)|NUMBER\([1-9][0-9]?,0\)|CLOB|TIMESTAMP\(6\) WITH TIME ZONE|VECTOR\(\*,FLOAT32\))', column['type'])
                        or type(column['required']) is not bool
                        or column['default'] not in (None, 'SYSTIMESTAMP')
                        or column['default'] and column['type'] != 'TIMESTAMP(6) WITH TIME ZONE'):
                    raise MappingError('GOLD_B003_COLUMN_CONTRACT')
            for columns in [table['primary_key'], *table['indexes']]:
                if not columns or len(columns) != len(set(columns)) or not set(columns) <= table['columns'].keys():
                    raise MappingError('GOLD_B003_KEY')
            tables[key] = {**table, 'owner': owner}
        for key in AGENTS.values():
            table = development.tables[key]
            tables[key] = {'owner': table['owner'], 'name': table['name'],
                           'columns': {k: dict(v) for k, v in table['columns'].items()},
                           'primary_key': list(table['primary_key'])}
        return cls(_freeze(tables), hashlib.sha256(raw).hexdigest(), digest(tables), profile='gold')

    def ontology_repository(self, request, glossary):
        from .oracle_gold_ontology import repository
        return repository(self, request, glossary)
