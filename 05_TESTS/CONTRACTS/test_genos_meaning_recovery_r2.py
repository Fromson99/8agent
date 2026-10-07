"""Frozen plans across checkout aliases, scripted reference calls only."""
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import zipfile

import pytest

from semantic_runtime.contracts import sha
from lawrag.pipeline import term_generation, document_release as release
from test_genos_meaning_variants import prepared, reference_calls, tool as variants
from test_genos_meaning_recovery import fail_at_fulltext, context, recovery as r1, ORIGINAL, checkout

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / '06_TOOLS/OFFLINE/genos_meaning_recover_r2.py'
spec = importlib.util.spec_from_file_location('meaning_recovery_r2', PATH)
r2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r2)
PACKAGE = ROOT / '08_DEPLOYMENT/GENOS/handoffs/meaning_recovery_20261002_r2'
STEM = 'GENOS_MEANING_RECOVERY_20261002_R2'


def aliased_code_pins(tmp_path, monkeypatch):
    original = variants.code_pins()
    aliases = tmp_path / 'checkout-alias'; aliases.mkdir()
    current = {}
    for number, (name, expected) in enumerate(original.items()):
        if Path(name) == ORIGINAL:
            current[name] = expected
            continue
        alias = aliases / (str(number) + '-' + Path(name).name)
        alias.symlink_to(name)
        current[str(alias)] = expected
    monkeypatch.setattr(variants, 'code_pins', lambda: dict(current))
    return current


def test_photo_plan_failure_reproduces_then_original_r1_checkpoint_resumes(prepared, monkeypatch, reference_calls, tmp_path):
    ctx, output, stage, before = fail_at_fulltext(prepared, monkeypatch, reference_calls)
    plan = output / 'plan.json'; plan_bytes = plan.read_bytes()
    checkpoint = (output / 'baseline-recovery-r1.json').read_bytes()
    aliased_code_pins(tmp_path, monkeypatch)
    with r1.Recovery(term_generation).installed(release), pytest.raises(ValueError, match='Immutable receipt differs'):
        variants.build_variant(ctx, 'off')
    assert not reference_calls
    with r1.Recovery(term_generation).installed(release), r2.PlanGuard(variants).installed():
        result = variants.build_variant(ctx, 'off')
    assert result['completed'] and not result['activated'] and len(reference_calls) == 1
    assert plan.read_bytes() == plan_bytes
    assert (output / 'baseline-recovery-r1.json').read_bytes() == checkpoint
    assert all(sha(path) == pin for path, pin in before.items())
    event = json.loads((output / 'plan-alias-recovery-r2.jsonl').read_text())
    assert event['same_inode_and_sha256'] and event['stored_pins'] == r1.read(plan)['pins']
    assert not stage.exists()
    with r1.Recovery(term_generation).installed(release), r2.PlanGuard(variants).installed():
        assert variants.build_variant(ctx, 'off') == result
    assert len(reference_calls) == 1
    assert len((output / 'plan-alias-recovery-r2.jsonl').read_text().splitlines()) == 2


def test_probe_checks_existing_native_plan_without_building_or_changing_pins(prepared, monkeypatch, reference_calls, tmp_path):
    ctx, output, stage, before = fail_at_fulltext(prepared, monkeypatch, reference_calls)
    aliased_code_pins(tmp_path, monkeypatch)
    pins_before = dict(ctx['pins'])
    r2.check_plans(variants, ctx)
    assert ctx['pins'] == pins_before and not reference_calls and stage.exists()
    assert not (output / 'plan-alias-recovery-r2.jsonl').exists()
    assert all(sha(path) == pin for path, pin in before.items())


def test_stored_code_symlink_alias_preserves_plan_and_final_native_verification(prepared, monkeypatch, reference_calls, tmp_path):
    ctx, output, stage, before = fail_at_fulltext(prepared, monkeypatch, reference_calls)
    code = variants.code_pins()
    aliases = tmp_path / 'stored-checkout-alias'; aliases.mkdir()
    plan = output / 'plan.json'; old = r1.read(plan)
    for number, name in enumerate(code):
        if Path(name) == ORIGINAL:
            continue
        alias = aliases / (str(number) + '-' + Path(name).name); alias.symlink_to(name)
        old['pins'][str(alias)] = old['pins'].pop(name)
    plan.write_text(json.dumps(old)); plan_bytes = plan.read_bytes()
    with r1.Recovery(term_generation).installed(release), r2.PlanGuard(variants).installed():
        result = variants.build_variant(ctx, 'off')
        assert variants.verify_variant(output) == result
    assert result['completed'] and len(reference_calls) == 1 and not stage.exists()
    assert plan.read_bytes() == plan_bytes
    assert all(sha(path) == pin for path, pin in before.items())


