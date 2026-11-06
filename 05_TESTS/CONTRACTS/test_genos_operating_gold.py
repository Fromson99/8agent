"""Serving must match the separately shipped operating loader, not its own fixture."""
import json
from pathlib import Path

import pytest

from semantic_runtime.oracle_gold_mapping import GoldMapping
from semantic_runtime.oracle_development_mapping import DevelopmentMapping
from semantic_runtime.physical_mapping import MappingError
from test_genos_gold_mapping import metadata


def test_thirteen_gold_tables_match_operating_r5_registration():
    registration = json.loads((Path(__file__).resolve().parents[2] /
        '08_DEPLOYMENT/DATAIKU/gold_oneclick_prod_20261105_r5/package/registration_current.json').read_text())
    mapping = GoldMapping.load(owner='APP_GOLD')
    for key, expected in registration['tables'].items():
        actual = mapping.tables[key]
        assert actual['name'] == expected['name']
        assert dict(actual['columns']) == expected['columns']
        assert list(actual['primary_key']) == expected['primary_key']
    assert 'RFRN_DTA_CTNT AS VALUE_JSON' in mapping.names('query_row').table


def registration_row(mapping):
    rows, sql, calls = metadata(mapping)
    table = mapping.tables['SRC_POST']
    row = next(r for r in rows[(table['owner'], table['name'])]
               if r['COLUMN_NAME'] == table['columns']['RGSN_AITM']['name'])
    return row, sql, calls


@pytest.mark.parametrize('precision', [0, 3, 6, 9])
@pytest.mark.parametrize('nullable', ['Y', 'N'])
def test_only_gold_registration_accepts_loader_plain_timestamp(precision, nullable):
    mapping = GoldMapping.load(owner='APP_GOLD')
    row, sql, calls = registration_row(mapping)
    row.update(DATA_TYPE=f'TIMESTAMP({precision})', DATA_SCALE=precision, NULLABLE=nullable)
    assert mapping.preflight(sql)['tables'] == len(calls) == 17
    development = DevelopmentMapping.load()
    row, sql, _ = registration_row(development)
    row.update(DATA_TYPE=f'TIMESTAMP({precision})', DATA_SCALE=precision, NULLABLE=nullable)
    with pytest.raises(MappingError, match='DEV_G19_SCHEMA_TYPE'):
        development.preflight(sql)


@pytest.mark.parametrize('typ,scale,nullable', [
    ('DATE', None, 'Y'), ('VARCHAR2', None, 'Y'),
    ('TIMESTAMP(6) WITH LOCAL TIME ZONE', 6, 'N'),
    ('TIMESTAMP(3) WITH TIME ZONE', 3, 'N'),
    ('TIMESTAMP(6) WITH TIME ZONE', 6, 'Y'),
    ('TIMESTAMP(6)', 3, 'Y'), ('TIMESTAMP(6)', 6, '?'),
])
def test_registration_unsupported_metadata_stays_rejected(typ, scale, nullable):
    mapping = GoldMapping.load(owner='APP_GOLD')
    row, sql, _ = registration_row(mapping)
    row.update(DATA_TYPE=typ, DATA_SCALE=scale, NULLABLE=nullable)
    with pytest.raises(MappingError, match='GOLD_B003_SCHEMA_TYPE: APP_GOLD.IDD_B003_LGL_SRC_POST.RGSN_ASTM'):
        mapping.preflight(sql)


def test_agent_timestamps_are_not_relaxed_by_gold_compatibility():
    mapping = GoldMapping.load(owner='APP_GOLD')
    rows, sql, _ = metadata(mapping)
    changed = 0
    for key in ('AGT_BODY', 'AGT_REC', 'AGT_RUN', 'EXEC_ST'):
        table = mapping.tables[key]
        for c in table['columns'].values():
            if c['type'].startswith('TIMESTAMP'):
                row = next(r for r in rows[(table['owner'], table['name'])] if r['COLUMN_NAME'] == c['name'])
                old = dict(row)
                row.update(DATA_TYPE='TIMESTAMP(6)', DATA_SCALE=6)
                with pytest.raises(MappingError, match='GOLD_B003_SCHEMA_TYPE: SIDDA.'):
                    mapping.preflight(sql)
                row.update(old)
                changed += 1
    assert changed > 0


@pytest.mark.parametrize('mismatch', ['old_flag_type', 'old_search_names', 'old_vector_length', 'char_semantics', 'hidden_agent'])
def test_operating_mismatch_does_not_fallback_or_write(mismatch):
    mapping = GoldMapping.load(owner='APP_GOLD')
    rows, sql, calls = metadata(mapping)
    if mismatch == 'hidden_agent':
        rows[('SIDDA', 'LGL_AGT_BODY_A')] = []
    else:
        key, name = {'old_flag_type': ('DOC_BLK', 'ADDN_IFMN_UN_APPN_YN'),
            'old_search_names': ('SRCH_ROW', 'RFRN_DTA_CTNT'),
            'old_vector_length': ('VCTR_ITEM', 'BODY_UNIT_ID'),
            'char_semantics': ('VCTR_ITEM', 'BODY_UNIT_ID')}[mismatch]
        row = next(r for r in rows[('APP_GOLD', 'IDD_B003_LGL_'+key)] if r['COLUMN_NAME'] == name)
        if mismatch == 'old_flag_type': row['DATA_TYPE'] = 'CHAR'
        elif mismatch == 'old_search_names': row['COLUMN_NAME'] = 'RFRN_DATA_CTNT'
        elif mismatch == 'old_vector_length': row['DATA_LENGTH'] = 50
        else: row['CHAR_USED'] = 'C'
    with pytest.raises(MappingError, match='GOLD_B003_SCHEMA_'):
        mapping.preflight(sql)
    assert all(t.startswith('IDD_B003_LGL_') or t.endswith('_A') for _, t in calls)
