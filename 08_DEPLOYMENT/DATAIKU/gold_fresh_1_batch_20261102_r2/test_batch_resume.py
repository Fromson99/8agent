import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'package'))
import run as runner
import batch_resume
from gold_io import Contract, Stop, digest
from lawrag.pipeline import oracle_query_publish as publisher


class Progress:
    def __init__(self): self.events = []
    def emit(self, *a, **k): self.events.append((a, k))
    def set(self, *a, **k): pass


def rows(n):
    for i in range(n):
        value = {'kind': 'fixture.item', 'row_id': str(i), 'document_id': 'D1',
                 'lookup_id': str(i), 'owner_id': None, 'target_id': None,
                 'value': {'text': '한글😀' + str(i)}}
        yield {**value, 'sha256': digest(value)}


class MemoryDB:
    """Failure-injection writer; no claim to emulate Oracle SQL performance."""
    def __init__(self):
        self.saved = {}; self.calls = []; self.fail_after_commit = False
    def block(self, sql, binds, rollback=False):
        payload = json.loads(binds[0][1]); self.calls.append((len(payload), rollback))
        if rollback:
            if any(self.saved.get(v['c2']) != v for v in payload):
                raise RuntimeError('ORA-20042: missing or conflicting')
            return 0.1
        staged = dict(self.saved)
        for value in payload:
            if value['c2'] in staged and staged[value['c2']] != value:
                raise RuntimeError('ORA-20042: conflicting')
            staged[value['c2']] = value
        self.saved = staged
        if self.fail_after_commit:
            self.fail_after_commit = False
            raise RuntimeError('lost response after commit')
        return 0.1
    def query(self, sql): return [{'N': len(self.saved)}]


def setup(tmp_path, monkeypatch, n, batch_rows=5):
    monkeypatch.setenv('G19_QUERY_BATCH_ROWS', str(batch_rows))
    monkeypatch.setenv('G19_QUERY_BATCH_BYTES', str(4 * 1024**2))
    path = tmp_path / 'input.sqlite'; path.write_bytes(b'fixed fixture source')
    source_rows = list(rows(n)); query = {'tables': {'fixture.item': {'rows': n}}}
    monkeypatch.setattr(publisher, 'projected_rows', lambda *a: iter(source_rows))
    state_dir = tmp_path / 'state'; state_dir.mkdir()
    db = MemoryDB(); contract = Contract(HERE / 'package/contract.json')
    job = runner.Job(db, contract, state_dir, {'fixture': True}, Progress())
    paths = {'input.sqlite': runner.file_hash(path)}
    return job, source_rows, query, paths


def seed(job, values, query, count):
    job.batch('SRCH_ROW', [runner.query_row(digest(query), r) for r in values[:count]],
              next_progress={'rows': count}, section='query', slot='input.sqlite')


def test_resume_from_old_offset_not_divisible_by_new_batch(tmp_path, monkeypatch):
    job, values, query, paths = setup(tmp_path, monkeypatch, 19, 10)
    seed(job, values, query, 7)
    original = copy.deepcopy(job.state); job.db.calls.clear()
    runner.load_query(job, tmp_path, {}, {}, query, paths)
    assert job.db.calls == [(10, False), (2, False)]
    assert len(job.db.saved) == 19 and job.state['query']['input.sqlite']['complete']
    assert job.state['deadline'] == original['deadline']


def test_unknown_old_batch_verified_at_original_size_before_larger_batch(tmp_path, monkeypatch):
    job, values, query, paths = setup(tmp_path, monkeypatch, 19, 10)
    job.db.fail_after_commit = True
    with pytest.raises(RuntimeError, match='lost response'): seed(job, values, query, 7)
    marker = copy.deepcopy(job.state['pending']); job.db.calls.clear()
    runner.load_query(job, tmp_path, {}, {}, query, paths)
    assert marker['rows'] == 7
    assert job.db.calls == [(7, True), (10, False), (2, False)]
    assert job.state['pending'] is None and len(job.db.saved) == 19


def test_unknown_missing_batch_is_not_reinserted(tmp_path, monkeypatch):
    job, values, query, paths = setup(tmp_path, monkeypatch, 19, 10)
    job.db.fail_after_commit = True
    with pytest.raises(RuntimeError): seed(job, values, query, 7)
    job.db.saved.clear(); job.db.calls.clear(); before = copy.deepcopy(job.state['pending'])
    with pytest.raises(Stop, match='PENDING_WRITE_REQUIRES_RECONCILIATION'):
        runner.load_query(job, tmp_path, {}, {}, query, paths)
    assert job.db.calls == [(7, True)] and job.db.saved == {}
    assert job.state['pending'] == before


def test_pending_hash_change_rejected_before_db_call(tmp_path, monkeypatch):
    job, values, query, paths = setup(tmp_path, monkeypatch, 12, 10)
    job.db.fail_after_commit = True
    with pytest.raises(RuntimeError): seed(job, values, query, 7)
    job.state['pending']['sha256'] = '0' * 64; job.db.calls.clear()
    with pytest.raises(Stop, match='PENDING_BATCH_BINDING_MISMATCH'):
        runner.load_query(job, tmp_path, {}, {}, query, paths)
    assert not job.db.calls


