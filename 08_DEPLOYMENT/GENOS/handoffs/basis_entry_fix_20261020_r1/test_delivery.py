"""Exact mailed archive installation and real service bootstrap, synthetic data."""
from pathlib import Path
from contextlib import closing
import gzip
import hashlib
import json
import os
import subprocess
import zipfile

from test_risk_team_compare_workflow import generation

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAME = 'GENOS_BASIS_ENTRY_FIX_20261020_R1'


def test_exact_delivery(tmp_path, generation):
    from lawrag.pipeline.fulltext_stage import derive
    from lawrag.pipeline.search_selection import plan, activate
    from semantic_runtime.basis_links.api import local_factory
    from test_authority import WHO, BODY, review_body
    selected = tmp_path / 'generation'
    derive(generation, selected, workers=1)
    activate(plan(selected, latest=True))
    transfer = tmp_path / 'transfer'; transfer.mkdir()
    checkout = tmp_path / 'checkout'; checkout.mkdir()
    task_home = tmp_path / 'task-home'; task_home.mkdir()
    (task_home / 'DEV').symlink_to(checkout, target_is_directory=True)
    with zipfile.ZipFile(HERE.with_name('main92_cumulative_20261020_r1') / 'code.zip') as z:
        z.extractall(checkout)
    runtime = tmp_path / 'runtime'
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    config = checkout / '00_SYSTEM/GENOS_SERVING_PATHS.json'
    config.write_text(json.dumps({
        'schema_version': 'genos-serving-paths-v1', 'selection': 'operator-fixed',
        'generation': str(selected), 'runtime': str(runtime),
        'generation_manifest_sha256': sha(selected / 'manifest.json')}))
    marker = runtime / 'basis-links/SQLITE_ENABLED.json'
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({'schema_version': 'basis-shared-sqlite-v1',
                                 'database': 'authority.sqlite'}))
    with local_factory(runtime, selected)() as service:
        row = service.propose(WHO, BODY)
        service.review(WHO, review_body(row))
        history_before = service.repo.history(row['link']['link_id'])
    old_job = runtime / 'basis-batch/pilot-review-skip-20261020-r4'
    old_job.mkdir(parents=True)
    for name, value in [('PLAN.json', {'batch_id': 'previous'}),
                        ('STATE.json', {'status': 'interrupted', 'used': 7}),
                        ('CANDIDATES.json', {'items': ['preserve']})]:
        (old_job / name).write_text(json.dumps(value))
    protected = [config, marker, *old_job.iterdir(), marker.with_name('authority.sqlite')]
    before = {p: sha(p) for p in protected}
    data_before = {p: sha(p) for p in selected.rglob('*') if p.is_file()}
    env = {k: v for k, v in os.environ.items() if not k.startswith((
        'GENOS_', 'SEMANTIC_', 'LEGAL_AGENT_', 'PYTHON', 'LAWRAG_',
        'SOURCE_PROVIDER_', 'WORKFLOW_', 'TASK_TEST_'))}
    env.update(HOME=str(task_home), PATH=str(ROOT / '.venv/bin') + os.pathsep + os.environ['PATH'],
               PYTHONDONTWRITEBYTECODE='1', DP='sqlite', GENOS_AUTO_WARMUP='0',
               AD_WORKER_ENABLED='0', SEMANTIC_LLM_BACKEND='genos',
               GENOS_RAG_IMPLEMENTATION='legal-agent-unified-v6',
               GENOS_SYSTEM_LOG_DIR=str(tmp_path / 'system-logs'))
    trace = []

    def command(args, expected=0):
        result = subprocess.run([str(a) for a in args], cwd=transfer, env=env,
                                capture_output=True, text=True, timeout=60)
        output = result.stdout + result.stderr
        trace.append({'args': [str(a) for a in args], 'exit': result.returncode,
                      'expected': expected, 'output': output})
        with gzip.open(HERE / 'DELIVERY_TRACE.json.gz', 'wt') as stream:
            json.dump(trace, stream, ensure_ascii=False)
        assert (result.returncode == 0) == (expected == 0), output[-16000:]
        return output

    command(['git', 'init', '-q', checkout])
    for rev in ('r3', 'r4'):
        name = 'GENOS_BASIS_BATCH_20261020_' + rev.upper()
        folder = transfer / name
        command(['python3', '-m', 'zipfile', '-e',
                 HERE.with_name('basis_batch_20261020_' + rev) / (name + '.zip'), folder])
        command(['bash', folder / (name + '_RUN.txt'), 'apply'])
    r4 = json.loads((HERE.with_name('basis_batch_20261020_r4') / 'PACKAGE.json').read_text())
    assert {n: sha(checkout / n) for n in r4['code']} == r4['code']
    package = transfer / NAME
    command(['python3', '-m', 'zipfile', '-e', HERE / (NAME + '.zip'), package])
    script = package / (NAME + '_RUN.txt')
    for action in ('check', 'apply', 'gate', 'apply'):
        command(['bash', script, action])
    spec = json.loads((package / 'PACKAGE.json').read_text())
    assert {n: sha(checkout / n) for n in spec['code']} == spec['code']
    assert {p: sha(p) for p in protected} == before
    command(['git', '-C', checkout, 'add', '--', *spec['code']])
    command(['git', '-C', checkout, '-c', 'user.name=Fixture',
             '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'verified fixture'])
    gate = command(['bash', script, 'release-gate'])
    assert 'GENOS_RELEASE_GATE PASS' in gate
    assert '"serving_revision": "NOT_VERIFIED"' in gate

    # No _APP injection: bootstrap the actual installed service entry.
    # Only temporary mount classification is simulated; no model is invoked.
    smoke = transfer / 'service_smoke.py'
    smoke.write_text(
        "import sys,asyncio,json\n"
        f"sys.path[:0]=[{str(checkout)!r},{str(checkout/'02_BACKEND')!r}]\n"
        "from semantic_runtime import state_sqlite\n"
        "state_sqlite.network_storage=lambda p: True\n"
        "import service\n"
        "assert service._APP is None\n"
        "r=asyncio.run(service.service({},dict(API_TYPE='LEGAL_AGENT',"
        "question='대사: 모의내규의 영업일 승인 기준',team_id='risk_team',"
        "session_id='installed-entry',request_id='installed-entry-1',use_llm=False)))\n"
        "print('INSTALLED_SERVICE_RESULT',json.dumps(r,ensure_ascii=False))\n"
        "assert r['status']==200,r\n"
        "assert r['body'].get('error_code')!='BASIS_IDENTITY',r\n"
        "assert service._APP is not None\n"
        "assert service._APP.state.pipeline.basis_factory is not None\n")
    command(['python3', smoke])
    with local_factory(runtime, selected)() as service:
        assert service.repo.history(row['link']['link_id']) == history_before
    # The independent batch subprocess also needs the same synthetic mount
    # classification. Keep this test helper outside the installed checkout.
    fixture_modules = transfer / 'fixture-modules'; fixture_modules.mkdir()
    (fixture_modules / 'sitecustomize.py').write_text(
        "import sys\n"
        f"sys.path.insert(0,{str(checkout/'02_BACKEND')!r})\n"
        "from semantic_runtime import state_sqlite\n"
        "state_sqlite.network_storage=lambda p: True\n")
    env['PYTHONPATH'] = str(fixture_modules)
    command(['bash', script, 'plan', '--count', '3'])
    job = runtime / 'basis-batch/pilot-review-entryfix-20261020-r1'
    new_plan = (job / 'PLAN.json').read_bytes()
    assert json.loads(new_plan)['candidate_storage']['publication'] == 'manual-review-only'
    command(['bash', script, 'report', '--output', './후보검토.html'])
    assert '<html' in (transfer / '후보검토.html').read_text()
    env.pop('PYTHONPATH')
    path = checkout / '02_BACKEND/semantic_runtime/app.py'
    raw = path.read_bytes()
    path.write_bytes(raw + b'\n# unknown fixture edit\n')
    assert 'Unknown code' in command(['bash', script, 'gate'], expected=1)
    path.write_bytes(raw)
    tool = package / 'tools/basis_batch_candidates.py'
    original = tool.read_bytes(); tool.write_bytes(original + b'\n# altered\n')
    assert 'Package file changed' in command(['bash', script, 'report'], expected=1)
    tool.write_bytes(original)
    # Service reads can persist review views and change SQLite journaling.
    # Installer/rollback must preserve its current bytes; approved data/history
    # must remain identical across the entire run.
    db_path = marker.with_name('authority.sqlite')
    db_before_rollback = sha(db_path)
    command(['bash', script, 'rollback'])
    assert {n: sha(checkout / n) for n in r4['code']} == r4['code']
    assert sha(db_path) == db_before_rollback
    assert {p: sha(p) for p in protected if p != db_path} == {
        p: value for p, value in before.items() if p != db_path}
    with local_factory(runtime, selected)() as service:
        assert service.repo.history(row['link']['link_id']) == history_before
    assert {p: sha(p) for p in data_before} == data_before
    assert (job / 'PLAN.json').read_bytes() == new_plan
    exits = list((transfer / 'basis-entry-fix-r1-logs').glob('*.log.exit'))
    assert len(exits) == sum(r['args'][:2] == ['bash', str(script)] for r in trace)
    record = {'status': 'PASS', 'zip_sha256': sha(HERE / (NAME + '.zip')),
              'commands': len(trace), 'code_files': len(spec['code']),
              'real_installed_service_without_app_injection': True,
              'synthetic_data_and_mount_classification': True, 'model_calls': 0,
              'idempotent_install_and_exact_rollback': True,
              'approved_sqlite_and_old_candidates_preserved': True,
              'source_and_config_preserved': True, 'release_gate_pass': True,
              'new_manual_review_plan_and_html': True,
              'code_and_package_tamper_rejected': True, 'GENOS_field_verified': False}
    (HERE / 'FINAL_VERIFICATION.json').write_text(json.dumps(record, indent=2) + '\n')
