import copy
import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE/'package'), str(HERE/'package/engine')]
from gold_io import Contract, Stop
from prod_run import configure


def params():
    return {'CODE_FOLDER_ID':'existing', 'INPUT_FOLDER_ID':'', 'ORACLE_CONNECTION':'AIDP',
            'EXPECTED_DB_USER':'PIDD2APP', 'GOLD_OWNER':'SIDDS',
            'TABLE_PREFIX':'IDD_B003_LGL_', 'TABLE_NAMES':{}, 'EMBED_MODEL':'stub',
            'EMBED_DIMENSIONS':4, 'WORK_DIR':''}


def placed_contract(tmp_path, *, previous=False, cls=Contract):
    cfg, _ = configure(params(), 'LEGAL_RAG')
    target = cfg['target']
    if previous:
        old = json.loads((HERE.parent/'gold_oneclick_prod_20261104_r1/package/registration_current.json').read_text())
        target['tables']['DOC_BLK']['columns'] = old['tables']['DOC_BLK']['columns']
    path = tmp_path/('old.json' if previous else 'new.json')
    path.write_text(json.dumps(target))
    return cls(path)


def column_rows(table):
    rows = []
    for column in table['columns'].values():
        typ = column['type']
        row = {'COLUMN_NAME':column['name'], 'DATA_TYPE':typ.split('(')[0],
               'DATA_LENGTH':4000, 'CHAR_USED':None, 'DATA_PRECISION':None,
               'DATA_SCALE':None, 'NULLABLE':'N' if column['required'] else 'Y',
               'DATA_DEFAULT':column['default']}
        if typ.startswith(('CHAR(', 'VARCHAR2(')):
            row.update(DATA_LENGTH=int(typ.split('(')[1].split()[0]), CHAR_USED='B')
        rows.append(row)
    return rows


class Metadata:
    def __init__(self, table, changes):
        self.table = table
        self.rows = column_rows(table)
        if changes:
            target = next(r for r in self.rows if r['COLUMN_NAME']=='ADDN_IFMN_UN_APPN_YN')
            target.update(changes)
        self.calls = []

    def query(self, sql):
        assert sql.startswith('SELECT ')
        self.calls.append(sql)
        if 'FROM ALL_TAB_COLUMNS' in sql:
            return self.rows
        if 'FROM ALL_CONSTRAINTS' in sql:
            return [{'COLUMN_NAME':self.table['columns'][key]['name'],
                     'STATUS':'ENABLED', 'VALIDATED':'VALIDATED'}
                    for key in self.table['primary_key']]
        if 'FROM ALL_TRIGGERS' in sql:
            return []
        raise AssertionError(sql)

    def block(self, *args, **kwargs):
        raise AssertionError('metadata check must not write')


def test_exact_two_physical_names_changed_and_separate_workspace():
    old = json.loads((HERE.parent/'gold_oneclick_prod_20261104_r2/package/registration_current.json').read_text())
    new = json.loads((HERE/'package/registration_current.json').read_text())
    expected = copy.deepcopy(old)
    expected['tables']['SRCH_ROW']['columns']['SRCH_DATA_HASH_VALU']['name'] = 'RFRN_DTA_HASH_VALU'
    expected['tables']['SRCH_ROW']['columns']['SRCH_DATA_CTNT']['name'] = 'RFRN_DTA_CTNT'
    assert new == expected
    assert new['tables']['DOC_BLK']['columns']['ADD_INFO_TEXT_OMIT_YN']['type'] == 'VARCHAR2(1 BYTE)'
    import prod_config
    current, new_root = configure(params(), 'LEGAL_RAG')
    # Run the unchanged configuration function against the actual R2 registration.
    original_root = prod_config.ROOT
    try:
        prod_config.ROOT = HERE.parent/'gold_oneclick_prod_20261104_r2/package'
        previous, old_root = configure(params(), 'LEGAL_RAG')
    finally:
        prod_config.ROOT = original_root
    assert current['storage'] != previous['storage'] and new_root != old_root


