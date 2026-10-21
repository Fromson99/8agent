"""Exact emailed cells against real SQLite + fake ORDS; never contacts GENOS."""
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_compact_v2_rag import structured_generation
from test_oracle_dp_runtime import AssetOracle
from test_oracle_dp import run
from lawrag.pipeline import oracle_migration as migration
from semantic_runtime import oracle_dp_assets as assets

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / '08_DEPLOYMENT/DATAIKU/legal_oracle_transfer_20261018_r1/package'


def cell(namespace, number):
    path, = PACKAGE.glob(f'LEGAL_ORACLE_{number}_*.txt')
    exec(compile(path.read_text(), str(path), 'exec'), namespace)


@pytest.fixture
def delivery(structured_generation, tmp_path, monkeypatch):
    remote = AssetOracle()
    source = structured_generation / 'store.sqlite'
    resolve = Path.resolve

    def map_source(path, *args, **kwargs):
        return source if str(path) == migration.SOURCE else resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'resolve', map_source)
    desk = SimpleNamespace(require_connection=lambda: SimpleNamespace(client=remote),
                           recovery_required=False, binding=lambda: 'mock-target',
                           settings={'log_dir': str(tmp_path / 'notebook-logs')})
    return remote, {'desk': desk}, source


def test_exact_delivery_all_steps_and_reexecution(delivery, tmp_path):
    remote, namespace, source = delivery
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source.parent.rglob('*') if p.is_file()}
    # Seed some rows as in the field's successful sample test.
    result = run(remote, source, tmp_path / 'sample', action='run', max_batches=1)
    assert result['status'] == 'PAUSED'
    cell(namespace, '02')
    assert namespace['LEGAL_FULL_TRANSFER_RESULT']['status'] == 'SOURCE_COMPLETE'
    writes = remote.writes
    cell(namespace, '03')
    transfer = namespace['LEGAL_FULL_TRANSFER_RESULT']
    assert transfer['status'] == 'VERIFIED'
    assert remote.writes == writes
    cell(namespace, '04')
    publication = namespace['LEGAL_DP_PUBLISH_RESULT']
    assert publication['status'] == 'COMPLETE'
    release = json.loads(remote.releases[publication['release_id']]['body'])
    _, inventory = assets.inventory(source.parent)
    assert release['assets'] == inventory
    assert set(release['source_rows']) == {'document', 'source_unit', 'block_payload'}
    assert all(v['rows'] == transfer['counts'][k] for k, v in release['source_rows'].items())
    writes = remote.writes
    for number in ('02', '03', '04'):
        cell(namespace, number)
    assert remote.writes == writes
    assert namespace['LEGAL_DP_PUBLISH_RESULT']['release_id'] == publication['release_id']
    assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in source.parent.rglob('*') if p.is_file()}


@pytest.mark.parametrize('mode', ['denied', 'after_timeout'])
def test_exact_source_error_resume(delivery, mode):
    remote, namespace, _ = delivery
    remote.mode = mode
    with pytest.raises(RuntimeError):
        cell(namespace, '02')
    assert 'LEGAL_FULL_TRANSFER_RESULT' not in namespace
    remote.mode = None
    cell(namespace, '02')
    cell(namespace, '03')
    assert namespace['LEGAL_FULL_TRANSFER_RESULT']['status'] == 'VERIFIED'


def test_exact_verify_detects_remote_content_change(delivery):
    remote, namespace, _ = delivery
    cell(namespace, '02')
    key = next(iter(remote.data['document']))
    remote.data['document'][key]['NAME'] = 'changed remotely'
    with pytest.raises(RuntimeError):
        cell(namespace, '03')
    assert not remote.releases
    receipt = Path(namespace['LEGAL_FULL_TRANSFER_RESULT']['receipt'])
    assert json.loads(receipt.read_text())['status'] == 'FAILED'


def test_exact_publish_requires_verified_source(delivery):
    remote, namespace, _ = delivery
    cell(namespace, '02')
    with pytest.raises(RuntimeError, match='TRANSFER_FIRST'):
        cell(namespace, '04')
    assert not remote.releases and not remote.parts


def test_exact_asset_uncertain_commit_resume(delivery):
    remote, namespace, _ = delivery
    cell(namespace, '02')
    cell(namespace, '03')
    remote.mode = 'after_timeout'
    with pytest.raises(RuntimeError):
        cell(namespace, '04')
    assert remote.parts and not remote.releases
    remote.mode = None
    cell(namespace, '04')
    assert namespace['LEGAL_DP_PUBLISH_RESULT']['status'] == 'COMPLETE'
    assert len(remote.releases) == 1


def test_package_sql_matches_writer_contract_and_cells_compile():
    sql = (PACKAGE / 'LEGAL_ORACLE_01_TABLES_20261018_R1.txt').read_text()
    assert sql.count('CREATE TABLE SIDDA.') == 2
    assert sql.count('GRANT SELECT, INSERT ON SIDDA.') == 2
    assert 'TO BAIP04APP;' in sql
    assert 'SIDDA.LEGAL_RAG_ASSET_PART_A' in sql and 'SIDDA.LEGAL_RAG_RELEASE_A' in sql
    import re
    uncommented = re.sub(r'--[^\n]*', '', sql)
    assert not re.search(r'\b(DROP|TRUNCATE|DELETE|UPDATE)\b', uncommented)
    for number in ('02', '03', '04'):
        path, = PACKAGE.glob(f'LEGAL_ORACLE_{number}_*.txt')
        ast.parse(path.read_text(), feature_version=(3, 11))
        compile(path.read_text(), str(path), 'exec')
