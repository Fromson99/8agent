"""Run exact delivered notebook cells from an empty namespace with a fake SDK."""
import ast
import json
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest
from test_compact_v2_rag import structured_generation
from test_oracle_dp_runtime import AssetOracle

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / '08_DEPLOYMENT/DATAIKU/legal_oracle_notebook_20261019_r1/package'
BOOK = FOLDER / 'LEGAL_ORACLE_FULL_TRANSFER_20261019_R1.ipynb'


class NotebookOracle(AssetOracle):
    login = 'BAIP04APP'
    auth_failure = False

    def request(self, method, path, json):
        sql = json['statementText']
        if sql.startswith('SELECT 1 AS OK'):
            if self.auth_failure:
                raise PermissionError('mock secret must not escape')
            self.calls.append(json)
            return {'items': [{'resultSet': {'items': [{'OK': 1, 'LOGIN_USER': self.login,
                                                       'CURRENT_SCHEMA': self.login}], 'hasMore': False, 'offset': 0}}]}
        if 'LEGAL_RAG_' in sql and 'WHERE 1=0' in sql:
            self.calls.append(json)
            return {'items': [{'resultSet': {'items': [], 'hasMore': False, 'offset': 0}}]}
        return super().request(method, path, json)


def execute(ns, step):
    book = json.loads(BOOK.read_text())
    c, = [c for c in book['cells'] if c.get('metadata', {}).get('legal_step') == step]
    exec(compile(''.join(c['source']), str(BOOK) + '#' + step, 'exec'), ns)


@pytest.fixture
def fresh(structured_generation, tmp_path, monkeypatch):
    remote = NotebookOracle()
    kwargs_seen = []
    def factory(**kwargs):
        kwargs_seen.append(kwargs)
        assert kwargs['schema'] == 'b04'
        assert kwargs['verify'] is True and 'base_url' not in kwargs
        return remote
    genos = ModuleType('genos'); ords = ModuleType('genos.ords'); ords.ORDSClient = factory
    monkeypatch.setitem(sys.modules, 'genos', genos)
    monkeypatch.setitem(sys.modules, 'genos.ords', ords)
    monkeypatch.setenv('ORACLE_ORDS_CLIENT_ID', 'TEST_ONLY_ID')
    monkeypatch.setenv('ORACLE_ORDS_CLIENT_SECRET', 'TEST_ONLY_SECRET')
    monkeypatch.delenv('LLMOPS_ORDS_BASE_URL', raising=False)
    def new_kernel():
        ns = {}
        execute(ns, 'bootstrap')
        execute(ns, 'settings')
        ns['SOURCE_SQLITE'] = str(structured_generation / 'store.sqlite')
        ns['LOG_DIR'] = str(tmp_path / 'logs')
        ns['SETTINGS'] = dict(schema=ns['SCHEMA'], prefix=ns['PREFIX'], timeout=ns['TIMEOUT'], log_dir=ns['LOG_DIR'])
        execute(ns, 'credentials')
        execute(ns, 'connect')
        return ns
    return remote, new_kernel, kwargs_seen


def test_empty_kernel_all_steps_and_restart_summary(fresh):
    remote, new_kernel, calls = fresh
    ns = new_kernel()
    assert not remote.writes
    execute(ns, 'check')
    assert not remote.writes
    for step in ('run', 'verify', 'publish', 'summary'):
        execute(ns, step)
    assert ns['FINAL_RESULT']['status'] == 'TRANSFER_AND_ASSETS_COMPLETE'
    assert ns['FINAL_RESULT']['serving_switched'] is False
    writes = remote.writes
    ns2 = new_kernel()
    execute(ns2, 'summary')
    assert ns2['FINAL_RESULT'] == ns['FINAL_RESULT']
    assert remote.writes == writes
    assert len(calls) == 2