def test_data_symlinks_keep_native_rejection(tmp_path):
    source = tmp_path / 'data.sqlite'; source.write_bytes(b'synthetic data')
    alias = tmp_path / 'alias.sqlite'; alias.symlink_to(source)
    with r2.PlanGuard(variants).installed(), pytest.raises(ValueError, match='symlink path'):
        variants.verify_pins({str(alias): sha(source)})


@pytest.mark.parametrize('change', ['settings', 'different-copy', 'added-file', 'missing-file', 'changed-hash'])
def test_guard_rejects_real_changes_without_modifying_existing_plan(tmp_path, change):
    original = tmp_path / 'original.py'; original.write_text('synthetic original\n')
    alias = tmp_path / 'alias.py'; os.link(original, alias)
    plan = tmp_path / 'off/plan.json'; plan.parent.mkdir()
    old = {'schema_version': 'synthetic-plan', 'reference_batch_size': 8, 'pins': {str(original): sha(original)}}
    plan.write_text(json.dumps(old))
    candidate = {**old, 'pins': {str(alias): sha(alias)}}
    if change == 'settings':
        candidate['reference_batch_size'] = 4
    if change == 'different-copy':
        copy = tmp_path / 'copy.py'; shutil.copyfile(original, copy)
        candidate['pins'] = {str(copy): sha(copy)}
    if change == 'added-file':
        extra = tmp_path / 'extra.py'; extra.write_text('synthetic extra')
        candidate['pins'][str(extra)] = sha(extra)
    if change == 'missing-file':
        candidate['pins'] = {}
    if change == 'changed-hash':
        original.write_text('synthetic changed bytes')
        candidate['pins'] = {str(alias): sha(alias)}
    before = plan.read_bytes()
    with pytest.raises(ValueError):
        r2.PlanGuard(variants).immutable(plan, candidate)
    assert plan.read_bytes() == before
    assert not (plan.parent / 'plan-alias-recovery-r2.jsonl').exists()


def test_alias_receipt_is_append_only_and_native_pin_dictionary_is_retained(tmp_path):
    original = tmp_path / 'original.py'; original.write_text('synthetic code')
    alias = tmp_path / 'alias.py'; os.link(original, alias)
    plan = tmp_path / 'off/plan.json'; plan.parent.mkdir()
    old = {'pins': {str(original): sha(original)}}
    plan.write_text(json.dumps(old)); before = plan.read_bytes()
    guard = r2.PlanGuard(variants)
    for _ in range(2):
        pins = {str(alias): sha(alias)}
        value = {'pins': pins}
        guard.immutable(plan, value)
        assert value['pins'] is pins and pins == old['pins']
    assert plan.read_bytes() == before
    rows = (plan.parent / 'plan-alias-recovery-r2.jsonl').read_text().splitlines()
    assert len(rows) == 2 and all(json.loads(row)['same_inode_and_sha256'] for row in rows)


def test_new_handoff_has_exact_base_and_preserves_mailed_r1_inventory():
    with zipfile.ZipFile(PACKAGE / (STEM + '.zip')) as z:
        manifest = json.loads(z.read('CODE_MANIFEST.json'))
        assert set(z.namelist()) == {row['path'] for row in manifest['files']} | {'CODE_MANIFEST.json'}
        import hashlib
        for row in manifest['files']:
            assert hashlib.sha256(z.read(row['path'])).hexdigest() == row['sha256']
            assert Path(row['path']).suffix not in ('.js', '.jsx', '.mjs', '.cjs')
        assert z.read('06_TOOLS/OFFLINE/genos_meaning_recover_r1.py') == (ROOT / '06_TOOLS/OFFLINE/genos_meaning_recover_r1.py').read_bytes()
        assert z.read('06_TOOLS/OFFLINE/genos_meaning_recover_r2.py') == PATH.read_bytes()
        assert z.read('original/GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt') == ORIGINAL.read_bytes()
    historical = ROOT / '08_DEPLOYMENT/GENOS/handoffs/meaning_recovery_20261002_r1'
    handoff = json.loads((historical / 'HANDOFF.json').read_text())
    assert all(sha(historical / name) == expected for name, expected in handoff['files'].items())
    assert sha(ROOT / '06_TOOLS/OFFLINE/genos_meaning_recover_r1.py') == handoff['runner_sha256']
    text = (PACKAGE / (STEM + '.txt')).read_text()
    assert '.venv/bin/python' not in text and 'log-off' in text and 'log-on' in text and 'log-review' in text
    subprocess.run(['bash', '-n', str(PACKAGE / (STEM + '.txt'))], check=True)


def r2_checkout(tmp_path):
    root, _, python, env = checkout(tmp_path)
    for suffix in ('.zip', '.txt'):
        shutil.copyfile(PACKAGE / (STEM + suffix), root / 'TRANSFER' / (STEM + suffix))
    return root, root / 'TRANSFER' / (STEM + '.txt'), python, env