def test_r1_reproduces_failure_and_r3_retains_registered_varchar(tmp_path):
    old = placed_contract(tmp_path, previous=True)
    new = placed_contract(tmp_path)
    db = Metadata(new.tables['DOC_BLK'], {})
    with pytest.raises(Stop, match='TYPE_MISMATCH:.*ADDN_IFMN_UN_APPN_YN'):
        old.preflight(db, 'DOC_BLK')
    new.preflight(db, 'DOC_BLK')


@pytest.mark.parametrize('changes', [
    {'DATA_TYPE':'CHAR'}, {'DATA_LENGTH':2}, {'CHAR_USED':'C'},
    {'NULLABLE':'N'}, {'DATA_DEFAULT':"'N'"},
])
def test_other_column_mismatches_still_rejected(changes, tmp_path):
    contract = placed_contract(tmp_path)
    with pytest.raises(Stop, match='TYPE_MISMATCH:.*ADDN_IFMN_UN_APPN_YN'):
        contract.preflight(Metadata(contract.tables['DOC_BLK'], changes), 'DOC_BLK')


@pytest.mark.parametrize('value', ['Y', 'N', None])
def test_flag_values_preserved_in_insert(value, tmp_path):
    from prod_pipeline import Contract as ProductionContract
    contract = placed_contract(tmp_path, cls=ProductionContract)
    row = {key:'test' for key in contract.tables['DOC_BLK']['primary_key']}
    row['ADD_INFO_TEXT_OMIT_YN'] = value
    sql, binds = contract.batch('DOC_BLK', [row])
    assert 'VARCHAR2(1 BYTE)' in sql and 'ADDN_IFMN_UN_APPN_YN' in sql
    names = list(contract.tables['DOC_BLK']['columns'])
    payload = json.loads(binds[0][1])
    assert payload[0]['c'+str(names.index('ADD_INFO_TEXT_OMIT_YN'))] == value
    with pytest.raises(Stop, match='ROW_BYTE_LENGTH_OR_EMPTY'):
        contract.batch('DOC_BLK', [dict(row, ADD_INFO_TEXT_OMIT_YN='NN')])


def test_r2_reproduces_search_columns_failure_and_r3_accepts_photo_names(tmp_path):
    new = placed_contract(tmp_path)
    old_value = copy.deepcopy(new.value)
    old = json.loads((HERE.parent/'gold_oneclick_prod_20261104_r2/package/registration_current.json').read_text())
    old_value['tables']['SRCH_ROW']['columns'] = old['tables']['SRCH_ROW']['columns']
    old_path = tmp_path/'r2.json'
    old_path.write_text(json.dumps(old_value))
    db = Metadata(new.tables['SRCH_ROW'], {})
    with pytest.raises(Stop, match='COLUMNS_MISMATCH:.*SRCH_ROW'):
        Contract(old_path).preflight(db, 'SRCH_ROW')
    new.preflight(db, 'SRCH_ROW')


def test_search_insert_preserves_hash_and_content_under_new_names(tmp_path):
    from prod_pipeline import Contract as ProductionContract
    contract = placed_contract(tmp_path, cls=ProductionContract)
    row = {'RFRN_POST_HASH_VALU':'post', 'RFRN_DTA_TYPE_VALU':'kind', 'RFRN_DTA_ID':'id',
           'SRCH_DATA_HASH_VALU':'a'*64, 'SRCH_DATA_CTNT':'한글 원문 그대로'}
    sql, binds = contract.batch('SRCH_ROW', [row])
    assert 'RFRN_DTA_HASH_VALU' in sql and 'RFRN_DTA_CTNT' in sql
    assert 'RFRN_DATA_HASH_VALU' not in sql and 'RFRN_DATA_CTNT' not in sql
    columns = list(contract.tables['SRCH_ROW']['columns'])
    payload = json.loads(binds[0][1])[0]
    for key in ('SRCH_DATA_HASH_VALU', 'SRCH_DATA_CTNT'):
        assert payload['c'+str(columns.index(key))] == row[key]
