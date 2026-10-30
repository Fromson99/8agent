"""Physical rename contracts. No network, model calls or corpus mutation."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / 'gold_connection_r12'))
spec = importlib.util.spec_from_file_location('gold_map_test_target', HERE / 'physical_mapping.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
GoldMapping, MappingError = module.GoldMapping, module.MappingError


def value():
    return json.loads((HERE / 'mapping_r14_photos.json').read_text())


def test_all_photo_names_and_physical_columns_are_covered():
    mapping = GoldMapping(value())
    assert len(mapping.tables) == 13
    assert sum(len(t['columns']) for t in mapping.tables.values()) == 60
    names = {c['name'] for t in mapping.tables.values() for c in t['columns'].values()}
    assert len(names) == 38
    assert {'RGLT_DOC_ID', 'RGLT_DOC_NAME', 'BODY_POST_HASH_VALU', 'BODY_POST_IFMN_CTNT',
            'ADDN_IFMN_UN_APPN_YN', 'CHAN_ORD', 'BODY_UNIT_ID', 'VCTR_DTLS_IFMN_CTNT', 'EMBD_VCTR'} <= names
    assert not {'DOC_ID', 'DOC_NAME', 'DOC_POST_HASH_VALU', 'CHAN_NO', 'SRC_UNIT_ID', 'EMBD_VCTR_VALU'} & names


def test_every_table_projection_survives_physical_column_order_change():
    data = value()
    for t in data['tables'].values():
        t['columns'] = dict(reversed(list(t['columns'].items())))
    mapped = GoldMapping(data)
    original = GoldMapping(value())
    for key in module.CONTRACT:
        assert mapped.table(key) == original.table(key)
    assert 'EMBD_VCTR AS EMBD_VCTR_VALU' in mapped.table('VCTR_ITEM')
    assert 'CHAN_ORD AS CHAN_NO' in mapped.table('VCTR_HEAD')


@pytest.mark.parametrize('kind', ['document', 'source_unit', 'block_payload', 'source_release', 'query_release', 'query_row', 'query_active'])
def test_existing_consumer_column_contract_survives(kind):
    from gold_connection import READ_COLUMNS
    mapping = GoldMapping(value())
    names = mapping.names(kind)
    assert set(names.columns) == set(READ_COLUMNS[kind][1])
    for column in names.columns:
        assert names.c(column) == column
    assert 'IDD_B03_LGL_' in names.table


def test_flags_and_clobs_keep_existing_value_semantics():
    m = GoldMapping(value())
    assert 'TO_CLOB(RGLT_DOC_NAME) AS NAME' in m.names('document').table
    assert "ADDN_IFMN_UN_APPN_YN='Y' THEN 1" in m.names('block_payload').table
    assert "='N' THEN 0 ELSE 2 END" in m.names('block_payload').table
    assert 'IS NULL THEN NULL' in m.names('block_payload').table


@pytest.mark.parametrize('kind', ['identifier', 'duplicate_table', 'duplicate_column', 'missing_column', 'extra_column', 'type', 'default', 'missing_table'])
def test_invalid_mapping_is_rejected_before_sql(kind):
    data = value()
    t = data['tables']['DOC_VER']
    if kind == 'identifier': t['columns']['DOC_ID']['name'] = 'ID); DROP TABLE X;--'
    if kind == 'duplicate_table': data['tables']['DOC_UNIT']['name'] = t['name']
    if kind == 'duplicate_column': t['columns']['DOC_ID']['name'] = t['columns']['DOC_NAME']['name']
    if kind == 'missing_column': del t['columns']['DOC_ID']
    if kind == 'extra_column': t['columns']['UNKNOWN'] = deepcopy(t['columns']['DOC_ID'])
    if kind == 'type': t['columns']['DOC_ID']['type'] = 'VARCHAR2(50); DROP TABLE X'
    if kind == 'default': t['columns']['DOC_ID']['default'] = 'SYSTIMESTAMP'
    if kind == 'missing_table': del data['tables']['ONTL_ANC']
    with pytest.raises(MappingError): GoldMapping(data)


def test_mapping_hash_and_duplicate_json_are_checked(tmp_path):
    with pytest.raises(MappingError, match='HASH'):
        GoldMapping.load(HERE / 'mapping_r14_photos.json', expected_sha256='0' * 64)
    p = tmp_path / 'bad.json'
    p.write_text('{"schema_version":"a","schema_version":"b"}')
    with pytest.raises(MappingError, match='DUPLICATE'):
        GoldMapping.load(p)


def test_agent_and_archives_are_not_implicitly_redirected_to_gold():
    m = GoldMapping(value())
    for key in ('asset_part', 'query_state'):
        with pytest.raises(MappingError, match='UNSUPPORTED'):
            m.names(key)


def test_changing_owner_binds_a_different_physical_target():
    assert GoldMapping(value(), owner='A').target_sha256 != GoldMapping(value(), owner='B').target_sha256
    mapping = GoldMapping(value())
    with pytest.raises(MappingError, match='IMMUTABLE'):
        mapping.owner = 'OTHER_OWNER'
    with pytest.raises(TypeError):
        mapping.tables['VCTR_ITEM']['columns']['DOC_ID']['name'] = 'OTHER_ID'


def test_generated_ddl_contains_only_registered_physical_names():
    text = '\n'.join(GoldMapping(value()).ddl())
    assert text.count('CREATE TABLE ') == 13
    assert text.count('CREATE INDEX ') == 11
    assert 'EMBD_VCTR VECTOR(*,FLOAT32)' in text
    assert 'RGLT_DOC_ID VARCHAR2(50 BYTE)' in text
    assert 'CHAN_ORD NUMBER(30,0)' in text


def test_request_ontology_preserves_column_order_and_uses_query_budget():
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / '02_BACKEND'))
    from semantic_runtime.legal_agent.ontology_compiler import anchor_key
    calls = []
    def query(sql, binds, limit):
        calls.append((sql, binds, limit))
        # A bounded JSON row preserves positional columns without depending on
        # response-object key order; no package read is allowed by this ACL.
        return [{'ROWS_JSON': json.dumps([['publication', 'private']])}]
    repo = GoldMapping(value()).request_ontology_repository(SimpleNamespace(sql=SimpleNamespace(query=query)))
    anchor = {'document_id': 'public', 'version': 'v1', 'unit_id': 'u1'}
    assert repo.lookup(anchor, {'public'}) == []
    assert len(calls) == 1 and calls[0][1][0][1] == anchor_key(anchor)
    assert 'RGLT_DOC_ID AS DOC_ID' in calls[0][0]
    with pytest.raises(MappingError, match='READ_ONLY'):
        with repo.session(True): pass
    with pytest.raises(MappingError, match='PRECREATED'):
        repo.initialize()


@pytest.mark.parametrize('count', [1024, 1025])
def test_request_ontology_keeps_existing_anchor_bound_in_one_call(count):
    from types import SimpleNamespace
    from semantic_runtime.legal_agent.errors import ContractError
    calls = []
    def query(sql, binds, limit):
        calls.append(sql)
        assert limit == 1 and 'FETCH FIRST 1025 ROWS ONLY' in sql
        return [{'ROWS_JSON': json.dumps([['p', 'private']] * count)}]
    repo = GoldMapping(value()).request_ontology_repository(SimpleNamespace(sql=SimpleNamespace(query=query)))
    anchor = {'document_id': 'public', 'version': 'v1', 'unit_id': 'u1'}
    if count == 1025:
        with pytest.raises(ContractError, match='anchor result bound'):
            repo.lookup(anchor, {'public'})
    else:
        assert repo.lookup(anchor, {'public'}) == []
    assert len(calls) == 1


def test_active_mapping_selects_only_hash_pinned_local_file(tmp_path):
    entry = importlib.util.spec_from_file_location('gold_mapping_entry', HERE / 'connect.py')
    connector = importlib.util.module_from_spec(entry);entry.loader.exec_module(connector)
    pointer = tmp_path / 'ACTIVE_MAPPING.json'
    assert connector.active_mapping(pointer) == (None, None)
    target = tmp_path / 'physical.json'
    target.write_text(json.dumps(value()))
    selected = {'schema_version': 'gold-active-physical-map-v1', 'mapping_file': target.name,
                'sha256': connector.sha(target), 'migration_receipt': 'test-only'}
    pointer.write_text(json.dumps(selected))
    assert connector.active_mapping(pointer) == (target.resolve(), selected['sha256'])
    target.write_text('{}')
    with pytest.raises(ValueError, match='hash changed'):
        connector.active_mapping(pointer)
    selected['mapping_file'] = '../outside.json'
    pointer.write_text(json.dumps(selected))
    with pytest.raises(ValueError, match='path'):
        connector.active_mapping(pointer)
