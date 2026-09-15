"""The aggregate command calls the maintained units in dependency order."""
import sys
from pathlib import Path

import pytest


COMMANDS = Path(__file__).resolve().parents[3] / '06_TOOLS/COMMANDS'
sys.path.insert(0, str(COMMANDS))
import composed_build  # noqa: E402


def _paths(tmp_path, monkeypatch):
    from lawrag.pipeline import genos_stages, glossary_linking, glossary_review

    state = tmp_path / 'state'
    state.mkdir()
    output = tmp_path / 'reviewed'
    monkeypatch.setattr(glossary_review, 'configured_paths',
                        lambda: {'state': state, 'output': output, 'glossary': tmp_path / 'base'})
    monkeypatch.setattr(genos_stages, 'offline_data_root', lambda root: tmp_path)
    monkeypatch.setattr(glossary_linking, 'configured', lambda root, data: output)
    return state, output


def test_execute_reviews_before_document_unit(tmp_path, monkeypatch):
    _, output = _paths(tmp_path, monkeypatch)
    calls = []
    code = composed_build.run(['--run-id', 'new-001', '--execute',
        '--max-review-jobs', '25', '--exclude-internal', '--max-calls', '4'],
        call=lambda argv: calls.append(argv) or 0)
    assert code == 0
    assert calls[0][3:] == ['glossary', 'knowledge', 'check']
    assert calls[1][3:] == ['glossary', 'review', 'complete', '--max-jobs', '25']
    assert calls[2][3:] == ['build-data-stages', '--run-id', 'new-001', '--stage', 'all',
                          '--glossary-dir', str(output), '--execute', '--exclude-internal',
                          '--max-calls', '4']


def test_pending_review_stops_before_document_unit(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    calls = []
    assert composed_build.run(['--run-id', 'new-001', '--execute'],
        call=lambda argv: calls.append(argv) or (0 if argv[4:6]==['knowledge','check'] else 3)) == 3
    assert len(calls) == 2


def test_wrong_review_selection_cannot_reach_document_unit(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    from lawrag.pipeline import glossary_linking
    monkeypatch.setattr(glossary_linking, 'configured', lambda root, data: tmp_path / 'older')
    calls = []
    with pytest.raises(ValueError, match='does not match'):
        composed_build.run(['--run-id', 'new-001', '--execute'],
                           call=lambda argv: calls.append(argv) or 0)
    assert len(calls) == 2


def test_check_only_plans_and_checks_without_execute(tmp_path, monkeypatch):
    state, _ = _paths(tmp_path, monkeypatch)
    state.rmdir()
    calls = []
    assert composed_build.run(['--run-id', 'new-001', '--check-only'],
        call=lambda argv: calls.append(argv) or 0) == 0
    assert [c[3:6] for c in calls] == [
        ['glossary', 'knowledge', 'check'],
        ['glossary', 'review', 'prepare'],
        ['glossary', 'review', 'status'],
        ['build-data-stages', '--run-id', 'new-001'],
    ]
    assert '--execute' not in [arg for call in calls for arg in call]


def test_missing_knowledge_stops_before_review_or_models():
    calls=[]
    assert composed_build.run(['--run-id','new-001','--execute'],
        call=lambda argv:calls.append(argv) or 2)==2
    assert len(calls)==1
    assert calls[0][3:]==['glossary','knowledge','check']


@pytest.mark.parametrize('option', ['--knowledge-zip', '--publish', '--stage', '--glossary-dir'])
def test_legacy_or_owned_flags_are_rejected_before_model_calls(option):
    with pytest.raises(SystemExit) as exc:
        composed_build.run(['--run-id', 'new-001', '--execute', option, 'value'],
                           call=lambda argv: pytest.fail('unexpected model call'))
    assert exc.value.code == 2
