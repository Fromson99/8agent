"""Structure precedes the single combined glossary review and serving build."""
import sys
from pathlib import Path
import pytest

COMMANDS = Path(__file__).resolve().parents[3] / '06_TOOLS/COMMANDS'
sys.path.insert(0, str(COMMANDS))
import composed_build


def _paths(tmp_path, monkeypatch):
    from lawrag.pipeline import glossary_review
    monkeypatch.setattr(glossary_review, 'configured_paths',
                        lambda: {'glossary': tmp_path / 'base'})


def test_all_structure_precedes_combined_review(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    calls = []
    assert composed_build.run(['--run-id', 'new-001', '--execute', '--exclude-internal'],
                             call=lambda argv: calls.append(argv[3:]) or 0) == 0
    assert calls == [
        ['build-data-stages', '--run-id', 'new-001', '--stage', 'structure', '--execute', '--exclude-internal'],
        ['glossary', 'knowledge', 'check'],
        ['document-release', 'build', '--run-id', 'new-001', '--glossary-dir', str(tmp_path / 'base'), '--max-review-jobs', '100'],
    ]


@pytest.mark.parametrize('failed_unit,code', [('document-release', 3), ('structure', 2), ('knowledge', 2)])
def test_failure_stops_downstream(tmp_path, monkeypatch, failed_unit, code):
    _paths(tmp_path, monkeypatch)
    calls = []
    def call(argv):
        calls.append(argv[3:])
        return code if failed_unit in argv else 0
    assert composed_build.run(['--run-id', 'new-001', '--execute'], call=call) == code
    assert failed_unit in calls[-1]
    if failed_unit == 'structure':
        assert len(calls) == 1


def test_check_only_does_not_prepare_old_glossary_review(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    calls = []
    assert composed_build.run(['--run-id', 'new-001', '--check-only'],
        call=lambda argv: calls.append(argv[3:]) or 0) == 0
    assert calls == [
        ['build-data-stages', '--run-id', 'new-001', '--stage', 'structure', '--check-only'],
        ['glossary', 'knowledge', 'check'],
    ]


@pytest.mark.parametrize('option', ['--knowledge-zip', '--publish', '--stage'])
def test_legacy_or_owned_flags_are_rejected_before_model_calls(option):
    with pytest.raises(SystemExit) as exc:
        composed_build.run(['--run-id', 'new-001', '--execute', option, 'value'],
                           call=lambda argv: pytest.fail('unexpected model call'))
    assert exc.value.code == 2


def test_explicit_completed_glossary_reused_and_bases_forwarded(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    glossary = tmp_path / 'prior-reviewed'; calls = []
    assert composed_build.run(['--run-id', 'next', '--execute', '--glossary-dir', str(glossary),
                              '--base-generation', '/selected/base', '--exclude-document', 'old-id',
                              '--max-review-jobs', '7', '--retry-review-failed'],
                             call=lambda argv: calls.append(argv[3:]) or 0) == 0
    assert ['document-release', 'verify-glossary', '--glossary-dir', str(glossary)] == calls[1]
    assert calls[-1][-7:] == ['--max-review-jobs', '7', '--base-generation', '/selected/base', '--exclude-document', 'old-id', '--retry-review-failed']
