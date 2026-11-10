"""Agent-record lease and commit round trips on the real local Oracle (2026-11-10, after MAIN176).

MAIN176 still spent 3 round trips per lease acquire (Oracle clock, lease state read, write) plus a head read
per journal transaction and a stored-parts read per commit: 640 of 896 round trips in one measured question.
Now a lease this process released last is taken back with one compare-and-set on exactly that released row,
which can also confirm the journal head revision; a commit sends small new bodies without the stored-parts read
because its statement already inserts each row or proves an existing row JSON_EQUAL; and a commit that ends
its caller's lease releases it in the same statement (journal transaction 6 round trips -> 2). Anything else (row taken,
re-released, head moved, a stored body in another layout) falls back to the original read-then-write path.
Uses the adr_1242 local Oracle fixture (SIDDA *_A tables, isolated scope).
"""
from pathlib import Path
import hashlib
import importlib.util
import json

import pytest

from semantic_runtime import oracle_agent_records as records_module
from semantic_runtime import runtime_sqlite
from semantic_runtime.oracle_agent_records import AgentRecords
from semantic_runtime.oracle_dp_io import DPError, digest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('adr_1242_records', ROOT / '06_TOOLS/EXPERIMENTS/adr_1242/test_records.py')
_base = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_base)
oracle_agent = _base.oracle_agent  # noqa: F401  (fixture)


class Counting:
    def __init__(self, client):
        self.client, self.seen = client, []
        self.SQL_PATH = client.SQL_PATH

    def request(self, method, path, json):
        text = json['statementText']
        kind = ('commit' if "'OPERATION'" in text and text.startswith('DECLARE v_revision') else
                'lease_fast' if text.startswith('DECLARE v_n NUMBER') else
                'body_write' if text.startswith('DECLARE v_old CLOB') else
                'body_read' if 'PART_JSON_CN,4000,1) AS PART' in text else
                'receipt_read' if 'SELECT BODY_HASH_VAL,ORD_SEQ_NO,LOOKUP_HASH_VAL' in text else
                'state_read' if text.startswith('SELECT CHG_SEQ_NO,ST_HASH_VAL') else
                'clock' if 'AS SECONDS FROM DUAL' in text else
                'lease_write' if text.startswith('BEGIN') and 'LGL_EXEC_ST' in text else
                'rows_read' if 'REC_KIND_CD,REC_KEY_HASH_VAL,REC_REV_NO' in text else 'other')
        self.seen.append(kind)
        return self.client.request(method, path, json)

    def __getattr__(self, name):
        return getattr(self.client, name)


def counted(store):
    counter = Counting(store.sql.client)
    store.sql.client = counter
    return counter


def lease_key(identity):
    return 'a1:lease:' + digest(identity)


def overwrite_state(client, store, key, value, revision):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    h = digest({'scope_hash': store.scope, 'key': key, 'revision': revision, 'value': value})
    with client.db.cursor() as c:
        c.execute('UPDATE SIDDA.LGL_EXEC_ST_A SET CHG_SEQ_NO=:r,ST_HASH_VAL=:h,ST_JSON_CN=:v WHERE SCOPE_HASH_VAL=:s AND ST_KEY_ID=:k',
                  r=revision, h=h, v=text, s=store.scope, k=key)
    client.db.commit()


def test_released_lease_is_taken_back_with_one_statement(oracle_agent):
    store, client, _ = oracle_agent
    counter = counted(store)
    with store.lease(['fast', 'one']):
        pass
    assert counter.seen == ['clock', 'state_read', 'lease_write', 'lease_write'], counter.seen
    counter.seen.clear()
    with store.lease(['fast', 'one']) as value:
        assert store.state(lease_key(['fast', 'one']))['value'] == value
    assert counter.seen == ['lease_fast', 'state_read', 'lease_write'], counter.seen
    counter.seen.clear()
    with store.lease(['fast', 'one']):
        pass
    assert counter.seen == ['lease_fast', 'lease_write'], counter.seen
    assert store.state(lease_key(['fast', 'one']))['value']['token'] is None
    assert not client.errors


