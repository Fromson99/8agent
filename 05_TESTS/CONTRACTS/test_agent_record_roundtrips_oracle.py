"""Agent-record round trips on the real local Oracle (2026-11-07 field: 70% of SQL time was record traffic).

A commit stores its fresh body rows in the same acknowledged transaction (one read of what is already
stored + one write); a lone body upload needs no read-back once acknowledged. Integrity checks that the
removed reads used to provide stay inside the statement: byte-equal duplicates only, an existing replayed
operation must carry the same receipt, a failed commit leaves no body behind. Large or resumed bodies keep
the earlier write-then-confirm path. Uses the adr_1242 local Oracle fixture (SIDDA *_A tables, isolated scope).
"""
from pathlib import Path
import hashlib
import importlib.util
import os
import sys

import pytest

from semantic_runtime import oracle_agent_records as records_module
from semantic_runtime.oracle_agent_records import AgentRecords
from semantic_runtime.oracle_dp_io import DPError, digest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('adr_1242_records', ROOT / '06_TOOLS/EXPERIMENTS/adr_1242/test_records.py')
_base = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_base)
oracle_agent = _base.oracle_agent  # noqa: F401  (fixture)
INLINE_BODY_ROWS = getattr(records_module, 'INLINE_BODY_ROWS', 100)


class Counting:
    """Wrap the local ORDS bridge and classify each statement."""
    def __init__(self, client):
        self.client, self.seen = client, []
        self.SQL_PATH = client.SQL_PATH

    def request(self, method, path, json):
        text = json['statementText']
        kind = ('commit' if "'OPERATION'" in text and text.startswith('DECLARE v_revision') else
                'body_write' if text.startswith('DECLARE v_old CLOB') else
                'body_read' if 'PART_JSON_CN,4000,1) AS PART' in text else
                'receipt_read' if 'SELECT BODY_HASH_VAL,ORD_SEQ_NO,LOOKUP_HASH_VAL' in text else 'other')
        self.seen.append(kind)
        return self.client.request(method, path, json)

    def __getattr__(self, name):
        return getattr(self.client, name)


def counted(store):
    counter = Counting(store.sql.client)
    store.sql.client = counter
    return counter


def fresh_reader(store):
    other = AgentRecords(store.sql, namespace='unused'); other.scope = store.scope
    return other


def test_fresh_commit_is_one_read_and_one_write_and_bodies_are_stored(oracle_agent):
    store, client, _ = oracle_agent
    counter = counted(store)
    owner = digest('roundtrip-commit'); a = ('본문 A ' * 400).encode(); b = b'{"x": 1}'
    rows = [{'key': digest('k1'), 'kind': 'T', 'order': 1, 'lookup': None, 'body': hashlib.sha256(a).hexdigest(), 'deleted': 0}]
    assert store.commit(owner, 0, {'type': 'test'}, rows, bodies=[a, b]) == 1
    assert counter.seen == ['body_read', 'commit'], counter.seen
    reader = fresh_reader(store)
    assert reader.body(hashlib.sha256(a).hexdigest()) == a and reader.body(hashlib.sha256(b).hexdigest()) == b
    assert reader.state('a1:head:' + owner)['revision'] == 1
    assert reader.exact(owner, 'T', digest('k1'))['BODY_HASH_VAL'] == hashlib.sha256(a).hexdigest()
    # Second commit on the same owner: bodies already verified, only the receipt is new.
    counter.seen.clear()
    assert store.commit(owner, 1, {'type': 'test', 'n': 2}, [], bodies=[a]) == 2
    assert counter.seen == ['body_read', 'commit'], counter.seen
    assert not client.errors


def test_lone_body_upload_needs_no_read_back(oracle_agent):
    store, client, _ = oracle_agent
    counter = counted(store)
    raw = os.urandom(5000)
    store.put_bodies([raw])
    assert counter.seen == ['body_read', 'body_write'], counter.seen
    assert fresh_reader(store).body(hashlib.sha256(raw).hexdigest()) == raw
    counter.seen.clear(); store.put_bodies([raw])
    assert counter.seen == []  # verified in this request