def test_cursor_beyond_end_rejected(tmp_path, monkeypatch):
    job, values, query, paths = setup(tmp_path, monkeypatch, 4)
    job.state['query']['input.sqlite'] = {'rows': 8}
    with pytest.raises(Stop, match='QUERY_CURSOR_EXCEEDS_INPUT'):
        runner.load_query(job, tmp_path, {}, {}, query, paths)
    assert not job.db.calls


def test_decreasing_batch_size_preserves_offset(tmp_path, monkeypatch):
    job, values, query, paths = setup(tmp_path, monkeypatch, 19, 3)
    seed(job, values, query, 10); job.db.calls.clear()
    runner.load_query(job, tmp_path, {}, {}, query, paths)
    assert job.db.calls == [(3, False)] * 3 and len(job.db.saved) == 19


def test_verify_continues_at_its_own_offset_without_writes(tmp_path, monkeypatch):
    job, values, query, paths = setup(tmp_path, monkeypatch, 19, 10)
    seed(job, values, query, 19); job.db.calls.clear()
    job.state['verify_query']['input.sqlite'] = {'rows': 7}
    before = copy.deepcopy(job.db.saved)
    runner.load_query(job, tmp_path, {}, {}, query, paths, verify_only=True)
    assert job.db.calls == [(10, True), (2, True)] and job.db.saved == before


def test_registered_r1_migration_keeps_all_other_state_and_backup(tmp_path):
    prior = runner.read(HERE / 'package/PREDECESSOR.json')
    old_binding = {'code': prior['code_binding'], 'contract': prior['contract_sha256'], 'files': {'a': 'x'}}
    new_binding = {**old_binding, 'code': 'new-code'}
    state = {'binding': old_binding, 'deadline': 1234, 'query': {'a': {'rows': 698110}},
             'pending': {'sha256': 'pending'}, 'last_error': {'type': 'kept'}}
    path = tmp_path / 'state.json'; runner.atomic(path, state)
    updated = batch_resume.migrate(runner.resume_api(), path, state, new_binding, Progress())
    assert {k: v for k, v in updated.items() if k not in ('binding', 'code_transitions')} == {
        k: v for k, v in state.items() if k != 'binding'}
    assert runner.read(tmp_path / updated['code_transitions'][0]['backup']) == state
    assert batch_resume.migrate(runner.resume_api(), path, updated, new_binding, Progress()) == updated


def test_existing_vector_checkpoint_blocks_code_migration(tmp_path):
    prior = runner.read(HERE / 'package/PREDECESSOR.json')
    old = {'code': prior['code_binding'], 'contract': prior['contract_sha256']}
    state = {'binding': old}; path = tmp_path / 'state.json'; runner.atomic(path, state)
    checkpoint = tmp_path / 'vectors/pub/state.json'; checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text('{"calls":1}')
    with pytest.raises(Stop, match='R1_VECTOR_ALREADY_STARTED'):
        batch_resume.migrate(runner.resume_api(), path, state, {**old, 'code':'new'}, Progress())
    assert runner.read(path) == state and list(tmp_path.glob('state-before-*')) == []


@pytest.mark.parametrize('field,value', [('code','unknown'), ('files',{'a':'different'}), ('contract','changed')])
def test_unregistered_code_or_data_change_rejects_migration(tmp_path, field, value):
    prior = runner.read(HERE / 'package/PREDECESSOR.json')
    old = {'code': prior['code_binding'], 'contract': prior['contract_sha256'], 'files': {'a': 'x'}}
    new = {**old, 'code': 'new-code'}
    if field == 'code': old[field] = value
    else: new[field] = value
    state = {'binding': old}; path = tmp_path / 'state.json'; runner.atomic(path, state)
    with pytest.raises(Stop, match='JOB_BINDING_CHANGED'):
        batch_resume.migrate(runner.resume_api(), path, state, new, Progress())
    assert runner.read(path) == state and list(tmp_path.glob('state-before-*')) == []


@pytest.mark.parametrize('rows_limit,byte_limit', [('10001','4194304'), ('0','4194304'), ('10000','4194305')])
def test_limits_reject_unbounded_values(monkeypatch, rows_limit, byte_limit):
    monkeypatch.setenv('G19_QUERY_BATCH_ROWS', rows_limit)
    monkeypatch.setenv('G19_QUERY_BATCH_BYTES', byte_limit)
    with pytest.raises(ValueError, match='QUERY_BATCH_LIMIT'): batch_resume.limits()


def test_query_10000_validated_and_encoded_without_truncation():
    c = Contract(HERE / 'package/contract.json')
    values = [runner.query_row('r' * 64, r) for r in rows(10000)]
    sql, binds = c.batch('SRCH_ROW', values)
    assert len(json.loads(binds[0][1])) == 10000
    assert 'DBMS_LOB.COMPARE' in sql and binds[1][1] == 10000
    with pytest.raises(Stop, match='BATCH_SIZE'): c.batch('SRCH_ROW', values + [values[0]])
