"""Agent tables per environment: _A everywhere except the unsuffixed development set."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from semantic_runtime.oracle_agent_records import AgentRecords, BODY, RECORD, RUN, STATE
from semantic_runtime.oracle_development_mapping import DevelopmentMapping
from semantic_runtime.physical_mapping import MappingError


@pytest.mark.parametrize('mode', [None, 'mapped', 'legacy', 'development_g19_1', 'gold'])
def test_all_modes_bind_same_agent_tables_before_sql(monkeypatch, mode):
    from semantic_runtime import oracle_dp, oracle_ords
    monkeypatch.setattr(oracle_ords, 'create_client', lambda **_: SimpleNamespace())
    for key, value in {'DP':'oracle', 'ORACLE_ORDS_SCHEMA':'fixture',
                       'ORACLE_ORDS_CLIENT_ID':'fixture', 'ORACLE_ORDS_CLIENT_SECRET':'fixture',
                       'GENOS_ORACLE_GOLD_OWNER':'APP_GOLD'}.items():
        monkeypatch.setenv(key, value)
    if mode is None:
        monkeypatch.delenv('GENOS_ORACLE_TABLE_MAPPING', raising=False)
    else:
        monkeypatch.setenv('GENOS_ORACLE_TABLE_MAPPING', mode)
    client = oracle_dp.client_from_environment()
    records = AgentRecords(SimpleNamespace(client=client))
    tables = (records.body_table, records.record, records.run, records.state_table)
    if mode == 'development_g19_1':
        assert tables == ('SIDDA.LGL_AGT_BODY', 'SIDDA.LGL_AGT_REC', 'SIDDA.LGL_AGT_RUN', 'SIDDA.LGL_EXEC_ST')
    else:
        assert tables == (BODY, RECORD, RUN, STATE)
        assert all(name.endswith('_A') for name in (BODY, RECORD, RUN, STATE))


@pytest.mark.parametrize('suffix', ['_1', '_A', '_A_1'])
@pytest.mark.parametrize('key', ['AGT_BODY', 'AGT_REC', 'AGT_RUN', 'EXEC_ST'])
def test_mapping_cannot_silently_return_to_suffix_one(tmp_path, key, suffix):
    import semantic_runtime.oracle_development_mapping as module
    path = Path(module.__file__).resolve().parents[2] / '00_SYSTEM/ORACLE/development_g19_1.json'
    value = json.loads(path.read_text())
    value['tables'][key]['name'] += suffix
    altered = tmp_path / 'map.json'
    altered.write_text(json.dumps(value))
    with pytest.raises(MappingError, match='DEV_G19_AGENT_TABLE'):
        DevelopmentMapping.load(altered)


def test_new_development_tables_are_unsuffixed_in_their_layers():
    mapping = DevelopmentMapping.load()
    assert dict(mapping.agent_tables) == {'body': 'SIDDA.LGL_AGT_BODY', 'record': 'SIDDA.LGL_AGT_REC',
                                          'run': 'SIDDA.LGL_AGT_RUN', 'state': 'SIDDA.LGL_EXEC_ST'}
    assert [mapping.physical_table(k) for k in ('ONTL_POST', 'ONTL_HEAD', 'ONTL_ANC')] == [
        'SIDDS.LGL_G19_ONTL_POST', 'SIDDS.LGL_G19_ONTL_HEAD', 'SIDDS.LGL_G19_ONTL_ANC']
    assert mapping.physical_table('DOC_VER') == 'SIDDS.LGL_G19_DOC_VER_S_1'


@pytest.mark.parametrize('owner,name', [('SIDDA', 'LGL_G19_ONTL_POST_A_1'), ('SIDDA', 'LGL_G19_ONTL_POST'),
                                        ('SIDDS', 'LGL_G19_ONTL_POST_S_1')])
def test_ontology_stays_unsuffixed_in_silver(tmp_path, owner, name):
    import semantic_runtime.oracle_development_mapping as module
    path = Path(module.__file__).resolve().parents[2] / '00_SYSTEM/ORACLE/development_g19_1.json'
    value = json.loads(path.read_text())
    value['tables']['ONTL_POST'].update(owner=owner, name=name)
    altered = tmp_path / 'map.json'
    altered.write_text(json.dumps(value))
    with pytest.raises(MappingError, match='DEV_G19_NEW_TABLE'):
        DevelopmentMapping.load(altered)


def test_agent_change_does_not_accept_unsuffixed_g19_data(tmp_path):
    import semantic_runtime.oracle_development_mapping as module
    path = Path(module.__file__).resolve().parents[2] / '00_SYSTEM/ORACLE/development_g19_1.json'
    value = json.loads(path.read_text())
    value['tables']['DOC_VER']['name'] = 'LGL_G19_DOC_VER_S'
    altered = tmp_path / 'map.json'
    altered.write_text(json.dumps(value))
    with pytest.raises(MappingError, match='DEV_G19_SUFFIX'):
        DevelopmentMapping.load(altered)
