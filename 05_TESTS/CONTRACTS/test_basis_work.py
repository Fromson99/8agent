"""Stable commands use historical data and a current verified consumer."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest

import basis_work as work
from lawrag.pipeline import basis_batch_artifacts as art
from test_basis_batch_artifacts import pilot, generation
from test_basis_quick_all import campaign

ROOT = Path(__file__).resolve().parents[2]


def test_historical_campaign_read_after_patch_preserves_state_and_blocks_resume(campaign, tmp_path):
    c, runner = campaign
    c.initialize()
    assert c.run() == 0
    before = {str(p): p.read_bytes() for p in c.job.rglob('*.json')}
    c.binding = {'code': 'compatible-current-patch'}
    offset = len(runner.calls)
    assert c.status()['documents']['completed'] == 43
    c.render(tmp_path / 'report')
    assert all(action == 'report' for action, _, _ in runner.calls[offset:])
    with pytest.raises(ValueError, match='결속'):
        c.run()
    assert before == {str(p): p.read_bytes() for p in c.job.rglob('*.json')}


def test_portable_bundle_contains_data_and_keeps_review_requirement(pilot, tmp_path):
    value = art.capture(pilot['job'], pilot['generation'], pilot['runtime'])
    folder = tmp_path / 'portable'
    artifact = art.export_bundle(value, folder)
    with zipfile.ZipFile(artifact) as z:
        assert not any(n.endswith('.py') for n in z.namelist())
        assert 'portable/TRANSFER_CONTRACT.json' in z.namelist()
    with pytest.raises(Exception, match='검토'):
        art.load_reviewed(folder / 'RELATIONS.json', value)
    decision = art.review(value, folder / 'REVIEW.json', accept_all=True)
    approved = art.reviewed(value, decision)
    art.atomic(folder / 'REVIEWED.sql', art.sql(approved))
    archive = art.reviewed_archive(folder)
    with zipfile.ZipFile(archive) as z:
        assert 'portable/REVIEW.json' in z.namelist()
        assert not any(n.endswith('CODE_REQUIREMENTS.json') for n in z.namelist())
    assert approved['items'][0]['link']['status'] == 'PROPOSED'


@pytest.fixture
def installed(tmp_path, pilot):
    code = tmp_path / 'checkout'
    archive = ROOT / '08_DEPLOYMENT/GENOS/handoffs/main95_comparison_scope_20261020_r1/code.zip'
    with zipfile.ZipFile(archive) as z:
        z.extractall(code)
    for name in ['00_SYSTEM/BASIS_COMMANDS.json', *json.loads((ROOT / '00_SYSTEM/BASIS_COMMANDS.json').read_text())['files']]:
        target = code / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    pipeline = code / '06_TOOLS/pipeline.py'
    original = pipeline.read_text()
    anchor = 'root = Path(__file__).resolve().parents[1]\n'
    addition = "if __name__ == '__main__' and sys.argv[1:2] == ['basis-work']:\n    os.execv(sys.executable, [sys.executable, str(root / '06_TOOLS/COMMANDS/basis_work.py'), *sys.argv[2:]])\n"
    assert original.count(anchor) == 1 and "['basis-work']" not in original
    pipeline.write_text(original.replace(anchor, anchor + addition, 1))
    art.atomic(code / '00_SYSTEM/GENOS_SERVING_PATHS.json',
               {'generation': str(pilot['generation']), 'runtime': str(pilot['runtime'])})
    transfer = tmp_path / 'TRANSFER'
    transfer.mkdir()
    return code, transfer


def test_real_pipeline_export_review_operating_import_after_patch(pilot, installed, tmp_path):
    code, transfer = installed
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'AD_WORKER_ENABLED': '0', 'GENOS_AUTO_WARMUP': '0'}
    trace = []
    def call(*args, success=True):
        result = subprocess.run([str(ROOT / '.venv/bin/python'), '-B', str(code / '06_TOOLS/pipeline.py'),
                                 'basis-work', *map(str, args)], cwd=transfer, env=env,
                                text=True, capture_output=True, timeout=60)
        trace.append({'args': list(map(str, args)), 'exit': result.returncode, 'output': result.stdout + result.stderr})
        assert (result.returncode == 0) == success, trace[-1]
        return result
    before = {p.name: p.read_bytes() for p in pilot['job'].glob('*.json')}
    bundle = transfer / 'relations'
    call('check')
    call('export', '--job', pilot['job'], '--output', bundle)
    call('transfer', 'check', '--bundle', bundle / 'RELATIONS.json', '--local-validation', success=False)
    call('transfer', 'review', '--bundle', bundle / 'RELATIONS.json', '--all')
    assert before == {p.name: p.read_bytes() for p in pilot['job'].glob('*.json')}
    # A properly installed patch changes PIPELINE's code identity without changing
    # the supported relation/source contract. No old snapshot is rewritten.
    configpath = code / '00_SYSTEM/PIPELINE.json'
    configuration = json.loads(configpath.read_text())
    configuration['document_build']['risk_basis_append']['genos_field_validation'] = 'NOT_RUN_CURRENT_PATCH'
    art.atomic(configpath, configuration)
    runtime = tmp_path / 'operating-runtime'
    art.atomic(code / '00_SYSTEM/GENOS_SERVING_PATHS.json',
               {'generation': str(pilot['generation']), 'runtime': str(runtime)})
    operating = tmp_path / 'OPERATING_TRANSFER'
    operating.mkdir()
    with zipfile.ZipFile(transfer / 'relations_REVIEWED.zip') as z:
        z.extractall(operating)
    data = operating / 'relations/RELATIONS.json'
    call('transfer', 'check', '--bundle', data, '--local-validation')
    assert not runtime.exists()
    call('transfer', 'apply', '--bundle', data, '--local-validation')
    call('transfer', 'apply', '--bundle', data, '--local-validation')
    result = call('transfer', 'status', '--bundle', data)
    assert '"marker_enabled":true' in result.stdout
    call('transfer', 'rollback', '--bundle', data, '--local-validation')
    call('transfer', 'apply', '--bundle', data, '--local-validation', success=False)
    # Current runtime corruption still fails before reading or writing relations.
    resolver = code / '02_BACKEND/semantic_runtime/basis_links/resolver.py'
    resolver.write_text(resolver.read_text() + '\n# unregistered change\n')
    result = call('transfer', 'status', '--bundle', data, success=False)
    assert 'engine code hash mismatch' in result.stderr
    assert len(list((transfer / 'basis-work-logs').glob('*.log.exit'))) == len(trace)
    (tmp_path / 'TRACE.json').write_text(json.dumps(trace, ensure_ascii=False, indent=2))


def test_current_tool_tamper_blocks_before_mutation(installed):
    code, transfer = installed
    helper = code / '02_BACKEND/lawrag/pipeline/basis_batch_artifacts.py'
    helper.write_text(helper.read_text() + '\n# changed\n')
    result = subprocess.run([str(ROOT / '.venv/bin/python'), '-B', str(code / '06_TOOLS/pipeline.py'),
                             'basis-work', 'check'], cwd=transfer, text=True, capture_output=True, timeout=60)
    assert result.returncode == 1 and '명령 코드 해시 불일치' in result.stderr


def test_source_selection_receipts_replay_real_consumer_and_rollback(pilot, installed, tmp_path):
    import basis_source
    from semantic_runtime.deployment_paths import install, verify_generation
    code, transfer = installed
    old = pilot['generation']
    new = tmp_path / 'new-data/generation'
    new.parent.mkdir()
    shutil.copytree(old, new)
    shutil.copytree(old.parent / 'SEARCH_SELECTION', new.parent / 'SEARCH_SELECTION')
    config = code / '00_SYSTEM/GENOS_SERVING_PATHS.json'
    original = {'schema_version': 'genos-serving-paths-v1', 'selection': 'operator-fixed',
                'generation': str(old), 'runtime': str(pilot['runtime']), 'state': None,
                'generation_manifest_sha256': work.quick.sha(old / 'manifest.json')}
    art.atomic(config, original)
    plan, receipt, undo = (transfer / name for name in ('SOURCE_PLAN.json', 'SOURCE_APPLY.json', 'SOURCE_UNDO.json'))
    assert basis_source.main(['source-plan', '--generation', str(new), '--output', str(plan), '--local-validation'], code) == 0
    assert art.read_json(config) == original
    args = ['source-apply', '--plan', str(plan), '--output', str(receipt), '--local-validation']
    assert basis_source.main(args, code) == 0
    assert basis_source.main(args, code) == 0
    env = {}
    selected = install(code, environment=env)
    verify_generation(selected, new)
    assert env['GENOS_GENERATION'] == str(new) and env['GENOS_RUNTIME_DIR'] == str(pilot['runtime'])
    args = ['source-rollback', '--receipt', str(receipt), '--output', str(undo), '--local-validation']
    assert basis_source.main(args, code) == 0
    assert basis_source.main(args, code) == 0
    assert art.read_json(config) == original


def test_source_selection_refuses_stale_plan_without_replacing_settings(pilot, installed, tmp_path):
    import basis_source
    code, transfer = installed
    config = code / '00_SYSTEM/GENOS_SERVING_PATHS.json'
    original = {'schema_version': 'genos-serving-paths-v1', 'selection': 'operator-fixed',
                'generation': str(pilot['generation']), 'runtime': str(pilot['runtime']), 'state': None,
                'generation_manifest_sha256': work.quick.sha(pilot['generation'] / 'manifest.json')}
    art.atomic(config, original)
    plan = transfer / 'plan.json'
    basis_source.main(['source-plan', '--generation', str(pilot['generation']), '--output', str(plan), '--local-validation'], code)
    changed = {**original, 'source': 'a later operator change'}
    art.atomic(config, changed)
    with pytest.raises(ValueError, match='달라졌습니다'):
        basis_source.main(['source-apply', '--plan', str(plan), '--output', str(transfer / 'apply.json'), '--local-validation'], code)
    assert art.read_json(config) == changed and not (transfer / 'apply.json').exists()


def test_current_plan_all_uses_actual_service_and_reads_after_patch(pilot, installed, tmp_path):
    from lawrag.pipeline.fulltext_stage import derive
    from lawrag.pipeline.search_selection import plan, activate
    code, transfer = installed
    selected = tmp_path / 'fulltext-generation'
    derive(pilot['generation'], selected, workers=1)
    activate(plan(selected, latest=True))
    config = {'schema_version': 'genos-serving-paths-v1', 'selection': 'operator-fixed', 'state': None,
              'generation': str(selected), 'runtime': str(pilot['runtime']),
              'generation_manifest_sha256': work.quick.sha(selected / 'manifest.json')}
    art.atomic(code / '00_SYSTEM/GENOS_SERVING_PATHS.json', config)
    env = {k: v for k, v in os.environ.items() if not k.startswith(
        ('GENOS_', 'SEMANTIC_', 'LEGAL_AGENT_', 'PYTHON', 'LAWRAG_', 'SOURCE_PROVIDER_', 'WORKFLOW_', 'TASK_TEST_'))}
    env.update(PYTHONDONTWRITEBYTECODE='1', GENOS_AUTO_WARMUP='0', AD_WORKER_ENABLED='0')
    def call(*args, success=True):
        result = subprocess.run([str(ROOT / '.venv/bin/python'), '-B', str(code / '06_TOOLS/pipeline.py'),
                                 'basis-work', *args], cwd=transfer, env=env, capture_output=True, text=True, timeout=60)
        assert (result.returncode == 0) == success, result.stdout + result.stderr
        return result
    call('plan-all', 'smoke')
    job = pilot['runtime'] / 'basis-batch/pilot-review-user-smoke'
    original = {str(p): p.read_bytes() for p in job.rglob('*.json')}
    child = art.read_json(job / 'parts/part-00001/PLAN.json')
    assert [d['document_id'] for d in child['documents']] == ['inside']
    assert child['candidate_storage']['kind'] == 'json-candidates-v1'
    path = code / '00_SYSTEM/PIPELINE.json'
    pipeline = art.read_json(path)
    pipeline['document_build']['risk_basis_append']['genos_field_validation'] = 'PATCHED_AFTER_PLAN'
    art.atomic(path, pipeline)
    call('status', 'smoke')
    call('report', 'smoke')
    result = call('all', 'smoke', success=False)
    assert '결속이 달라졌습니다' in result.stderr
    assert original == {str(p): p.read_bytes() for p in job.rglob('*.json')}


def test_final_zip_existing_checkout_install_repeat_drift_and_rollback(tmp_path):
    code = tmp_path / 'DEV'
    base = ROOT / '08_DEPLOYMENT/GENOS/handoffs/main95_comparison_scope_20261020_r1/code.zip'
    with zipfile.ZipFile(base) as z:
        z.extractall(code)
    subprocess.run(['git', 'init', str(code)], check=True, capture_output=True)
    ignore = code / '.gitignore'
    ignore.write_text(ignore.read_text() + '\n# preserve latest ignore repair\nTRANSFER/\n')
    transfer = tmp_path / 'TRANSFER'
    kit = transfer / 'GENOS_STABLE_COMMANDS_20261021_R1'
    handoff = ROOT / '08_DEPLOYMENT/GENOS/handoffs/stable_commands_20261021_r1'
    with zipfile.ZipFile(handoff / (kit.name + '.zip')) as z:
        z.extractall(kit)
    package = art.read_json(kit / 'PACKAGE.json')
    names = [*package['payload'], '06_TOOLS/pipeline.py', '.gitignore', 'genosIgnore']
    before = {n: (code / n).read_bytes() if (code / n).exists() else None for n in names}
    env = {**os.environ, 'PATH': str(ROOT / '.venv/bin') + ':' + os.environ['PATH'], 'PYTHONDONTWRITEBYTECODE': '1'}
    trace = []
    def call(action, success=True):
        result = subprocess.run(['bash', str(kit / 'GENOS_STABLE_COMMANDS_RUN.txt'), action,
                                 '--root', str(code)], cwd=transfer, env=env, text=True, capture_output=True, timeout=60)
        trace.append({'action': action, 'exit': result.returncode, 'output': result.stdout + result.stderr})
        assert (result.returncode == 0) == success, trace[-1]
    call('check')
    assert before == {n: (code / n).read_bytes() if (code / n).exists() else None for n in names}
    call('apply')
    call('apply')
    call('status')
    result = subprocess.run([str(ROOT / '.venv/bin/python'), '-B', str(code / '06_TOOLS/pipeline.py'),
                             'basis-work', 'check'], cwd=transfer, env=env, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    helper = code / '06_TOOLS/COMMANDS/basis_work.py'
    saved = helper.read_bytes()
    helper.write_bytes(saved + b'\n# later change\n')
    call('status', success=False)
    call('rollback', success=False)
    helper.write_bytes(saved)
    call('rollback')
    call('rollback')
    assert before == {n: (code / n).read_bytes() if (code / n).exists() else None for n in names}
    art.atomic(tmp_path / 'INSTALL_TRACE.json', trace)
