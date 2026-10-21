"""Real SQLite interruption, synthetic originals, actual API/service consumers."""
import asyncio
import importlib
import json
import sqlite3
import time
from dataclasses import replace
from types import SimpleNamespace as S

import pytest

import test_comparison_ten_minute as fixture
from semantic_runtime import workflow_bridge as bridge
from semantic_runtime.legal_agent import context as contexts
from test_research_resolution_consumers import load

tree = fixture.tree


@pytest.mark.parametrize('mode', ['review', 'request', 'final_read', 'early_interrupt', 'other_sql', 'integrity', 'publication'])
def test_reference_sql_deadline_returns_saved_sources_through_service(tmp_path, tree, monkeypatch, mode):
    app, _ = fixture.fixture.application(tmp_path, tree)
    transport = fixture.Transport(fixture.Clock(), 'normal')
    app.state.pipeline.term_agent.transport = transport
    clock = S(now=time.monotonic())
    start = clock.now
    virtual_time = S(monotonic=lambda: clock.now)
    monkeypatch.setattr(bridge, 'time', virtual_time)
    monkeypatch.setattr(contexts, 'time', virtual_time)
    native = importlib.import_module(bridge.__package__ + '.comparison_research_bridge')
    original = native.locators
    interruptions = []
    final_interruptions = []

    def locators(port, *args, **kwargs):
        session = port.session
        if mode == 'other_sql':
            clock.now = session.context.deadline + .01
            return session.tools.db.execute('SELECT * FROM absent_table_for_contract_test').fetchall()
        def trace(sql):
            if sql.startswith('SELECT r.json FROM reference r JOIN reference_end'):
                if mode != 'early_interrupt':
                    clock.now = start + 601 if mode == 'request' else session.context.deadline + .01
                session.tools.db.set_progress_handler(lambda: 1, 1)
        session.tools.db.set_trace_callback(trace)
        try:
            return original(port, *args, **kwargs)
        except sqlite3.OperationalError as exc:
            interruptions.append((exc.sqlite_errorcode, session.context.deadline))
            raise
        finally:
            session.tools.db.set_trace_callback(None)

    monkeypatch.setattr(native, 'locators', locators)
    original_evidence = bridge.SourcePort.evidence
    def evidence(port):
        if interruptions:
            if mode == 'integrity':
                raise bridge.ContractError('synthetic source hash changed after interruption')
            abort = mode == 'final_read' and not final_interruptions or mode == 'publication' and port._verification_deadline is not None
            if abort:
                clock.now = port.session.context.deadline + .01
                port.session.store.db.set_progress_handler(lambda: 1, 1)
                try:
                    port.session.store.db.execute('SELECT 1').fetchall()
                except sqlite3.OperationalError as exc:
                    final_interruptions.append(exc.sqlite_errorcode)
                    raise
        return original_evidence(port)
    monkeypatch.setattr(bridge.SourcePort, 'evidence', evidence)
    service = load('sql_interrupt_service', 'service.py')
    service._APP = app
    service._BINDING = {'mode': 'isolated-contract-test'}
    request = {'API_TYPE': 'RAG_ASK', **fixture.BODY}
    from semantic_runtime.legal_agent.answer_stream import capture
    events = []
    with capture(fixture.BODY['request_id'], events.append):
        result = asyncio.run(service.service({}, request))
    if mode in ('early_interrupt', 'other_sql', 'integrity', 'publication'):
        assert result['status'] == 500, result
        assert not events
        assert transport.final_calls == (1 if mode == 'publication' else 0)
        journal = next(app.state.workflow_runtime.root.glob('*/journal.sqlite'))
        with sqlite3.connect(journal) as db:
            status, result_json, checkpoint = db.execute('SELECT status,result_json,checkpoint_json FROM workflow_state').fetchone()
            assert status == 'failed' and result_json is None
            failure = json.loads(checkpoint)['failure']
            assert failure['type'] == ('ContractError' if mode == 'integrity' else 'OperationalError')
        calls = len(transport.calls)
        again = asyncio.run(service.service({}, request))
        assert again['status'] == 409 and len(transport.calls) == calls
        return
    assert result['status'] == 200, result
    body = result['body']
    assert body['status'] == 'partial'
    assert interruptions and interruptions[0][0] == sqlite3.SQLITE_INTERRUPT
    assert len(interruptions) == 1
    assert transport.final_calls == (1 if mode == 'review' else 0)
    assert body['finalization']['status'] == ('COMPLETE' if mode == 'review' else 'SAVED_EVIDENCE_ONLY')
    if mode != 'request':
        assert body['finalization']['cause'] == 'DEADLINE_EXCEEDED'
    if mode == 'final_read':
        assert final_interruptions == [sqlite3.SQLITE_INTERRUPT]
    assert body['evidence_refs'] and body['answer']['text']
    assert ''.join(event['text'] for event in events) == body['answer']['text']
    assert {s['side'] for s in body['assembly']['term_agent']['source_bundle']['sources']} == {'internal', 'external'}
    journal = app.state.workflow_runtime.root / body['run_id'] / 'journal.sqlite'
    with sqlite3.connect(journal) as db:
        deadline = db.execute('SELECT deadline_at FROM run').fetchone()[0]
        budget = db.execute('SELECT * FROM budget').fetchall()
        stopped = [json.loads(raw) for raw, in db.execute("SELECT payload_json FROM event WHERE kind='WORKFLOW_STOPPED'")]
        classified = [json.loads(raw) for raw, in db.execute("SELECT payload_json FROM event WHERE kind='WORKFLOW_SOURCE_DEADLINE'")]
    assert stopped[0]['stage'] == 'ITEM_REVIEW'
    assert len(classified) == (2 if mode == 'final_read' else 1)
    assert all(e['cause'] == 'interrupted' and not e['retried'] for e in classified)
    calls = len(transport.calls)
    again = asyncio.run(service.service({}, request))
    saved = asyncio.run(service.service({}, {'API_TYPE': 'WORKFLOW_STATUS', 'run_id': body['run_id'], 'session_id': 's'}))
    assert again['status'] == saved['status'] == 200
    assert again['body']['answer'] == saved['body']['answer'] == body['answer']
    assert len(transport.calls) == calls
    with sqlite3.connect(journal) as db:
        assert db.execute('SELECT deadline_at FROM run').fetchone()[0] == deadline
        assert db.execute('SELECT * FROM budget').fetchall() == budget


