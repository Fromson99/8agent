"""Team/session selectors behind the existing GENOS platform access boundary.

The legacy owner column is a storage key, not a login user or an access grant.
Only ingress calls bind(); stored/internal requests are never bound a second time.
"""
import hashlib
import json
import os
import re

POLICY = 'team-session-v1'


def stable(value, field):
    if (not isinstance(value, str) or not value.strip() or len(value) > 256
            or value in ('anonymous', 'sess-anonymous') or any(ord(c) < 32 for c in value)):
        raise ValueError('안정적인 ' + field + '가 필요합니다.')
    return value


def selectors(body, trusted=None):
    if trusted is not None and not isinstance(trusted,dict):
        raise ValueError('서버의 팀·문서 범위를 확인할 수 없습니다.')
    trusted = trusted or {}
    team = trusted.get('team_id') or os.environ.get('TEAM_ID') or body.get('team_id')
    from .team_scope import validate_team_id
    validate_team_id(team)
    if body.get('team_id') is not None and body['team_id'] != team:
        raise ValueError('서버에 지정된 팀과 요청의 team_id가 다릅니다.')
    session = stable(body.get('session_id'), 'session_id')
    key = hashlib.sha256(json.dumps([POLICY, team, session], ensure_ascii=False,
                                   separators=(',', ':')).encode()).hexdigest()
    return team, session, key


def bind(body, trusted=None):
    team, session, key = selectors(body, trusted)
    # Namespace both columns: legacy memory-v2/v3 has a globally unique session PK.
    # Ignoring incoming user_id also makes retries independent of login metadata.
    value = {**body, 'team_id': team, 'session_id': POLICY + ':' + key,
             'user_id': 'session:' + key}
    principal = {**(trusted or {}), 'team_id': team, 'user_id': value['user_id']}
    return value, principal


def public_result(value, session):
    if not isinstance(value, dict) or session is None:
        return value
    return {k: session if k in ('session_id', 'original_session_id') else v for k, v in value.items()}


def reject_legacy(runtime, body):
    """Do not silently start a new budget/history over an old user-owned chat.

Inspect only selected state metadata, never original documents or indexes.
Immutable old events are left for the previous revision or explicit migration.
"""
    from .oracle_runtime_paths import Path
    from .state_sqlite import readonly
    from .legal_agent.shortcut_store import selected_store
    team, session, _ = selectors(body)
    candidates = {session, 's-' + hashlib.sha256(session.encode()).hexdigest(),
                  re.sub(r'[^A-Za-z0-9_.:-]', '-', session).strip('-')[:64]}
    marks = ','.join('?' for _ in candidates)
    runtime = Path(runtime)
    paths = {selected_store(runtime), runtime/'case-memory/cases-v3.sqlite',
             runtime/'corrected-memory/memory-v2.sqlite'}
    for path in paths:
        if not path.is_file():
            continue
        db = readonly(path)
        try:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            found = False
            if {'sw_intake', 'sw_scope'} <= tables:
                found = db.execute('SELECT 1 FROM sw_intake i JOIN sw_scope s ON s.id=i.scope '
                                   f'WHERE i.session IN ({marks}) AND s.team=? LIMIT 1',
                                   (*candidates, team)).fetchone() is not None
            if not found and 'session' in tables:
                found = db.execute(f'SELECT 1 FROM session WHERE id IN ({marks}) AND team=? LIMIT 1',
                                   (*candidates, team)).fetchone() is not None
            if found:
                raise ValueError('SESSION_LEGACY_BINDING: 이전 사용자 기준 대화 기록을 보존했습니다. '
                                 '새 채팅 세션에서 시작하세요. 이전 실행은 원래 코드 리비전에서 재개해야 합니다.')
        finally:
            db.close()
