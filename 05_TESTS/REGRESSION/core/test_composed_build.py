"""Structure precedes the single combined glossary review and serving build."""
import sys
from pathlib import Path
import pytest

COMMANDS = Path(__file__).resolve().parents[3] / '06_TOOLS/COMMANDS'
sys.path.insert(0, str(COMMANDS))
import composed_build


@pytest.fixture(autouse=True)
def reviewed_compatibility_policy(monkeypatch):
    monkeypatch.setattr(composed_build, 'build_policy', lambda: 'reviewed')


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


def test_completed_reference_review_is_forwarded_only_to_release(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    review = tmp_path / 'reference-review'
    calls = []
    assert composed_build.run(
        ['--run-id', 'with-references', '--execute',
         '--reference-review-state', str(review)],
        call=lambda argv: calls.append(argv[3:]) or 0,
    ) == 0
    assert all('--reference-review-state' not in call for call in calls[:-1])
    assert calls[-1][-2:] == ['--reference-review-state', str(review.resolve())]


def test_replace_glossary_document_evidence_reaches_release(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    calls = []
    assert composed_build.run(
        ['--run-id', 'fresh-linked', '--execute', '--glossary-corpus-policy', 'replace'],
        call=lambda argv: calls.append(argv[3:]) or 0,
    ) == 0
    assert all('--glossary-corpus-policy' not in call for call in calls[:-1])
    assert calls[-1][-2:] == ['--glossary-corpus-policy', 'replace']


def test_reference_model_and_budgets_reach_final_release_only(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    calls = []
    profile = tmp_path / 'reference-profile.json'
    assert composed_build.run(['--run-id', 'model-linked', '--execute',
                              '--reference-model-profile', str(profile), '--max-reference-cases', '16',
                              '--reference-batch-size', '4'], call=lambda argv: calls.append(argv[3:]) or 0) == 0
    assert all('--reference-model-profile' not in call for call in calls[:-1])
    assert calls[-1][-6:] == ['--reference-model-profile', str(profile.resolve()),
                              '--max-reference-cases', '16', '--reference-batch-size', '4']


def test_main_no_model_policy_uses_native_structure_and_existing_r8(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    monkeypatch.setattr(composed_build, 'build_policy', lambda: 'native-no-models')
    calls = []
    assert composed_build.run(['--run-id', 'team-native', '--execute'],
                             call=lambda argv: calls.append(argv[3:]) or 0) == 0
    assert calls == [
        ['build-data-stages', '--run-id', 'team-native', '--stage', 'structure', '--execute',
         '--structure-vlm', 'off', '--pdf-conversion', 'off', '--pdf-parser', 'local'],
        ['document-release', 'prepare', '--run-id', 'team-native', '--glossary-dir', str(tmp_path / 'base'),
         '--glossary-corpus-policy', 'replace'],
        ['document-release', 'reindex', '--from-run-id', 'team-native', '--run-id', 'team-native-index'],
    ]


@pytest.mark.parametrize('option', ['--reference-model-profile', '--reference-review-state', '--retry-review-failed'])
def test_no_model_build_rejects_review_options_before_structure(option):
    arguments = ['--run-id', 'team-native', '--no-models', '--execute', option]
    if option != '--retry-review-failed':
        arguments.append('/model-or-review')
    with pytest.raises(SystemExit):
        composed_build.run(arguments, call=lambda _: pytest.fail('No dependent work should run'))


def test_no_model_structure_failure_prevents_r8_index(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    calls = []
    assert composed_build.run(['--run-id', 'native-failed', '--no-models', '--execute'],
                             call=lambda argv: calls.append(argv[3:]) or 2) == 2
    assert len(calls) == 1


def test_reviewed_mode_can_be_selected_explicitly(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    monkeypatch.setattr(composed_build, 'build_policy', lambda: 'native-no-models')
    calls = []
    assert composed_build.run(['--run-id', 'reviewed', '--with-model-review', '--execute'],
                             call=lambda argv: calls.append(argv[3:]) or 0) == 0
    assert calls[-1][:2] == ['document-release', 'build']