def test_a_lease_taken_by_another_owner_is_never_taken_over(oracle_agent):
    store, client, _ = oracle_agent
    key = lease_key(['fast', 'foreign'])
    with store.lease(['fast', 'foreign']):
        pass
    old = store.state(key)
    # Another process takes it (active) after this process released it.
    taken = {'token': 'other-owner', 'expires': 4102444800, 'fence': old['revision'] + 1}
    overwrite_state(client, store, key, taken, old['revision'] + 1)
    with pytest.raises(BlockingIOError):
        with store.lease(['fast', 'foreign'], wait=0):
            pass
    assert store.state(key)['value'] == taken
    # It releases: the original read-then-write path takes it.
    overwrite_state(client, store, key, {**taken, 'token': None, 'expires': 0}, old['revision'] + 2)
    with store.lease(['fast', 'foreign'], wait=0) as value:
        assert store.state(key)['value'] == value and store.state(key)['revision'] == old['revision'] + 3


def test_a_lost_lease_does_not_leave_a_reusable_release(oracle_agent):
    store, client, _ = oracle_agent
    key = lease_key(['fast', 'lost'])
    with store.lease(['fast', 'lost']) as mine:
        held = store.state(key)
        # The lease is replaced while held; this owner's release then matches no row.
        taken = {'token': 'other-owner', 'expires': 4102444800, 'fence': held['revision'] + 1}
        overwrite_state(client, store, key, taken, held['revision'] + 1)
    assert store.state(key)['value'] == taken
    with pytest.raises(BlockingIOError):
        with store.lease(['fast', 'lost'], wait=0):
            pass
    assert store.state(key)['value'] == taken and mine['token'] != taken['token']


def test_journal_transaction_confirms_its_head_inside_the_lease(oracle_agent):
    store, client, root = oracle_agent
    root.mkdir(exist_ok=True); path = root / 'journal.sqlite'
    conn = runtime_sqlite.connect(path, isolation_level=None)
    conn.execute('CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)')
    conn.execute("INSERT INTO t VALUES(1,'a')")
    counter = counted(store)
    conn.execute("INSERT INTO t VALUES(2,'b')")
    # One lease statement (also checking the head) and the commit, which also releases the lease.
    assert counter.seen == ['lease_fast', 'commit'], counter.seen
    assert store.state(lease_key(['sql-transaction', str(path)]))['value']['token'] is None
    # Another connection in this process writes the same journal in between: this process saw the newer head,
    # so the lease skips the head check and the head is read and loaded as before (no refused statement).
    other = runtime_sqlite.connect(path, isolation_level=None)
    other.execute("INSERT INTO t VALUES(3,'c')")
    counter.seen.clear()
    conn.execute("INSERT INTO t VALUES(4,'d')")
    assert counter.seen[:2] == ['lease_fast', 'state_read'] and counter.seen[-1] == 'commit', counter.seen
    assert not client.errors
    # Another process writes (simulated: this process has not seen that head): the in-lease check refuses,
    # the refusal is rolled back and the original path reloads the head.
    other.execute("INSERT INTO t VALUES(5,'e')")
    records_module._HEADS.pop((store.scope, 'a1:head:' + conn.owner), None)
    counter.seen.clear()
    conn.execute("INSERT INTO t VALUES(6,'f')")
    assert counter.seen[0] == 'lease_fast' and 'clock' in counter.seen and counter.seen[-1] == 'commit', counter.seen
    assert [e['code'] for e in client.errors] == [20048]
    assert conn.execute('SELECT id FROM t ORDER BY id').fetchall() == [(1,), (2,), (3,), (4,), (5,), (6,)]
    conn.close(); other.close()
    reopened = runtime_sqlite.connect(path, isolation_level=None)
    assert reopened.execute('SELECT v FROM t ORDER BY id').fetchall() == [('a',), ('b',), ('c',), ('d',), ('e',), ('f',)]
    reopened.close()