def test_r6_compatible_resume_uses_same_receipt_budget(fresh):
    remote, new_kernel, _ = fresh
    ns = new_kernel()
    engine = ns['_legal19_migration']
    old = engine.from_notebook(ns['desk'], source=ns['SOURCE_SQLITE'], action='run', seconds=3600, max_batches=1)
    assert old['status'] == 'PAUSED'
    before = json.loads(Path(old['receipt']).read_text())
    ns2 = new_kernel()
    execute(ns2, 'run')
    after = json.loads(Path(old['receipt']).read_text())
    assert ns2['LEGAL_FULL_TRANSFER_RESULT']['receipt'] == old['receipt']
    assert after['deadline'] == before['deadline']
    assert after['created_at'] == before['created_at']
    execute(ns2, 'verify')
    execute(ns2, 'publish')
    assert len(remote.releases) == 1


@pytest.mark.parametrize('mode', ['denied', 'after_timeout'])
def test_failed_write_then_fresh_kernel_resume(fresh, mode):
    remote, new_kernel, _ = fresh
    ns = new_kernel()
    remote.mode = mode
    with pytest.raises(RuntimeError):
        execute(ns, 'run')
    assert not remote.releases
    remote.mode = None
    ns2 = new_kernel()
    for step in ('run', 'verify', 'publish', 'summary'):
        execute(ns2, step)
    assert ns2['FINAL_RESULT']['status'] == 'TRANSFER_AND_ASSETS_COMPLETE'


def test_expired_budget_not_reset_by_new_notebook(fresh):
    _, new_kernel, _ = fresh
    ns = new_kernel(); execute(ns, 'check')
    path = Path(ns['CHECK_RESULT']['receipt'])
    state = json.loads(path.read_text()); state['deadline'] = 1
    path.write_text(json.dumps(state))
    ns2 = new_kernel()
    with pytest.raises(RuntimeError, match='PAUSED'):
        execute(ns2, 'run')
    assert json.loads(path.read_text())['deadline'] == 1


def test_changed_settings_do_not_silently_start_new_budget(fresh):
    remote, new_kernel, _ = fresh
    ns = new_kernel(); execute(ns, 'check')
    ns['desk'].settings['timeout'] = 31
    execute(ns, 'connect')
    with pytest.raises(RuntimeError, match='PRIOR_BINDING'):
        execute(ns, 'run')
    assert not remote.writes


def test_wrong_account_and_auth_failure_stop(fresh):
    remote, new_kernel, _ = fresh
    remote.login = 'OTHER_ACCOUNT'
    with pytest.raises(RuntimeError, match='LOGIN_USER'):
        new_kernel()
    remote.login = 'BAIP04APP'; remote.auth_failure = True
    with pytest.raises(RuntimeError, match='CONNECT_FAILED'):
        new_kernel()
    assert not remote.writes


def test_publish_guard_and_remote_release_tampering(fresh):
    remote, new_kernel, _ = fresh
    ns = new_kernel(); execute(ns, 'run')
    with pytest.raises(RuntimeError, match='VERIFY_FIRST'):
        execute(ns, 'publish')
    execute(ns, 'verify'); execute(ns, 'publish')
    key = ns['LEGAL_DP_PUBLISH_RESULT']['release_id']
    remote.releases[key]['body'] = '{}'
    with pytest.raises(RuntimeError, match='RELEASE_HASH'):
        execute(ns, 'summary')


def test_artifact_has_no_saved_outputs_or_credentials():
    from jsonschema import Draft4Validator
    schema = json.loads((FOLDER.parent / 'validation/nbformat.v4.5.schema.json').read_text())
    book = json.loads(BOOK.read_text())
    Draft4Validator(schema).validate(book)
    codes = [c for c in book['cells'] if c['cell_type'] == 'code']
    assert len(codes) == 9
    assert all(not c['outputs'] and c['execution_count'] is None for c in codes)
    for c in codes:
        source = ''.join(c['source'])
        ast.parse(source, feature_version=(3, 11))
        assert 'TEST_ONLY_SECRET' not in source
    assert 'CLIENT_SECRET =' not in BOOK.read_text()
    compile((FOLDER / 'LEGAL_ORACLE_FULL_TRANSFER_20261019_R1_RUN.txt').read_text(), 'run.txt', 'exec')
