import importlib.util
import json
from pathlib import Path
import subprocess
import pytest
from semantic_runtime.contracts import sha
from lawrag.pipeline import structure_selection, document_release
from test_document_release_stages import failed_run

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('selected_only', ROOT / '06_TOOLS/OFFLINE/genos_selected_only_release.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
PARENT = 'financial-risk-full-e2e-20260930-r3'
OLD = 'financial-risk-success-20261001-r1'
NEW = 'financial-risk-success-20261001-r2'


def setup(data):
    (data / 'LOGS/failed').rename(data / 'LOGS' / PARENT)
    (data / 'LOGS' / PARENT / 'reference-model-profile.json').write_text('{}')
    structure_selection.select_completed(data, PARENT, OLD, allow_incomplete=True, reason='모의 실패 보류')


def test_freeze_reuses_exact_scope_preserves_original_and_resumes(failed_run):
    data = failed_run
    setup(data)
    old_files = {p: sha(p) for p in (data / 'LOGS' / OLD).iterdir() if p.is_file()}
    result = tool.freeze(data, expected_count=1)
    assert result['selected'] == 1 and result['omitted'] == 2
    assert tool.freeze(data, expected_count=1) == result
    assert all(sha(p) == expected for p, expected in old_files.items())
    paths, _ = document_release.selected_sources(data, NEW, [])
    assert len(paths) == 1 and 'STRUCTURE' in paths[0].parts
    assert not (data / 'TERM_RELEASES' / OLD).exists()
    assert not (data / 'generations/CURRENT.json').exists()


def test_unexpected_scope_stops_before_new_run(failed_run):
    setup(failed_run)
    with pytest.raises(ValueError, match='count'):
        tool.freeze(failed_run)
    assert not (failed_run / 'LOGS' / NEW).exists()


def test_parent_drift_stops_before_new_run(failed_run):
    setup(failed_run)
    path = failed_run / 'LOGS' / PARENT / 'structure-selection.json'
    value = json.loads(path.read_text())
    value['documents'] = {}
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='Parent successes changed'):
        tool.freeze(failed_run, expected_count=1)
    assert not (failed_run / 'LOGS' / NEW).exists()


def test_handoff_embeds_exact_sources_and_field_python():
    path = ROOT / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_SELECTED_ONLY_BUILD_R1_UTF8.txt'
    txt = path.read_text()
    selection = txt.split("<<'GENOS_SELECT_PY'\n", 1)[1].split('\nimport os\nfreeze(', 1)[0]
    compile(selection, str(path), 'exec')  # Preserve the previously mailed R1 bytes.
    progress = txt.split("<<'GENOS_PROGRESS_PY'\n", 1)[1].rsplit('\nGENOS_PROGRESS_PY', 1)[0]
    compile(progress, str(path), 'exec')
    assert 'python3 -u -' in txt and '.venv/bin/python' not in txt
    assert 'selected_args=(--build --selected-only)' in txt
    subprocess.run(['bash', '-n', str(path)], check=True)


def test_replace_uses_new_run_and_preserves_failed_plan(failed_run):
    setup(failed_run)
    failed = failed_run / 'TERM_RELEASES' / NEW / 'plan.json'
    failed.parent.mkdir(parents=True)
    failed.write_text('{"old_policy":"append"}')
    before = sha(failed)
    target = 'financial-risk-success-20261001-r3'
    result = tool.freeze(failed_run, expected_count=1, new_run=target, replace_corpus=True)
    assert result['run_id'] == target and sha(failed) == before
    assert not (failed_run / 'TERM_RELEASES' / target).exists()


def test_replace_handoff_exact_sources_and_correct_policy():
    path = ROOT / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_SELECTED_ONLY_BUILD_R2_UTF8.txt'
    txt = path.read_text()
    selection = txt.split("<<'GENOS_SELECT_PY'\n", 1)[1].split('\nimport os\nfreeze(', 1)[0]
    compile(selection, str(path), 'exec')  # R2 remains the previously mailed bytes.
    progress = txt.split("<<'GENOS_PROGRESS_PY'\n", 1)[1].rsplit('\nGENOS_PROGRESS_PY', 1)[0]
    compile(progress, str(path), 'exec')
    assert '--glossary-corpus-policy replace' in txt and 'replace_corpus=True' in txt
    assert '--run-id financial-risk-success-20261001-r3' in txt
    assert '.venv/bin/python' not in txt
    subprocess.run(['bash', '-n', str(path)], check=True)


def test_changed_only_log_handoff_preserves_run_and_policy():
    path = ROOT / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_SELECTED_ONLY_BUILD_R3_UTF8.txt'
    txt = path.read_text()
    progress = txt.split("<<'GENOS_PROGRESS_PY'\n", 1)[1].rsplit('\nGENOS_PROGRESS_PY', 1)[0]
    assert progress == (ROOT / '06_TOOLS/OFFLINE/genos_release_progress.py').read_text()
    assert '--run-id financial-risk-success-20261001-r3' in txt
    assert '--glossary-corpus-policy replace' in txt
    assert 'hot-updated' in txt
    assert '준비: 용어 출현 위치 재탐색' in progress
    subprocess.run(['bash', '-n', str(path)], check=True)