def test_commit_sends_small_new_bodies_without_reading_stored_parts(oracle_agent):
    store, client, _ = oracle_agent
    counter = counted(store)
    raw = ('본문 ' * 300).encode()
    owner = digest('fast-commit')
    assert store.commit(owner, 0, {'type': 'test'}, [], bodies=[raw]) == 1
    assert counter.seen == ['commit'], counter.seen
    # The same body already stored identically (another request): accepted by the commit itself.
    second = AgentRecords(store.sql, namespace='unused'); second.scope = store.scope
    counter.seen.clear()
    assert second.commit(digest('fast-commit-2'), 0, {'type': 'test'}, [], bodies=[raw]) == 1
    assert counter.seen == ['commit'], counter.seen
    assert AgentRecords(store.sql, namespace='unused').scope != store.scope
    reader = AgentRecords(store.sql, namespace='unused'); reader.scope = store.scope
    assert reader.body(hashlib.sha256(raw).hexdigest()) == raw
    assert not client.errors


def test_commit_falls_back_when_the_stored_body_has_another_layout(oracle_agent):
    store, client, _ = oracle_agent
    raw = b'{"legacy": "v2 layout body"}'; key = hashlib.sha256(raw).hexdigest()
    parts, manifest = store._encode_body(raw, layout=2)
    store._write_body_rows([*parts, manifest])
    fresh = AgentRecords(store.sql, namespace='unused'); fresh.scope = store.scope
    counter = counted(fresh)
    assert fresh.commit(digest('fast-legacy'), 0, {'type': 'test'}, [], bodies=[raw]) == 1
    assert any(e['code'] == 20041 for e in client.errors)
    assert counter.seen[0] == 'commit' and counter.seen[-1] == 'commit' and 'body_read' in counter.seen, counter.seen
    reader = AgentRecords(store.sql, namespace='unused'); reader.scope = store.scope
    assert reader.body(key) == raw
    assert reader.state('a1:head:' + digest('fast-legacy'))['revision'] == 1


def test_other_definite_commit_errors_are_not_replanned(oracle_agent):
    store, client, _ = oracle_agent
    owner = digest('fast-stale')
    assert store.commit(owner, 0, {'type': 'test'}, []) == 1
    counter = counted(store)
    with pytest.raises(DPError):
        store.commit(owner, 0, {'type': 'other'}, [], bodies=[b'{"x":2}'])
    assert counter.seen.count('commit') == 1, counter.seen
    assert any(e['code'] == 20042 for e in client.errors)


def test_a_failed_commit_leaves_the_lease_to_its_own_release(oracle_agent):
    store, client, _ = oracle_agent
    owner = digest('fast-release-fail'); key = lease_key(['fast', 'release-fail'])
    assert store.commit(owner, 0, {'type': 'test'}, []) == 1
    counter = counted(store)
    with pytest.raises(DPError):
        with store.lease(['fast', 'release-fail']):
            store.commit(owner, 0, {'type': 'stale'}, [], release=key)  # stale revision: rolled back
    assert counter.seen[-1] == 'lease_write', counter.seen
    assert store.state(key)['value']['token'] is None and not store.released_in_commit
    counter.seen.clear()
    with store.lease(['fast', 'release-fail']):
        assert store.commit(owner, 1, {'type': 'next'}, [], release=key) == 2
    assert counter.seen == ['lease_fast', 'commit'], counter.seen
    released = store.state(key)
    assert released['value']['token'] is None and released['revision'] % 2 == 0
    # The release this commit made is reusable by the next acquire.
    counter.seen.clear()
    with store.lease(['fast', 'release-fail']):
        pass
    assert counter.seen == ['lease_fast', 'lease_write'], counter.seen


def test_runtime_file_write_is_two_round_trips_after_the_first(oracle_agent):
    store, client, root = oracle_agent
    root.mkdir(exist_ok=True); path = root / 'note.json'
    path.write_text('{"n": 1}')
    counter = counted(store)
    path.write_text('{"n": 2}')
    # Lease, head read, commit (with release).
    assert counter.seen == ['lease_fast', 'state_read', 'commit'], counter.seen
    assert path.read_text() == '{"n": 2}'
    assert store.state(lease_key(['file-write', str(path)]))['value']['token'] is None
