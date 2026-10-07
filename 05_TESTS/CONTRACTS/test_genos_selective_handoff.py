"""Photographed code bytes, reversible installation and compatible mail deltas.

Synthetic checkouts/responses only; no GENOS access or performance comparison.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '09_ARTIFACTS/HANDOFFS/20260929-selective-compatible-r1'
BUNDLE = OUT / 'bundle'
definition = importlib.util.spec_from_file_location('selective_installer_test', ROOT / '06_TOOLS/OFFLINE/genos_selective_patch.py')
CORE = importlib.util.module_from_spec(definition)
definition.loader.exec_module(CORE)
SPEC = json.loads((BUNDLE / 'SELECTIVE_MANIFEST.json').read_bytes())
PHOTO = SPEC['photo_sha256']
from test_model_decision_repair import work, base_work


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True)


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*')
            if p.is_file() and '.git' not in p.parts and 'TRANSFER' not in p.parts}


def repin(root):
    path = root / '00_SYSTEM/PIPELINE.json'
    pipeline = json.loads(path.read_bytes())
    for row in pipeline['engines'].values():
        manifest_path = root / row['manifest']
        manifest = json.loads(manifest_path.read_bytes())
        manifest['files'] = {name: CORE.sha((root / name).read_bytes()) for name in manifest['files'] if (root / name).exists()}
        manifest_path.write_bytes(CORE.dump(manifest))
        row['sha256'] = CORE.sha(manifest_path.read_bytes())
    def profile(node):
        if isinstance(node, dict):
            name = node.get('path')
            if isinstance(name, str) and name.startswith('00_SYSTEM/') and 'sha256' in node and (root / name).exists():
                node['sha256'] = CORE.sha((root / name).read_bytes())
            for value in node.values():
                profile(value)
        elif isinstance(node, list):
            for value in node:
                profile(value)
    profile(pipeline)
    path.write_bytes(CORE.dump(pipeline))


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / 'DEV'
    root.mkdir()
    with zipfile.ZipFile(ROOT / '09_ARTIFACTS/HANDOFFS/20260929-rag-main-integrated/code.zip') as zipped:
        zipped.extractall(root)
    patch_root = ROOT / '08_DEPLOYMENT/GENOS/patches'
    for name, folder in zip(PHOTO, ('prompt_compaction_20260928_r1', 'answer_stream_20260929_r1', 'chat_flow_20260928_r2')):
        raw = (patch_root / folder / 'payload' / name).read_bytes()
        assert CORE.sha(raw) == PHOTO[name]
        (root / name).write_bytes(raw)
    repin(root)
    git(root, 'init', '-q')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        'add', '-f', '.')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'photographed byte fixture')
    return root


def installed(root, feature='decision-repair', mode='apply'):
    CORE.run(root, BUNDLE, feature, mode)


def test_photo_apply_reapply_rollback_and_data_pins(checkout):
    before = snapshot(checkout)
    pipeline_before = json.loads((checkout / '00_SYSTEM/PIPELINE.json').read_bytes())
    installed(checkout, mode='check')
    assert snapshot(checkout) == before
    installed(checkout)
    after = snapshot(checkout)
    modified = {n for n in before if before[n] != after[n]}
    assert set(PHOTO) <= modified
    assert all(n in PHOTO or '/ENGINES/' in n or n == '00_SYSTEM/PIPELINE.json' for n in modified)
    pipeline_after = json.loads((checkout / '00_SYSTEM/PIPELINE.json').read_bytes())
    assert {k: v for k, v in pipeline_before.items() if k != 'engines'} == {
        k: v for k, v in pipeline_after.items() if k != 'engines'}
    assert b'def plan_request_search(' not in after[next(iter(PHOTO))]
    assert b'def catalogue_observation(' not in after[next(iter(PHOTO))]
    installed(checkout)
    assert snapshot(checkout) == after
    state = checkout / 'TRANSFER' / CORE.BUNDLE_ID
    backup = next(state.glob('backup-*'))
    CORE.rollback(checkout, state, backup)
    assert snapshot(checkout) == before


@pytest.mark.parametrize('feature', [key for key in SPEC['features'] if key != 'decision-repair'])
def test_other_mail_after_repair_preserves_repair_and_reapplies(checkout, feature):
    installed(checkout)
    repaired = {name: (checkout / name).read_bytes() for name in PHOTO}
    installed(checkout, feature)
    installed(checkout, feature)
    CORE.verify_pins(checkout)
    # Older mails cannot reverse the repair even when they change this file.
    for name in PHOTO:
        raw = (checkout / name).read_bytes()
        if 'gateway.py' in name:
            assert b'MODEL_OUTPUT_INVALID' in raw
        elif 'bounded_source_session' in name:
            assert b'data[\'cases\']' in raw
        else:
            assert b'model.output.invalid' in raw
    installed(checkout)
    assert {name: (checkout / name).read_bytes() for name in PHOTO} == repaired


@pytest.mark.parametrize('feature', [key for key, value in SPEC['features'].items() if value['strategy'] == 'merge'])
def test_each_delta_first_install_from_its_exact_preserved_baseline(checkout, feature):
    selected = SPEC['features'][feature]
    for name, row in selected['files'].items():
        option = row['options'][0]
        path = checkout / name
        if option['before'] is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((BUNDLE / option['before']).read_bytes())
    repin(checkout)
    before = snapshot(checkout)
    installed(checkout, feature)
    after = snapshot(checkout)
    for name, row in selected['files'].items():
        assert (checkout / name).read_bytes() == (BUNDLE / row['options'][0]['after']).read_bytes()
    CORE.verify_pins(checkout)
    installed(checkout, feature)
    assert snapshot(checkout) == after
    state = checkout / 'TRANSFER' / CORE.BUNDLE_ID
    backup = next(state.glob('backup-*'))
    CORE.rollback(checkout, state, backup)
    assert snapshot(checkout) == before


@pytest.mark.parametrize('feature', ['answer-stream', 'prompt-compaction', 'chat-flow', 'fulltext-location', 'request-prepare'])
def test_today_mails_before_repair_preserve_scope(checkout, feature):
    installed(checkout, feature)
    installed(checkout)
    installed(checkout, feature)
    CORE.verify_pins(checkout)


def test_unpinned_drift_stops_before_any_source_write(checkout):
    path = checkout / next(iter(PHOTO))
    path.write_bytes(path.read_bytes() + b'\n# site edit without matching pin\n')
    before = snapshot(checkout)
    with pytest.raises(ValueError, match='pin mismatch'):
        installed(checkout)
    assert snapshot(checkout) == before


def test_unknown_repair_function_and_missing_prerequisite_stop_before_write(checkout):
    path = checkout / next(iter(PHOTO))
    path.write_bytes(path.read_bytes().replace(b'max_schema_repairs\': 0', b'max_schema_repairs\': 2'))
    repin(checkout)
    before = snapshot(checkout)
    with pytest.raises(ValueError, match='unknown decision function'):
        installed(checkout)
    assert snapshot(checkout) == before


def test_write_failure_rolls_back_all_bytes(checkout, monkeypatch):
    before = snapshot(checkout)
    original = CORE.atomic
    failed = False
    def interrupt(path, raw):
        nonlocal failed
        if path == checkout / '00_SYSTEM/PIPELINE.json' and not failed:
            failed = True
            raise OSError('synthetic interruption')
        original(path, raw)
    monkeypatch.setattr(CORE, 'atomic', interrupt)
    with pytest.raises(OSError, match='synthetic interruption'):
        installed(checkout)
    assert snapshot(checkout) == before
    installed(checkout)
    CORE.verify_pins(checkout)


def test_rollback_refuses_later_edits_and_zip_inventory(checkout):
    installed(checkout)
    state = checkout / 'TRANSFER' / CORE.BUNDLE_ID
    backup = next(state.glob('backup-*'))
    path = checkout / next(iter(PHOTO))
    path.write_bytes(path.read_bytes() + b'\nLATER_SITE_CHANGE = True\n')
    before = snapshot(checkout)
    with pytest.raises(ValueError, match='later edit preserved'):
        CORE.rollback(checkout, state, backup)
    assert snapshot(checkout) == before
    with zipfile.ZipFile(OUT / 'GENOS_SELECTIVE_20260929_R1.zip') as zipped:
        rows = json.loads(zipped.read('CODE_MANIFEST.json'))['files']
        assert set(zipped.namelist()) == {row['path'] for row in rows} | {'CODE_MANIFEST.json'}
        for row in rows:
            assert CORE.sha(zipped.read(row['path'])) == row['sha256']
            assert not row['path'].endswith(('.js', '.jsx', '.mjs', '.cjs'))


def test_standalone_txt_on_python311_and_current_python(checkout, tmp_path):
    link = tmp_path / 'DEV-link'
    link.symlink_to(checkout, target_is_directory=True)
    for python in [sys.executable] + (['/usr/bin/python3.11'] if Path('/usr/bin/python3.11').exists() else []):
        env = {**os.environ, 'DEPLOY_ROOT': str(link), 'PYTHON_BIN': python, 'MODE': 'apply'}
        result = subprocess.run(['bash', str(OUT / 'GENOS_SELECTIVE_20260929_R1_APPLY.txt')],
                                env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
    CORE.verify_pins(checkout)


def load_photo_modules(checkout, monkeypatch):
    installed(checkout)
    import test_model_decision_repair as contract
    names = [('semantic_runtime.legal_agent._repaired_photo',
              '02_BACKEND/semantic_runtime/legal_agent/bounded_source_session.py', 'BoundedSourceSession'),
             ('semantic_runtime._repaired_progress', '02_BACKEND/semantic_runtime/progress.py', 'ProgressCapture')]
    for module_name, file, attribute in names:
        module = CORE.load_module(checkout / file, module_name)
        monkeypatch.setattr(contract, attribute, getattr(module, attribute))
    return contract


@pytest.mark.parametrize('failure', ['overlap', 'missing', 'unknown', 'duplicate', 'whitespace'])
def test_photo_semantic_errors_repair_before_commit(checkout, work, monkeypatch, failure):
    contract = load_photo_modules(checkout, monkeypatch)
    errors = {'overlap': 'must be disjoint', 'missing': 'should be non-empty',
              'unknown': 'unknown original question segment', 'duplicate': 'duplicate answer demand',
              'whitespace': 'non-whitespace characters'}
    contract.test_question_plan_semantic_errors_correct_before_commit(work, failure, errors[failure])


def test_photo_json_repair_and_progress_hide_response(checkout, work, monkeypatch, tmp_path):
    contract = load_photo_modules(checkout, monkeypatch)
    contract.test_json_and_schema_errors_return_to_model_with_original_view(work, '{broken', 'Expecting property name')
    contract.test_progress_describes_correction_without_raw_response(tmp_path, True)


def test_old_multi_case_plan_validation_is_repairable(checkout, work, monkeypatch):
    contract = load_photo_modules(checkout, monkeypatch)
    from semantic_runtime.legal_agent import source_query_planning as planning
    cases = [{'case_id': 'one'}, {'case_id': 'two'}]
    valid = {'plans': [{'case_id': c['case_id'], 'law_names': [], 'queries': ['승인 규정']} for c in cases]}
    invalid = {'plans': [valid['plans'][0], valid['plans'][0]]}
    session = contract.bounded(work, [invalid, valid], max_schema_repairs=1)
    assert session.structured('모의 지침', {'cases': cases, 'law_names': []},
        planning.schema(['one', 'two'], []), 'source-query-plan', 10) == valid
    assert len(session.gateway.transport.calls) == 2
    assert 'cover each input case' in session.gateway.transport.calls[-1]['messages'][2]['content']


def test_merge_conflict_and_new_file_collision_refuse_without_printing_source():
    with pytest.raises(ValueError, match='overlapping edits'):
        CORE.merge(b'private = 2\n', b'private = 1\n', b'private = 3\n', 'fixture.py')
    with pytest.raises(ValueError, match='incompatible existing/new'):
        CORE.merge(b'private = 2\n', None, b'private = 3\n', 'fixture.py')


@pytest.mark.parametrize('variant', ['photo', 'integrated', 'repair-r1'])
def test_final_r2_txt_apply_rerun_gate_rollback(checkout, tmp_path, variant):
    final = ROOT / '09_ARTIFACTS/HANDOFFS/20260929-model-decision-repair-compatible-r2'
    if variant != 'photo':
        release = ('legal-agent-structure-catalogue-pecab-20260929-r1' if variant == 'integrated'
                   else 'legal-agent-structure-catalogue-pecab-repair-20260929-r1')
        for name in PHOTO:
            (checkout / name).write_bytes((ROOT / '08_DEPLOYMENT/RELEASES' / release / 'code' / name).read_bytes())
        repin(checkout)
    before = snapshot(checkout)
    txt = final / 'GENOS_MODEL_DECISION_REPAIR_20260929_R2_APPLY.txt'
    def execute(python, mode, **extra):
        result = subprocess.run(['bash', str(txt)], env={**os.environ, 'DEPLOY_ROOT': str(checkout),
             'PYTHON_BIN': python, 'MODE': mode, **extra}, text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout
    assert 'CHECK_PASS' in execute(sys.executable, 'check')
    assert snapshot(checkout) == before
    assert 'APPLIED' in execute(sys.executable, 'apply')
    after = snapshot(checkout)
    if variant != 'photo':
        transform = CORE.load_module(ROOT / '06_TOOLS/OFFLINE/genos_decision_transform.py', '_final_r2_transform')
        name = '02_BACKEND/semantic_runtime/progress.py'
        qualified = 'ProgressCapture._poll_journal'
        assert transform.snippet(after[name], transform.node_for(after[name], qualified))[2] == transform.snippet(
            before[name], transform.node_for(before[name], qualified))[2]
    for python in [sys.executable] + (['/usr/bin/python3.11'] if Path('/usr/bin/python3.11').exists() else []):
        assert 'ALREADY_APPLIED' in execute(python, 'apply')
        assert snapshot(checkout) == after
    state = checkout / 'TRANSFER' / CORE.BUNDLE_ID
    git(checkout, 'add', '-u')
    git(checkout, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'validated repair')
    gate = CORE.load_module(ROOT / '06_TOOLS/COMMANDS/genos_release_gate.py', '_final_r2_gate')
    assert gate.compare_zip_to_checkout(state / 'applied-code.zip', checkout)['code_files'] > 3
    backup = next(state.glob('backup-*'))
    assert 'ROLLED_BACK' in execute(sys.executable, 'rollback', ROLLBACK_FROM=str(backup))
    assert snapshot(checkout) == before