@pytest.mark.parametrize('failure', ['normal', 'deadline', 'interrupt', 'other_sql', 'integrity'])
def test_read_scope_restores_callbacks_and_does_not_mask_errors(monkeypatch, failure):
    now = time.monotonic()
    clock = S(now=now)
    monkeypatch.setattr(bridge, 'time', S(monotonic=lambda: clock.now))
    monkeypatch.setattr(contexts, 'time', S(monotonic=lambda: clock.now))
    context = contexts.RequestContext.create({'scope': {'document_version_ids': []}}, {}, {}, 600)
    events = []
    store_db = sqlite3.connect(':memory:')
    tools_db = sqlite3.connect(':memory:')
    session = S(context=context, store=S(db=store_db), tools=S(db=tools_db, request_deadline=context.deadline),
                repo=S(event=lambda *args: events.append(args)))
    port = bridge.SourcePort.__new__(bridge.SourcePort)
    port.session = session
    phase = replace(context, deadline=now+480)
    query = 'WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<10000) SELECT sum(x) FROM n'
    caught = None
    try:
        try:
            with port.source_reads(phase):
                assert session.context.deadline == session.tools.request_deadline == phase.deadline
                if failure == 'deadline': clock.now = phase.deadline+.01
                if failure == 'interrupt': tools_db.set_progress_handler(lambda: 1, 1)
                if failure == 'other_sql':
                    clock.now = phase.deadline+.01
                    tools_db.execute('SELECT * FROM missing_table')
                if failure == 'integrity': raise bridge.ContractError('hash mismatch')
                tools_db.execute(query).fetchone()
        except Exception as exc:
            caught = exc
        if failure == 'normal': assert caught is None
        elif failure == 'deadline':
            assert isinstance(caught, bridge.DeadlineExceeded)
            assert caught.__cause__.sqlite_errorcode == sqlite3.SQLITE_INTERRUPT
            assert len(events) == 1
        elif failure == 'integrity': assert isinstance(caught, bridge.ContractError)
        else: assert isinstance(caught, sqlite3.OperationalError)
        assert session.context is context
        assert session.tools.request_deadline == context.deadline
        # The temporary expired callback is gone; the original hard limit stays.
        clock.now = now+481
        for db in (store_db, tools_db): assert db.execute(query).fetchone()[0] == 50005000
        clock.now = now+601
        for db in (store_db, tools_db):
            with pytest.raises(sqlite3.OperationalError, match='interrupted'): db.execute(query).fetchone()
    finally:
        store_db.close(); tools_db.close()
