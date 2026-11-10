"""Field 2026-11-10 SQL plan fixes (dev Exadata, automatic DOP, serving account without V$).

* Agent body reads: the JSON_TABLE join had no row estimate, so each read was a parallel full
  scan. The statement now tells the list size and runs serial (PK range scan, checked there).
* The scope sum of stored body bytes (2.4-2.9 s, 8 calls a request) is reused for
  GENOS_ORACLE_STORAGE_CHECK_SECONDS.
* Source views give the allowed-document list size as a fixed power-of-two hint.
* DP=oracle: the backend (and its warmup) is imported right after HTTP startup, not at the
  first question.
"""
import importlib.util
import json
import os
from pathlib import Path
import threading
import time

import pytest

from semantic_runtime import oracle_agent_records as records
from semantic_runtime.oracle_dp_io import DPError
from semantic_runtime import oracle_query_store

ROOT = Path(__file__).resolve().parents[2]
# Under run_tests --code-root the product tree is given here; stream_app is opened by path.
CODE = Path(os.environ.get('LOOP_TEST_CODE_ROOT') or ROOT)


def bare_store(answer):
    store = object.__new__(records.AgentRecords)
    store.body_table = 'SIDDA.LGL_AGT_BODY_A'
    store.scope = 'scope-' + str(id(store))
    store.sent = []

    def query(text, binds=(), limit=None):
        store.sent.append((text, list(binds)))
        return answer(text, binds)
    store._query = query
    return store


def test_body_read_is_serial_and_sized_and_keeps_paging():
    pages = [[{'BODY_HASH_VAL': 'a', 'PART_SEQ_NO': i, 'PART': json.dumps({'i': i})} for i in range(100)],
             [{'BODY_HASH_VAL': 'a', 'PART_SEQ_NO': 100, 'PART': json.dumps({'i': 100})}]]
    store = bare_store(lambda text, binds: pages.pop(0))
    found = store._parts(['a'])
    assert sorted(found['a']) == list(range(101))
    first, second = store.sent
    text = first[0]
    assert text.startswith('SELECT /*+ NO_PARALLEL */ * FROM (SELECT /*+ NO_PARALLEL */ ')
    assert "B.BODY_HASH_VAL IN (SELECT /*+ CARDINALITY(J 50) */ J.HASH FROM JSON_TABLE(:hashes" in text
    assert ' JOIN JSON_TABLE' not in text
    assert 'ORDER BY B.BODY_HASH_VAL,B.PART_SEQ_NO) WHERE ROWNUM<=100' in text
    assert dict((n, v) for n, v, _ in second[1])['after_part'] == 99   # paging unchanged


def test_allocated_bytes_is_reused_within_the_check_interval(monkeypatch):
    monkeypatch.setattr(records, '_ALLOCATED', {})
    monkeypatch.setenv('GENOS_ORACLE_STORAGE_CHECK_SECONDS', '60')
    values = iter([100, 250])
    store = bare_store(lambda text, binds: [{'N': next(values)}])
    assert store.allocated_bytes() == 100
    assert store.allocated_bytes() == 100 and len(store.sent) == 1
    other = bare_store(lambda text, binds: [{'N': 7}])           # another scope measures itself
    assert other.allocated_bytes() == 7
    assert store.allocated_bytes(max_age=0) == 250 and len(store.sent) == 2
    assert store.allocated_bytes() == 250 and len(store.sent) == 2


def test_allocated_bytes_interval_zero_always_measures_and_expires(monkeypatch):
    monkeypatch.setattr(records, '_ALLOCATED', {})
    monkeypatch.setenv('GENOS_ORACLE_STORAGE_CHECK_SECONDS', '0')
    store = bare_store(lambda text, binds: [{'N': 1}])
    store.allocated_bytes(); store.allocated_bytes()
    assert len(store.sent) == 2
    monkeypatch.setenv('GENOS_ORACLE_STORAGE_CHECK_SECONDS', '60')
    records._ALLOCATED.clear()
    clock = [1000.0]
    monkeypatch.setattr(records.time, 'monotonic', lambda: clock[0])
    store.allocated_bytes(); clock[0] += 59; store.allocated_bytes()
    assert len(store.sent) == 3
    clock[0] += 2; store.allocated_bytes()
    assert len(store.sent) == 4


@pytest.mark.parametrize('value', ['-1', 'soon', 'nan'])
def test_allocated_bytes_rejects_bad_interval(monkeypatch, value):
    monkeypatch.setenv('GENOS_ORACLE_STORAGE_CHECK_SECONDS', value)
    with pytest.raises(DPError, match='GENOS_ORACLE_STORAGE_CHECK_SECONDS'):
        bare_store(lambda text, binds: [{'N': 1}]).allocated_bytes()


def test_scope_hint_is_a_small_fixed_set_of_numbers():
    assert [oracle_query_store.cardinality(n) for n in (0, 1, 2, 3, 50, 1024, 1025, 1649)] == [1, 1, 2, 4, 64, 1024, 2048, 2048]


def test_source_view_hints_list_size_and_serial_base_table():
    connection = object.__new__(oracle_query_store.SourceConnection)
    connection.tables = {'document': ('source.schema', {'columns': {'document_id': {'max_bytes': 512}, 'name': {'max_bytes': 4000}},
                                                          'primary_key': ['document_id']})}
    allowed = {f'doc{i}' for i in range(1649)}
    connection.request = type('R', (), {'snapshot': type('S', (), {'dataset_version': 'v1'})(),
                                        'sources': type('Q', (), {'allowed': allowed})()})()
    text, binds = connection._view('document', 3)
    assert text.startswith('SELECT /*+ NO_PARALLEL */ ')
    assert "r.DOCUMENT_ID IN (SELECT /*+ CARDINALITY(s 2048) */ s.did FROM JSON_TABLE(:a8_scope3," in text
    assert json.loads(dict((n, v) for n, v, _ in binds)['a8_scope3']) == sorted(allowed)


def load_app(name):
    spec = importlib.util.spec_from_file_location(name, CODE / '08_DEPLOYMENT/GENOS/stream_app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_startup(module, monkeypatch, imported, fail=False):
    def fake_import(name):
        imported.append(name); done.set()
        if fail:
            raise RuntimeError('backend unavailable')
    monkeypatch.setattr(module.importlib, 'import_module', fake_import)
    done = threading.Event()
    from fastapi.testclient import TestClient
    with TestClient(module.app) as client:                # runs the startup handlers
        assert client.get('/health').status_code == 200
    return done


def test_oracle_serving_imports_backend_after_startup(monkeypatch):
    monkeypatch.setenv('DP', 'oracle'); monkeypatch.delenv('GENOS_EAGER_BACKEND_IMPORT', raising=False)
    module = load_app('eager_import_on'); imported = []
    assert run_startup(module, monkeypatch, imported).wait(5)
    assert imported == ['service']


def test_eager_import_failure_is_logged_and_health_stays_up(monkeypatch):
    monkeypatch.setenv('DP', 'oracle')
    module = load_app('eager_import_fail'); imported = []
    assert run_startup(module, monkeypatch, imported, fail=True).wait(5)
    assert imported == ['service']


@pytest.mark.parametrize('env', [{'DP': ''}, {'DP': 'oracle', 'GENOS_EAGER_BACKEND_IMPORT': 'off'}])
def test_no_eager_import_without_oracle_or_when_turned_off(monkeypatch, env):
    for key in ('DP', 'GENOS_EAGER_BACKEND_IMPORT'):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    module = load_app('eager_import_off'); imported = []
    run_startup(module, monkeypatch, imported)
    time.sleep(0.2)
    assert imported == []
