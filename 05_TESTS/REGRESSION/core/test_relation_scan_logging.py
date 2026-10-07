"""The per-request live log identifies a timed-out reference witness query."""
import json
import sqlite3
import time
from types import SimpleNamespace

import pytest

from semantic_runtime import observability as obs
from semantic_runtime.request_report import live_log
from semantic_runtime.legal_agent.repository import text_hash
from semantic_runtime.legal_agent.workflow_relation_cards import RelationCards


@pytest.mark.parametrize('expired', [False, True])
def test_reference_count_interruption_is_identified_in_live_log(tmp_path, expired):
    frame = 'synthetic reference'
    ref = {'id': 'r1', 'source_id': 's1', 'block_id': '1',
           'source_text': frame, 'source_text_sha256': text_hash(frame),
           'mention_start': 0, 'mention_end': len(frame), 'target_source_ids': []}

    class InterruptedCountDB:
        def execute(self, sql, args):
            if 'GROUP BY 1,2' in sql:
                raise sqlite3.OperationalError('interrupted')
            return [(json.dumps(ref),)]

    now = time.monotonic()
    sources = SimpleNamespace(
        repo=SimpleNamespace(evidence=lambda _: {'source_id': 's1', 'spans': [
            {'block_id': '1', 'start_cp': 0, 'end_cp': len(frame)}]}),
        tools=SimpleNamespace(db=InterruptedCountDB(), sources={
            's1': {'document_id': 'd1', 'blocks': [{'block_id': '1'}]}}),
        store=SimpleNamespace(source=lambda *_: {'text': frame}),
        scope={'d1'}, context=SimpleNamespace(deadline=now-1 if expired else now+10),
        profile={'relation_scan_seconds': 5},
        _relation_scan_started=now-6)

    with live_log(tmp_path, 'req-relations') as (path, _), obs.context(request_id='req-relations'):
        with pytest.raises(sqlite3.OperationalError, match='interrupted'):
            list(RelationCards(sources).references('E1'))
    logged = path.read_text(encoding='utf-8')
    assert 'relation.query.interrupted' in logged
    assert 'step=reference_witness_count' in logged
    assert ('failure_kind=REQUEST_DEADLINE' if expired else
            'failure_kind=SQL_INTERRUPTED_UNKNOWN') in logged
    assert 'deadline_scope=request' in logged
    assert 'scan_limit_ms=5000' not in logged
    assert 'scan_elapsed_ms=' in logged
    assert frame not in logged


def test_reference_witness_counts_use_source_endpoint_once():
    frame = 'synthetic reference'
    db = sqlite3.connect(':memory:')
    db.executescript('''CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
        CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,
            PRIMARY KEY(source_id,reference_id));''')
    for ident in ('r1', 'r2'):
        ref = {'id': ident, 'source_id': 's1', 'block_id': '1' if ident == 'r1' else '2',
               'source_text': frame, 'source_text_sha256': text_hash(frame),
               'mention_start': 0, 'mention_end': len(frame), 'target_source_ids': []}
        db.execute('INSERT INTO reference VALUES(?,?,?)', (ident, 'd1', json.dumps(ref)))
        db.execute('INSERT INTO reference_end VALUES(?,?)', ('s1', ident))
    for i in range(100):
        db.execute('INSERT INTO reference VALUES(?,?,?)', (f'unrelated-{i}', 'd2', json.dumps({
            'id': f'unrelated-{i}', 'source_id': 'other', 'block_id': '1'})))
    # Incoming references share the endpoint but must not make the outgoing
    # witness appear ambiguous.
    incoming = {'id': 'incoming', 'source_id': 's2', 'block_id': '1',
                'source_text': frame, 'source_text_sha256': text_hash(frame),
                'mention_start': 0, 'mention_end': len(frame), 'target_source_ids': ['s1']}
    db.execute('INSERT INTO reference VALUES(?,?,?)', ('incoming', 'd1', json.dumps(incoming)))
    db.execute('INSERT INTO reference_end VALUES(?,?)', ('s1', 'incoming'))
    statements = []
    db.set_trace_callback(statements.append)
    sources = SimpleNamespace(
        repo=SimpleNamespace(evidence=lambda _: {'source_id': 's1', 'spans': [
            {'block_id': block, 'start_cp': 0, 'end_cp': len(frame)} for block in ('1', '2')]}),
        tools=SimpleNamespace(db=db, sources={
            's1': {'document_id': 'd1', 'blocks': [{'block_id': '1'}, {'block_id': '2'}]}}),
        store=SimpleNamespace(source=lambda *_: {'text': frame}),
        scope={'d1'}, context=SimpleNamespace(deadline=time.monotonic()+10),
        profile={'relation_scan_seconds': 5})
    notices = list(RelationCards(sources).references('E1'))
    db.close()
    assert len(notices) == 3
    assert all(n['role_status'] != 'AMBIGUOUS' for n in notices if n['direction'] == 'outgoing')
    assert sum('GROUP BY 1,2' in sql for sql in statements) == 1
    assert not any('SELECT count(*) FROM reference' in sql for sql in statements)


def test_precomputed_witness_count_avoids_source_scan():
    frame = 'synthetic reference'
    db = sqlite3.connect(':memory:')
    db.executescript('''CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
        CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,
            PRIMARY KEY(source_id,reference_id));
        CREATE TABLE reference_witness_count(source_id TEXT,block_id TEXT,
            source_text_sha256 TEXT,n INTEGER,
            PRIMARY KEY(source_id,block_id,source_text_sha256));''')
    ref = {'id': 'r1', 'source_id': 's1', 'block_id': '1',
           'source_text': frame, 'source_text_sha256': text_hash(frame),
           'mention_start': 0, 'mention_end': len(frame), 'target_source_ids': []}
    db.execute('INSERT INTO reference VALUES(?,?,?)', ('r1', 'd1', json.dumps(ref)))
    db.execute('INSERT INTO reference_end VALUES(?,?)', ('s1', 'r1'))
    db.execute('INSERT INTO reference_witness_count VALUES(?,?,?,?)',
               ('s1', '1', text_hash(frame), 1))
    statements = []
    db.set_trace_callback(statements.append)
    sources = SimpleNamespace(
        repo=SimpleNamespace(evidence=lambda _: {'source_id': 's1', 'spans': [
            {'block_id': '1', 'start_cp': 0, 'end_cp': len(frame)}]}),
        tools=SimpleNamespace(db=db, has_reference_witness_count=True, sources={
            's1': {'document_id': 'd1', 'blocks': [{'block_id': '1'}]}}),
        store=SimpleNamespace(source=lambda *_: {'text': frame}),
        scope={'d1'}, context=SimpleNamespace(deadline=time.monotonic()+10),
        profile={'relation_scan_seconds': 5})
    notices = list(RelationCards(sources).references('E1'))
    db.close()
    assert len(notices) == 1 and notices[0]['role_status'] != 'AMBIGUOUS'
    assert sum('SELECT n FROM reference_witness_count' in sql for sql in statements) == 1
    assert not any('GROUP BY 1,2' in sql for sql in statements)