def test_replayed_operation_with_a_different_receipt_is_refused(oracle_agent):
    store, client, _ = oracle_agent
    owner = digest('roundtrip-replay')
    assert store.commit(owner, 0, {'type': 'test'}, []) == 1
    # Same inputs again: the existing operation is accepted (idempotent replay).
    assert store.commit(owner, 0, {'type': 'test'}, []) == 1
    with client.db.cursor() as c:
        c.execute("UPDATE SIDDA.LGL_AGT_REC_A SET BODY_HASH_VAL=:h WHERE SCOPE_HASH_VAL=:s AND OWNER_KEY_HASH_VAL=:o "
                  "AND REC_KIND_CD='OPERATION'", h='f' * 64, s=store.scope, o=owner)
    client.db.commit()
    with pytest.raises(DPError):
        store.commit(owner, 0, {'type': 'test'}, [])
    assert any(e['code'] == 20046 for e in client.errors)


def test_failed_commit_leaves_no_inline_body_and_no_verified_claim(oracle_agent):
    store, client, _ = oracle_agent
    owner = digest('roundtrip-conflict'); raw = b'{"never": "stored"}'
    assert store.commit(owner, 0, {'type': 'test'}, []) == 1
    with pytest.raises(DPError):
        store.commit(owner, 0, {'type': 'other'}, [], bodies=[raw])  # stale expected revision
    assert any(e['code'] == 20042 for e in client.errors)
    key = hashlib.sha256(raw).hexdigest()
    assert key not in store.verified_bodies
    with pytest.raises(DPError, match='MISSING'):
        fresh_reader(store).body(key)
    # The same body succeeds on the correct revision.
    assert store.commit(owner, 1, {'type': 'other'}, [], bodies=[raw]) == 2
    assert fresh_reader(store).body(key) == raw


def test_large_body_keeps_write_then_confirm_before_commit(oracle_agent):
    store, client, _ = oracle_agent
    counter = counted(store)
    raw = os.urandom(INLINE_BODY_ROWS * 2048 + 4096)  # incompressible: more rows than one inline write
    owner = digest('roundtrip-large')
    assert store.commit(owner, 0, {'type': 'test'}, [], bodies=[raw]) == 1
    assert counter.seen.count('body_write') == 2 and counter.seen[-1] == 'commit', counter.seen
    assert fresh_reader(store).body(hashlib.sha256(raw).hexdigest()) == raw


def test_sql_sites_and_agent_time_are_counted(oracle_agent):
    store, client, _ = oracle_agent
    owner = digest('roundtrip-sites')
    store.commit(owner, 0, {'type': 'test'}, [], bodies=[b'{"a": 1}'])
    summary = store.sql.stats.summary()
    sites = {row['site'].split('<')[0] for row in summary['sql_sites']}
    assert {'oracle_agent_records._parts', 'oracle_agent_records.commit'} <= sites, summary['sql_sites']
    calls = {row['name']: row['count'] for row in summary['agent_calls']}
    assert calls['commit'] == 1 and summary['agent_ms'] > 0
    progress = store.sql.stats.progress()
    assert progress['sql_count_total'] == summary['sql_count'] and set(progress) == {'sql_count_total', 'sql_ms_total', 'agent_ms_total'}


def test_model_events_snapshot_only_inside_oracle_requests(monkeypatch):
    from semantic_runtime.legal_agent import gateway
    from semantic_runtime import oracle_query_service as service
    assert gateway._timing_snapshot() == {}  # no Oracle request slot
    with service.request_context() as slot:
        class Stats:
            def progress(self): return {'sql_count_total': 3, 'sql_ms_total': 40, 'agent_ms_total': 9}
        slot['agent_records'] = type('R', (), {'sql': type('S', (), {'stats': Stats()})()})()
        snap = gateway._timing_snapshot()
        assert snap['sql_count_total'] == 3 and snap['cpu_ms_total'] >= 0
    monkeypatch.setitem(sys.modules, gateway._ORACLE_SERVICE, None)
    assert gateway._timing_snapshot() == {}