def test_mailed_preflight_checks_old_plan_under_actual_alternate_import_path(prepared, monkeypatch, reference_calls, tmp_path):
    ctx, output, stage, before = fail_at_fulltext(prepared, monkeypatch, reference_calls)
    root, txt, _, env = r2_checkout(tmp_path)
    env.update(GENOS_DATA_ROOT=str(prepared['parent'].parents[1]), GENOS_VARIANTS_RUN_ID='prepared',
               GENOS_VARIANTS_ORIGINAL=str(ORIGINAL))
    plan_before = (output / 'plan.json').read_bytes()
    for _ in range(2):
        outcome = subprocess.run(['bash', str(txt), 'check'], cwd=root, env=env,
                                 capture_output=True, text=True, timeout=90)
        assert outcome.returncode == 0, outcome.stdout + outcome.stderr
        assert 'PLAN ALIASES verified same inode + SHA-256' in outcome.stdout
        assert 'CHECK existing off frozen plan PASS' in outcome.stdout
    assert not reference_calls and stage.exists()
    assert (output / 'plan.json').read_bytes() == plan_before
    assert all(sha(path) == pin for path, pin in before.items())
    assert not (output / 'plan-alias-recovery-r2.jsonl').exists()
    for name in ('genos_meaning_recover_r1.py', 'genos_meaning_recover_r2.py'):
        assert (root / '06_TOOLS/OFFLINE' / name).read_bytes() == (ROOT / '06_TOOLS/OFFLINE' / name).read_bytes()


def test_mailed_preflight_stops_changed_plan_before_background_worker_starts(prepared, monkeypatch, reference_calls, tmp_path):
    ctx, output, stage, before = fail_at_fulltext(prepared, monkeypatch, reference_calls)
    plan = output / 'plan.json'; value = r1.read(plan); value['reference_batch_size'] = 1
    plan.write_text(json.dumps(value)); plan_bytes = plan.read_bytes()
    root, txt, _, env = r2_checkout(tmp_path)
    data = prepared['parent'].parents[1]
    env.update(GENOS_DATA_ROOT=str(data), GENOS_VARIANTS_RUN_ID='prepared', GENOS_VARIANTS_ORIGINAL=str(ORIGINAL))
    outcome = subprocess.run(['bash', str(txt)], cwd=root, env=env, capture_output=True, text=True, timeout=90)
    assert outcome.returncode == 1, outcome.stdout + outcome.stderr
    assert 'Frozen variant settings differ' in outcome.stdout
    assert 'BACKGROUND STARTED' not in outcome.stdout
    assert not (data / 'LOGS/prepared/meaning-recovery-r1/off-worker.json').exists()
    assert not reference_calls and stage.exists() and plan.read_bytes() == plan_bytes


def test_mailed_log_off_opens_recorded_log_without_installer_or_worker_signals(tmp_path):
    root, txt, _, env = r2_checkout(tmp_path)
    (root / 'TRANSFER' / (STEM + '.zip')).unlink()  # Log viewing must not require/apply a ZIP.
    data = tmp_path / 'log-data'; logs = data / 'LOGS/log-test/meaning-recovery-r1'; logs.mkdir(parents=True)
    log = logs / 'baseline-worker-old.log'; log.write_text('SYNTHETIC LAST WORKER ERROR\n')
    worker = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], start_new_session=True)
    (logs / 'off-worker.json').write_text(json.dumps({'pid': worker.pid, 'log': str(log)}))
    env.update(GENOS_DATA_ROOT=str(data), GENOS_VARIANTS_RUN_ID='log-test')
    viewer = subprocess.Popen(['bash', str(txt), 'log-off'], cwd=root, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        try:
            output, _ = viewer.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            os.killpg(viewer.pid, signal.SIGINT)
            output, _ = viewer.communicate(timeout=5)
        assert 'SYNTHETIC LAST WORKER ERROR' in output and 'WORKER LOG' in output
        assert worker.poll() is None
        assert not (root / '06_TOOLS/OFFLINE/genos_meaning_recover_r2.py').exists()
    finally:
        if viewer.poll() is None:
            os.killpg(viewer.pid, signal.SIGTERM); viewer.wait(timeout=5)
        worker.terminate(); worker.wait(timeout=5)


def test_installer_preserves_unrecognized_existing_r1(tmp_path):
    root, txt, _, env = r2_checkout(tmp_path)
    target = root / '06_TOOLS/OFFLINE/genos_meaning_recover_r1.py'
    target.parent.mkdir(parents=True); target.write_text('# synthetic different R1 bytes\n')
    env.update(GENOS_DATA_ROOT=str(tmp_path / 'data'), GENOS_VARIANTS_RUN_ID='unknown-r1',
               GENOS_VARIANTS_ORIGINAL=str(ORIGINAL))
    outcome = subprocess.run(['bash', str(txt), 'check'], cwd=root, env=env, capture_output=True, text=True, timeout=10)
    assert outcome.returncode == 1 and 'Existing R1 runner differs' in outcome.stdout
    assert target.read_text() == '# synthetic different R1 bytes\n'
    assert not target.with_name('genos_meaning_recover_r2.py').exists()
