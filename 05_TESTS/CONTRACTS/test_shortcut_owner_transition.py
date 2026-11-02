"""Intake-to-case handoff retains both locks until the request leaves its owner."""
from contextlib import ExitStack

import pytest

from semantic_runtime.legal_agent.corrected_memory import Conflict
from semantic_runtime.legal_agent.shortcut_cases import ShortcutCases


@pytest.mark.parametrize('interrupt', [False, True])
def test_new_case_blocks_same_session_and_other_session_then_releases(tmp_path, interrupt):
    principal = {'user_id': 'synthetic', 'team_id': 'risk_team',
                 'authenticated': True, 'document_ids': ['d']}
    body = {'session_id': 'first', 'request_id': 'r1', 'question': '모의 기준', 'document_ids': ['d']}
    path = tmp_path / 'cases.sqlite'
    with ExitStack() as cleanup:
        repos = [ShortcutCases(path, None, None) for _ in range(3)]
        for repo in repos:
            cleanup.callback(repo.close)
        first, second, unrelated = repos
        try:
            with first.owner(body, principal):
                case = first.shortcut.connect(first.intake_id, principal)
                first._own_investigation(case['id'], principal)
                linked = {**body, 'session_id': 'other', 'investigation_id': case['id']}
                for competitor in (body, linked):
                    with pytest.raises(Conflict, match='being updated'):
                        with second.owner(competitor, principal):
                            pytest.fail('competing owner entered an active request')
                    assert first.owner_held
                with unrelated.owner({**body, 'session_id': 'independent'}, principal):
                    assert unrelated.owner_held
                if interrupt:
                    raise RuntimeError('injected owner interruption')
        except RuntimeError as exc:
            assert interrupt and str(exc) == 'injected owner interruption'
        assert not first.owner_held
        for competitor in (body, linked):
            with second.owner(competitor, principal):
                assert second.owner_held
