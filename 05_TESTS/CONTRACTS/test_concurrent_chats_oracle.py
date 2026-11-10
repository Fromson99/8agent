"""Different chats must not block each other on Oracle records (field 2026-11-10).

Field log (code serving 135): /v1/rag/ask failed after 47.6 s with HTTP 500
"BlockingIOError: Oracle record owner is active". One user could use the service, a
second user failed: every chat wrote one shared case database (case-memory/cases-v4),
which on Oracle is one record namespace with one write lease.

Runs the actual service.py entry with Oracle-only records (adr_1244 local Oracle fixture,
scripted model). Another chat's write lease is held explicitly, which is what a second
user saw while the first user's request was writing.
"""
import asyncio
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[2]
CODE = Path(os.environ.get('WORKFLOW_TEST_CODE_ROOT', ROOT))
_spec = importlib.util.spec_from_file_location('adr_1244_concurrent_chats', ROOT/'06_TOOLS/EXPERIMENTS/adr_1244/test_oracle_service.py')
_base = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_base)
native_oracle = _base.native_oracle  # noqa: F401  (fixture)
published = _base.published  # noqa: F401  (fixture)
structured_generation = _base.structured_generation  # noqa: F401  (fixture)

RUNTIME = '/__oracle_agent__/runtime'
QUESTION = '모의승인규정 제1조의 승인 대상은?'


def service(native_oracle, tmp_path, monkeypatch):
    """The adr_1244 entry setup with shortcut capture on (the field default)."""
    client, generation, namespace = native_oracle
    from semantic_runtime import detailed_log_storage as details
    logs = tmp_path/'synthetic-nfs-logs'; monkeypatch.setenv('GENOS_SHARED_LOG_DIR', str(logs))
    monkeypatch.setattr(details, 'require_nfs', lambda p: Path(p).resolve())
    import test_unified_legal_agent as cases
    from test_bounded_source_main import settings
    from semantic_runtime import oracle_query_service as serving, app as application
    sp = importlib.util.spec_from_file_location('concurrent_chats_service_'+uuid.uuid4().hex, CODE/'service.py')
    entry = importlib.util.module_from_spec(sp); sp.loader.exec_module(entry)
    monkeypatch.setattr(entry, '_provider', lambda *args: object())
    transport = cases.ScriptedTransport()
    monkeypatch.setattr(entry, '_genos_v5_environment_binding', lambda *args: ({**settings(), 'max_model_attempts': 40}, transport))
    monkeypatch.setattr(serving, 'client_from_environment', lambda: client)
    monkeypatch.setattr(serving.Factory, 'start_recovery', lambda self: None)
    create = application.create_app

    def with_identity(*args, **kwargs):
        kwargs['memory_identity'] = lambda request: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d']}
        app = create(*args, **kwargs)
        app.state.pipeline.contracts.pipeline['shortcut_v4']['features']['capture'] = True
        return app
    monkeypatch.setattr(application, 'create_app', with_identity)
    connect = sqlite3.connect

    def only_memory(database, *args, **kwargs):
        assert str(database) == ':memory:' or 'mode=memory' in str(database), str(database)
        return connect(database, *args, **kwargs)
    monkeypatch.setattr(sqlite3, 'connect', only_memory)
    with serving.request_context():
        entry.application()

    def ask(session, request_id, question=QUESTION):
        started = time.monotonic()
        out = asyncio.run(entry.service({}, {'op': 'call', 'method': 'POST', 'path': '/v1/rag/ask', 'json': {
            'question': question, 'session_id': session, 'request_id': request_id, 'use_llm': True}}))
        return out, time.monotonic()-started
    return ask, client, namespace


def records(client, namespace):
    from semantic_runtime.oracle_agent_records import AgentRecords, RecordSQL
    return AgentRecords(RecordSQL(client, binding='concurrent-chats', deadline=time.monotonic()+600, max_calls=10000),
                        namespace=namespace)


def held(store, key, ready, release):
    with store.lease(key):
        ready.set(); release.wait(120)


def hold(store, key):
    ready, release = threading.Event(), threading.Event()
    thread = threading.Thread(target=held, args=(store, key, ready, release), daemon=True)
    thread.start(); assert ready.wait(60)
    return release, thread


def test_another_chats_write_lease_does_not_block_this_chat(native_oracle, tmp_path, monkeypatch):
    ask, client, namespace = service(native_oracle, tmp_path, monkeypatch)
    # The shared store a pre-fix service wrote for every chat, held by "the first user".
    release, thread = hold(records(client, namespace), ['sql-transaction', RUNTIME+'/case-memory/cases-v4.sqlite'])
    try:
        out, seconds = ask('user-b-chat', 'b-1')
    finally:
        release.set(); thread.join(30)
    assert out['status'] == 200, (out['status'], str(out.get('body'))[:600])
    assert seconds < 25, seconds  # pre-fix: waited 30 s for the shared lease, then failed
    assert not client.errors, client.errors


def test_same_chat_busy_is_409_not_500(native_oracle, tmp_path, monkeypatch):
    ask, client, namespace = service(native_oracle, tmp_path, monkeypatch)
    from semantic_runtime.session_identity import selectors
    from semantic_runtime.legal_agent.shortcut_store import chat_key
    team, session, key = selectors({'session_id': 'busy-chat', 'team_id': 'risk_team'})
    path = RUNTIME+'/case-memory/chats/'+chat_key(team, 'team-session-v1:'+key)+'/cases-v4.sqlite'
    release, thread = hold(records(client, namespace), ['sql-transaction', path])
    try:
        out, _ = ask('busy-chat', 'busy-1')
    finally:
        release.set(); thread.join(30)
    assert out['status'] == 409, (out['status'], str(out.get('body'))[:600])
    assert '처리 중' in out['body']['message']  # shown to the user instead of a 500 failure


def test_two_chats_in_parallel_then_follow_up_in_each(native_oracle, tmp_path, monkeypatch):
    ask, client, namespace = service(native_oracle, tmp_path, monkeypatch)
    results = {}

    def run(name):
        results[name] = ask(name, name+'-1')
    threads = [threading.Thread(target=run, args=(name,)) for name in ('chat-a', 'chat-b')]
    for t in threads: t.start()
    for t in threads: t.join(600)
    for name in ('chat-a', 'chat-b'):
        out, _ = results[name]
        assert out['status'] == 200, (name, out['status'], str(out.get('body'))[:600])
    # Same chat, same request: the stored answer comes back from that chat's own database.
    again, _ = ask('chat-a', 'chat-a-1')
    assert again['status'] == 200 and again['body']['answer'] == results['chat-a'][0]['body']['answer']
    with client.db.cursor() as c:
        from semantic_runtime import oracle_dp_io as io
        scope = io.digest({'format': 'oracle-agent-namespace-v1', 'namespace': namespace})
        c.execute("SELECT COUNT(DISTINCT ST_KEY_ID) FROM SIDDA.LGL_EXEC_ST_A WHERE SCOPE_HASH_VAL=:scope "
                  "AND ST_KEY_ID LIKE 'a1:head:%'", scope=scope)
        heads = c.fetchone()[0]
    assert heads > 0
    # Two new chats may create the shared parent folder case-memory/chats at the same moment:
    # one lease INSERT loses (ORA-00001) and the lease code waits and re-reads. Anything else is a fault.
    unexpected = [e for e in client.errors if not ('ORA-00001' in str(e) and 'EXEC_ST' in str(e))]
    assert not unexpected, unexpected
