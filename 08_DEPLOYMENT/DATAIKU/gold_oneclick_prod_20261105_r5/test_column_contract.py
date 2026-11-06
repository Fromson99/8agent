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


def test_r2_to_r5_mapping_changes_and_separate_workspace():
    old = json.loads((HERE.parent/'gold_oneclick_prod_20261104_r2/package/registration_current.json').read_text())
    new = json.loads((HERE/'package/registration_current.json').read_text())
    expected = copy.deepcopy(old)
    expected['tables']['SRCH_ROW']['columns']['SRCH_DATA_HASH_VALU']['name'] = 'RFRN_DTA_HASH_VALU'
    expected['tables']['SRCH_ROW']['columns']['SRCH_DATA_CTNT']['name'] = 'RFRN_DTA_CTNT'
    expected['revision'] = '20261105-b003-body-unit-id100'
    expected['tables']['VCTR_ITEM']['columns']['SRC_UNIT_ID']['type'] = 'VARCHAR2(100 BYTE)'
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


def timestamp_contract_and_db(tmp_path, rows):
    from prod_pipeline import Contract as ProductionContract
    contract = placed_contract(tmp_path, cls=ProductionContract)

    class Lookup:
        def query(self, sql):
            assert "FROM ALL_TAB_COLUMNS WHERE OWNER='SIDDS'" in sql
            assert "TABLE_NAME='IDD_B003_LGL_SRC_POST' AND COLUMN_NAME='RGSN_ASTM'" in sql
            return rows

    return contract, Lookup()


@pytest.mark.parametrize('typ,nullable,default,explicit', [
    ('TIMESTAMP(0)', 'N', None, True), ('TIMESTAMP(6)', 'Y', None, True),
    ('TIMESTAMP(9)', 'N', ' NULL\n', True), ('TIMESTAMP(3)', 'Y', 'systimestamp ', False),
    ('TIMESTAMP(6)', 'N', 'CURRENT_TIMESTAMP', False), ('TIMESTAMP(6)', 'Y', 'LOCALTIMESTAMP', False),
    ('TIMESTAMP(6) WITH TIME ZONE', 'N', 'SYSTIMESTAMP', False),
])
def test_source_post_insert_and_binding(tmp_path, typ, nullable, default, explicit):
    row = {'DATA_TYPE':typ, 'NULLABLE':nullable, 'DATA_DEFAULT':default}
    contract, db = timestamp_contract_and_db(tmp_path, [row])
    before = copy.deepcopy(contract.value)
    effective = contract.bind_registration_time(db)
    before['tables']['SRC_POST']['columns']['RGSN_AITM'] = effective
    assert contract.value == before
    assert effective['type'] == typ and effective['required'] == (nullable == 'N')
    assert contract.bind_registration_time(db) == effective
    source = {'DOC_POST_HASH_VALU':'a'*64, 'MNFST_HASH_VALU':'b'*64, 'DOC_POST_IFMN_CTNT':'{}'}
    sql, binds = contract.batch('SRC_POST', [source])
    assert ('RGSN_ASTM' in sql) is explicit
    assert ('CAST(SYSTIMESTAMP AS '+typ+')' in sql) is explicit
    assert set(json.loads(binds[0][1])[0].values()) == {'a'*64, 'b'*64, '{}', 0}
    with pytest.raises(Stop, match='LOAD_TYPE_NOT_SUPPORTED'):
        contract.batch('SRC_POST', [dict(source, RGSN_AITM='arbitrary')])
    with pytest.raises(Stop, match='ROW_REQUIRED'):
        contract.batch('SRC_POST', [dict(source, MNFST_HASH_VALU=None)])


@pytest.mark.parametrize('typ,nullable,default', [
    ('DATE','N',None), ('VARCHAR2','Y',None), ('TIMESTAMP(10)','N',None),
    ('TIMESTAMP(6) WITH LOCAL TIME ZONE','N','SYSTIMESTAMP'),
    ('TIMESTAMP(6) WITH TIME ZONE','Y',None), ('TIMESTAMP(6)','?',None),
    ('TIMESTAMP(6)','N','MY_FUNCTION()'),
])
def test_unknown_registration_definition_fails_before_insert(tmp_path, typ, nullable, default):
    row = {'DATA_TYPE':typ, 'NULLABLE':nullable, 'DATA_DEFAULT':default}
    contract, db = timestamp_contract_and_db(tmp_path, [row])
    sha = contract.sha256
    with pytest.raises(Stop, match='REGISTRATION_TIME_UNSUPPORTED:.*RGSN_ASTM') as error:
        contract.bind_registration_time(db)
    assert typ in str(error.value) and sha == contract.sha256


def test_missing_metadata_and_change_on_resume(tmp_path):
    from prod_pipeline import fixed
    rows = []
    contract, db = timestamp_contract_and_db(tmp_path, rows)
    with pytest.raises(Stop, match='REGISTRATION_TIME_METADATA_MISSING'):
        contract.bind_registration_time(db)
    rows.append({'DATA_TYPE':'TIMESTAMP(6)', 'NULLABLE':'Y', 'DATA_DEFAULT':None})
    saved = fixed(tmp_path/'inspect.json', contract.bind_registration_time(db))
    first_hash = contract.sha256
    rows[0]['NULLABLE'] = 'N'
    changed = contract.bind_registration_time(db)
    assert contract.sha256 != first_hash
    with pytest.raises(Stop, match='FLOW_SAVED_BINDING_CHANGED'):
        fixed(tmp_path/'inspect.json', changed)
    assert json.loads((tmp_path/'inspect.json').read_text()) == saved


@pytest.mark.parametrize('source_id', ['a'*51, 'a'*100, '한'*33 + 'a', 'a'*101, '한'*34])
def test_vector_id_byte_limit_before_embedding_and_insert(tmp_path, source_id):
    from vector_stage import check_coordinates, rows_for, vector_sql
    contract = placed_contract(tmp_path)
    items = [{'id':'section', 'meta':{'source_id':source_id, 'document_id':'document'}}]
    rows = rows_for('publication', items, [[1., 0.]])
    if len(source_id.encode('utf-8')) <= 100:
        check_coordinates(contract, items, {'document'})
        statement, binds = vector_sql(contract, rows, 2)
        assert "u VARCHAR2(100 BYTE) PATH '$.SRC_UNIT_ID'" in statement
        assert json.loads(binds[0][1])[0]['SRC_UNIT_ID'] == source_id
    else:
        with pytest.raises(Stop, match='VECTOR_COORDINATE_TOO_LONG:SRC_UNIT_ID'):
            check_coordinates(contract, items, {'document'})
        with pytest.raises(Stop, match='VECTOR_COORDINATE_TOO_LONG:SRC_UNIT_ID'):
            vector_sql(contract, rows, 2)
