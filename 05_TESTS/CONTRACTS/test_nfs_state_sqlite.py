"""NFS policy branch on local synthetic files; no actual NFS certification."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from semantic_runtime import state_sqlite
from semantic_runtime.ad_store import Store
from semantic_runtime.ad_backend import Backend
from semantic_runtime.ad_mode import handle
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
from semantic_runtime.legal_agent.shortcut_cases import ShortcutCases
from test_structure_first_search import structured_generation


@pytest.fixture
def nfs_policy(monkeypatch):
    monkeypatch.delenv('GENOS_MEMORY_JOURNAL_MODE', raising=False)
    monkeypatch.setattr(state_sqlite, 'filesystem', lambda _: 'nfs4')


def test_actual_deepest_mount_and_escaped_mountpoint(monkeypatch):
    original = Path.read_text
    def mounts(path, *args, **kwargs):
        if str(path) == '/proc/mounts':
            return 'root / ext4 rw 0 0\nserver /tmp/nfs\\040test nfs4 rw 0 0\ndisk /tmp/nfs\\040test/local ext4 rw 0 0\n'
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', mounts)
    assert state_sqlite.filesystem('/tmp/nfs test/db.sqlite') == 'nfs4'
    assert state_sqlite.filesystem('/tmp/nfs test/local/db.sqlite') == 'ext4'


def test_nfs_shortcut_and_ad_share_delete_without_env(tmp_path, nfs_policy):
    path = tmp_path / 'cases-v4.sqlite'
    repo = ShortcutRepository(path)
    principal = {'user_id': 'u', 'team_id': 't', 'authenticated': True, 'document_ids': ['d']}
    body = {'question': '합성 질문', 'session_id': 's', 'request_id': 'r', 'document_ids': ['d']}
    received = repo.intake(body, principal)
    case = repo.connect(received['id'], principal)
    assert repo.db.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
    repo.close()
    store = Store(path)
    try:
        backend = Backend(store, 't')
        assert backend.list('shortcut')[0]['id'] == case['id']
        assert store.db.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
        assert store.db.execute('PRAGMA synchronous').fetchone()[0] == 2
        assert store.db.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert store.db.execute('PRAGMA busy_timeout').fetchone()[0] == 30000
    finally: store.close()
    enter = handle(path, 't', 'genos', 'chat', '[AD모드 시작]', 'ad-enter')
    assert enter['ad_mode'] is True
    listed = handle(path, 't', 'genos', 'chat', 'shortcut 목록', 'ad-list')
    assert listed['answer_status'] == 'administration'
    assert handle(path, 't', 'genos', 'chat', '[AD모드 종료]', 'ad-exit')['ad_mode'] is False
    reopened = ShortcutRepository(path)
    try:
        assert reopened.event(received['event'], principal)['payload']['text'] == '합성 질문'
        assert reopened.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert reopened.db.execute('PRAGMA foreign_key_check').fetchall() == []
    finally: reopened.close()


def test_nfs_case_adapter_borrowed_connection_matches_policy(tmp_path, nfs_policy):
    cases = ShortcutCases(tmp_path / 'cases-v4.sqlite', None, None)
    try:
        assert cases.shortcut.db is cases.db
        assert cases.db.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
        assert cases.db.execute('PRAGMA user_version').fetchone()[0] == 4
    finally: cases.close()


def test_local_wal_and_explicit_delete_remain_supported(tmp_path, monkeypatch):
    monkeypatch.setattr(state_sqlite, 'filesystem', lambda _: 'ext4')
    monkeypatch.delenv('GENOS_MEMORY_JOURNAL_MODE', raising=False)
    repo = ShortcutRepository(tmp_path / 'wal.sqlite')
    assert repo.db.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
    repo.close()
    monkeypatch.setenv('GENOS_MEMORY_JOURNAL_MODE', 'DELETE')
    cases = ShortcutCases(tmp_path / 'delete.sqlite', None, None)
    assert cases.db.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
    cases.close()


def test_explicit_wal_on_nfs_fails_before_creation(tmp_path, nfs_policy, monkeypatch):
    monkeypatch.setenv('GENOS_MEMORY_JOURNAL_MODE', 'WAL')
    path = tmp_path / 'blocked.sqlite'
    with pytest.raises(ValueError, match='WAL is unsupported'): ShortcutRepository(path)
    assert not path.exists()


def test_existing_delete_data_is_not_recreated(tmp_path, nfs_policy):
    path = tmp_path / 'cases-v4.sqlite'
    repo = ShortcutRepository(path)
    repo.db.execute('CREATE TABLE preserve(value TEXT)')
    repo.db.execute("INSERT INTO preserve VALUES('original')")
    repo.close()
    store = Store(path)
    assert store.db.execute('SELECT value FROM preserve').fetchone()[0] == 'original'
    store.close()


def test_nfs_policy_through_current_v6_ingress(tmp_path, structured_generation, nfs_policy):
    from semantic_runtime.app import create_app
    from test_unified_legal_agent import ScriptedTransport
    from test_bounded_source_main import settings
    from test_legal_agent_double_harness import ROOT
    transport = ScriptedTransport()
    principal = {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d'], 'authenticated': True}
    app = create_app(tmp_path, structured_generation, contracts_root=ROOT, provider=object(),
                     implementation='legal-agent-unified-v6', legal_agent_profile=settings(),
                     legal_agent_transport=transport, memory_identity=lambda _: principal)
    app.state.pipeline.contracts.pipeline['shortcut_v4'] = {'features': {'capture': True}}
    with TestClient(app) as client:
        body = {'question': '안녕하세요', 'session_id': 's', 'request_id': 'r'}
        response = client.post('/v1/rag/ask', json=body)
        assert response.status_code == 200, response.text
        repeated = client.post('/v1/rag/ask', json=body)
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()['run_id'] == response.json()['run_id']
    repo = ShortcutRepository(tmp_path / '90_RUNTIME/semantic/case-memory/cases-v4.sqlite')
    try:
        assert repo.db.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
        assert repo.db.execute("SELECT count(*) FROM sw_intake WHERE status='COMPLETED'").fetchone()[0] == 1
    finally: repo.close()


CHILD = '''
import json,os,sys
from semantic_runtime import state_sqlite
state_sqlite.filesystem=lambda _: 'nfs4'
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
r=ShortcutRepository(sys.argv[1]);mode=sys.argv[2]
p={'user_id':'u','team_id':'t','authenticated':True,'document_ids':['d']}
b={'question':'original','session_id':'s','request_id':'same','document_ids':['d']}
i=r.intake(b,p)
if mode=='intake':r.close();sys.exit(0)
with r.transaction():
 r.db.execute("INSERT INTO synthetic VALUES('pending')")
 if mode=='rollback':os._exit(73)
os._exit(73)
'''


def test_two_process_writers_and_abrupt_exit_rollback(tmp_path, nfs_policy):
    path = tmp_path / 'cases-v4.sqlite'
    repo = ShortcutRepository(path)
    repo.db.execute('CREATE TABLE synthetic(value TEXT)')
    repo.close()
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[2] / '02_BACKEND')}
    env.pop('GENOS_MEMORY_JOURNAL_MODE', None)
    args = [sys.executable, '-c', CHILD, str(path)]
    children = [subprocess.Popen(args + ['intake'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(3)]
    for child in children:
        _, stderr = child.communicate(timeout=20)
        assert child.returncode == 0, stderr.decode()
    for mode in ('rollback', 'commit'):
        child = subprocess.run(args + [mode], env=env, capture_output=True, timeout=20)
        assert child.returncode == 73, child.stderr.decode()
        repo = ShortcutRepository(path)
        try:
            assert repo.db.execute('SELECT count(*) FROM sw_intake').fetchone()[0] == 1
            assert repo.db.execute('SELECT count(*) FROM synthetic').fetchone()[0] == int(mode == 'commit')
            assert repo.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        finally: repo.close()
