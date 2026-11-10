"""Opening an Oracle record database while another request commits (2026-11-10 field).

Field log: every question failed at the entry check (session_identity.reject_legacy ->
state_sqlite.readonly) with StateConflict AGENT_SQL_CHANGED, because another request or
code serving sharing the same Agent namespace committed while the shared memory/case
database rows were being read. Opening takes no lease, so the open re-reads the newer
head a bounded number of times; writers keep their lease/CAS checks. Uses the adr_1242
local Oracle fixture (SIDDA *_A tables, isolated scope).
"""
from pathlib import Path
import importlib.util

import pytest

from semantic_runtime import oracle_record_sqlite, runtime_sqlite
from semantic_runtime.oracle_query_state import StateConflict
from semantic_runtime.state_sqlite import readonly

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('adr_1242_records_hydration', ROOT / '06_TOOLS/EXPERIMENTS/adr_1242/test_records.py')
_base = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_base)
oracle_agent = _base.oracle_agent  # noqa: F401  (fixture)


def shared(root):
    p = root / 'memory-v2.sqlite'
    db = runtime_sqlite.connect(p, isolation_level=None)
    db.execute('CREATE TABLE session(id TEXT PRIMARY KEY, team TEXT)')
    db.execute('INSERT INTO session VALUES(?,?)', ('s-1', 'risk'))
    db.close()
    return p


def write_during_reads(monkeypatch, store, path, times):
    """Commit a new row from another connection while the reader fetches bodies."""
    original = store.bodies
    state = {'writes': 0, 'busy': False}

    def bodies(hashes):
        result = original(hashes)
        if state['writes'] < times and not state['busy']:  # the injected writer opens too
            state['writes'] += 1; state['busy'] = True
            try:
                other = runtime_sqlite.connect(path, isolation_level=None)
                other.execute('INSERT INTO session VALUES(?,?)', (f's-new-{state["writes"]}', 'risk'))
                other.close()
            finally:
                state['busy'] = False
        return result
    monkeypatch.setattr(store, 'bodies', bodies)
    return state


def test_readonly_open_rereads_when_another_request_commits(oracle_agent, monkeypatch):
    store, client, root = oracle_agent
    path = shared(root)
    monkeypatch.setattr(oracle_record_sqlite.time, 'sleep', lambda _: None)
    state = write_during_reads(monkeypatch, store, path, times=1)
    db = readonly(path)
    try:
        rows = db.execute('SELECT id FROM session ORDER BY id').fetchall()
    finally:
        db.close()
    assert state['writes'] == 1
    assert [r[0] for r in rows] == ['s-1', 's-new-1']  # the newer committed state, not a mix
    with pytest.raises(Exception):
        db2 = readonly(path)
        try:
            db2.execute('INSERT INTO session VALUES(?,?)', ('x', 'y')); db2.commit()
        finally:
            db2.close()
    assert not client.errors


def test_writer_open_also_rereads_and_keeps_both_changes(oracle_agent, monkeypatch):
    store, client, root = oracle_agent
    path = shared(root)
    monkeypatch.setattr(oracle_record_sqlite.time, 'sleep', lambda _: None)
    original = store.bodies
    write_during_reads(monkeypatch, store, path, times=2)
    db = runtime_sqlite.connect(path, isolation_level=None)
    db.execute('INSERT INTO session VALUES(?,?)', ('s-mine', 'risk'))
    db.close()
    monkeypatch.setattr(store, 'bodies', original)
    check = readonly(path)
    assert [r[0] for r in check.execute('SELECT id FROM session ORDER BY id')] == ['s-1', 's-mine', 's-new-1', 's-new-2']
    check.close()
    assert not client.errors


def test_continuous_writes_still_fail_after_bounded_attempts(oracle_agent, monkeypatch):
    store, client, root = oracle_agent
    path = shared(root)
    monkeypatch.setattr(oracle_record_sqlite.time, 'sleep', lambda _: None)
    retries = []
    monkeypatch.setattr(oracle_record_sqlite, 'hydration_retry', lambda p, attempt: retries.append(attempt))
    state = write_during_reads(monkeypatch, store, path, times=100)
    with pytest.raises(StateConflict, match='AGENT_SQL_CHANGED'):
        readonly(path)
    assert state['writes'] >= oracle_record_sqlite.HYDRATION_ATTEMPTS
    assert retries == list(range(1, oracle_record_sqlite.HYDRATION_ATTEMPTS))
    assert not client.errors


def test_missing_database_is_still_not_found_for_readers(oracle_agent):
    _, _, root = oracle_agent
    root.mkdir(exist_ok=True)
    with pytest.raises(FileNotFoundError):
        readonly(root / 'never-created.sqlite')
