"""Relation scans have only the request deadline, with real SQLite cancellation."""
from dataclasses import replace
from types import SimpleNamespace
import sqlite3
import time

import pytest

from semantic_runtime.legal_agent.context import RequestContext
from semantic_runtime.legal_agent.errors import DeadlineExceeded, ToolExecutionError
from semantic_runtime.legal_agent.relations_tools import RelationsTools as V3Tools
from semantic_runtime.legal_agent.tiers_tools import TiersTools as V4Tools
from semantic_runtime.legal_agent.workflow_relations_tools import RelationsTools as WorkflowTools
from semantic_runtime.legal_agent.workflow_tiers_tools import TiersTools as V5Tools
from test_legal_agent_double_harness import generation
from test_tool_exploration_v3 import session as v3_session, read, tool
from test_source_tiers_v4 import session as v4_session
from test_legal_agent_v5 import session as v5_session


@pytest.mark.parametrize('tools_class', [V3Tools, V4Tools, WorkflowTools, V5Tools])
@pytest.mark.parametrize('page_size', [2, 12])
def test_python_relation_scan_runs_past_five_seconds_and_keeps_cursor(monkeypatch, tools_class, page_size):
    clock = [100.0]
    monkeypatch.setattr(time, 'monotonic', lambda: clock[0])
    sources = tools_class.__new__(tools_class)
    sources.context = RequestContext.create({'question': 'synthetic'}, {}, {}, 300)
    # Existing pinned profiles can still carry the obsolete five-second value.
    sources.profile = {'relation_scan_seconds': 5, 'relation_page_size': page_size,
                       'max_relation_chars': 14000}
    sources.materialize = lambda value: value

    def stream(_):
        for i in range(4):
            clock[0] += 6
            yield {'relation_id': str(i)}

    sources.cards = SimpleNamespace(term_relations=stream)
    first, cursor, extra = sources.relation_page('E1', 'term', 0)
    assert [item['relation_id'] for item in first] == [str(i) for i in range(min(page_size, 4))]
    if cursor is None:
        assert extra['scan_status'] == 'COMPLETE'
    else:
        assert cursor == 2 and extra['scan_reason'] == 'PAGE_LIMIT'
        second, cursor, extra = sources.relation_page('E1', 'term', cursor)
        assert [item['relation_id'] for item in first+second] == ['0', '1', '2', '3']
        assert cursor is None and extra['scan_status'] == 'COMPLETE'
    sources.context = replace(sources.context, deadline=clock[0]+1)
    with pytest.raises(DeadlineExceeded):
        sources.relation_page('E1', 'term', 0)


@pytest.mark.parametrize('session_factory', [v3_session, v4_session, v5_session])
@pytest.mark.parametrize('operation', ['follow_relations', 'follow_reference'])
@pytest.mark.parametrize('expired', [False, True])
def test_relation_sql_uses_request_deadline_and_restores_callbacks(
        tmp_path, generation, monkeypatch, session_factory, operation, expired):
    with session_factory(tmp_path, generation) as s:
        read(s)
        anchor = s.work.evidence()[0]['evidence_id']
        action = (tool(operation, target=anchor, family='definition', cursor=None)
                  if operation == 'follow_relations' else
                  tool(operation, evidence=anchor, direction='both', cursor=None))
        original = s.sources.handlers[operation]
        clock = [time.monotonic()]
        monkeypatch.setattr(time, 'monotonic', lambda: clock[0])
        deadline = s.context.deadline
        dbs = [s.sources.store.db, s.sources.tools.db, *s.sources.glossary.dbs.values()]

        def tick():
            clock[0] = deadline+1 if expired else deadline-10
            return 0

        for db in dbs:
            db.create_function('relation_wait_tick', 0, tick)

        def slow_relation(args, offset):
            for db in dbs:
                assert db.execute('''WITH RECURSIVE n(x) AS (
                    VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<2000)
                    SELECT sum(x+relation_wait_tick()) FROM n''').fetchone()[0] == 2001000
            return original(args, offset)

        s.sources.handlers[operation] = slow_relation
        if expired:
            try:
                result = s.sources.execute(action, 'request-deadline-test')
            except ToolExecutionError as exc:
                assert 'OperationalError: interrupted' in str(exc)
            else:
                assert result['status'] == 'ERROR' and 'interrupted' in result['server_reason']
        else:
            result = s.sources.execute(action, 'request-deadline-test')
            assert result['status'] in ('OK', 'EMPTY')
            assert result['scan_status'] == 'COMPLETE'
        # The finally path must leave every connection on the whole-request guard.
        clock[0] = deadline+1
        for db in dbs:
            with pytest.raises(sqlite3.OperationalError, match='interrupted'):
                db.execute('''WITH RECURSIVE n(x) AS (
                    VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<2000)
                    SELECT sum(x) FROM n''').fetchone()
