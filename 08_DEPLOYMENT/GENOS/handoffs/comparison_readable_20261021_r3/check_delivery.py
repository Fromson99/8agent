"""Exercise the exact ZIP/TXT on disposable existing checkouts, without models."""
import ast
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAME = 'GENOS_COMPARISON_READABLE_20261021_R3'
BASE = HERE.with_name('main96_ad_disabled_20261021_r1')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text())
trace = []
env = {k: v for k, v in os.environ.items() if not k.startswith(
    ('GENOS_', 'SEMANTIC_', 'LEGAL_AGENT_', 'PYTHON', 'LAWRAG_', 'SOURCE_PROVIDER_', 'WORKFLOW_', 'TASK_TEST_'))}
env.update(PATH=str(ROOT / '.venv/bin') + ':' + env['PATH'], PYTHONDONTWRITEBYTECODE='1',
           GENOS_AUTO_WARMUP='0', AD_WORKER_ENABLED='0', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
spec = read(HERE / 'PACKAGE.json')


def record():
    with gzip.open(HERE / 'DELIVERY_TRACE.json.gz', 'wt') as stream:
        json.dump(trace, stream, ensure_ascii=False)


def call(args, cwd, ok=True, timeout=90):
    result = subprocess.run(list(map(str, args)), cwd=cwd, env={**env, "WORKFLOW_TEST_CODE_ROOT":str(cwd)}, text=True,
                            capture_output=True, timeout=timeout)
    trace.append({'command': list(map(str, args)), 'cwd': str(cwd), 'exit_code': result.returncode,
                  'output': result.stdout + result.stderr})
    record()
    assert (result.returncode == 0) == ok, trace[-1]
    return result.stdout


def run(transfer, package, code, action, ok=True):
    return call(['bash', package / (NAME + '_RUN.txt'), action, '--root', code], transfer, ok)


def copy_test_closure(code):
    todo = ['test_comparison_toggle_compat', 'test_bounded_delivered_handoff', 'test_investigation_diagnostics', 'test_judgment_loop_recovery', 'test_navigation_delivery_recovery', 'test_comparison_readable_report', 'test_workflow_failed_originals', 'test_comparison_ten_minute', 'test_comparison_partial_items',
            'test_document_release', 'test_source_span_norm', 'test_bounded_source_main', 'test_legal_agent_double_harness']
    seen = set()
    for name in ['pytest.ini', '05_TESTS/conftest.py']:
        target = code / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    for name in ['adr_0936/test_generalized.py', 'adr_0844/test_sources.py',
                 'adr_0838/test_workflow.py', 'adr_0811/test_handoff_orchestration.py']:
        target = code / '06_TOOLS/EXPERIMENTS' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / '06_TOOLS/EXPERIMENTS' / name, target)
        for node in ast.walk(ast.parse(target.read_text())):
            imports = [node.module] if isinstance(node, ast.ImportFrom) else (
                [item.name for item in node.names] if isinstance(node, ast.Import) else [])
            todo.extend(n for n in imports if n and n.startswith('test_'))
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        source = ROOT / '05_TESTS/CONTRACTS' / (name + '.py')
        if not source.exists():
            source = ROOT / '05_TESTS/REGRESSION' / (name + '.py')
        assert source.exists(), name
        target = code / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        for node in ast.walk(ast.parse(source.read_text())):
            imports = [node.module] if isinstance(node, ast.ImportFrom) else (
                [item.name for item in node.names] if isinstance(node, ast.Import) else [])
            todo.extend(n for n in imports if n and n.startswith('test_'))
    return len(seen)


def fixture(base, overlays):
    code = base / 'DEV'
    transfer = base / 'custom-upload-TRANSFER'
    transfer.mkdir(parents=True)
    with zipfile.ZipFile(HERE.with_name('main95_comparison_scope_20261020_r1') / 'code.zip') as archive:
        archive.extractall(code)
    for name in read(BASE / 'PACKAGE.json')['patch']:
        target = code / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BASE / 'payload' / name, target)
    assert all(sha(code / n) == h for n, h in read(BASE / 'PACKAGE.json')['code'].items())
    keep = {'.gitignore': b'.Trash*/\nTRANSFER/\nuser-private/\n',
            'genosIgnore': b'.Trash*/\n*.sqlite\nuser-rule\n', '.env': b'TEAM_ID=\nAD_WORKER_ENABLED=0\n',
            '00_SYSTEM/GENOS_SERVING_PATHS.json': b'{"runtime":"/field/runtime","generation":"/field/generation"}\n'}
    for name, raw in keep.items():
        (code / name).write_bytes(raw)
    call(['git', 'init', '-q'], code)
    call(['git', 'config', 'user.name', 'Synthetic patch verification'], code)
    call(['git', 'config', 'user.email', 'synthetic@example.invalid'], code)
    if overlays:
        for folder, archive_name, script in [
            ('stable_commands_20261021_r1', 'GENOS_STABLE_COMMANDS_20261021_R1.zip', 'GENOS_STABLE_COMMANDS_RUN.txt'),
            ('basis_fixed_local_20261021_r1', 'GENOS_BASIS_FIXED_LOCAL_20261021_R1.zip', 'GENOS_BASIS_FIXED_LOCAL_RUN.txt')]:
            unpack = transfer / folder
            with zipfile.ZipFile(HERE.with_name(folder) / archive_name) as archive:
                archive.extractall(unpack)
            call(['bash', unpack / script, 'apply', '--root', code], transfer)
            for name in read(unpack / 'PACKAGE.json')['payload']:
                keep[name] = (code / name).read_bytes()
        keep['06_TOOLS/pipeline.py'] = (code / '06_TOOLS/pipeline.py').read_bytes()
    if overlays:
        previous = transfer / 'previous-ten-minute'
        with zipfile.ZipFile(HERE.with_name('comparison_ten_minute_20261021_r1') / 'GENOS_COMPARISON_TEN_MINUTE_20261021_R1.zip') as archive:
            archive.extractall(previous)
        call(['bash', previous / 'GENOS_COMPARISON_TEN_MINUTE_20261021_R1_RUN.txt', 'apply', '--root', code], transfer)
    if overlays in {'readable-r2', 'navigation-r1'}:
        previous = transfer / 'previous-readable-r1'
        with zipfile.ZipFile(HERE.with_name('comparison_readable_20261021_r2') / 'GENOS_COMPARISON_READABLE_20261021_R2.zip') as archive:
            archive.extractall(previous)
        call(['bash', previous / 'GENOS_COMPARISON_READABLE_20261021_R2_RUN.txt', 'apply', '--root', code], transfer)
    if overlays == 'navigation-r1':
        previous = transfer/'previous-navigation-r1'
        with zipfile.ZipFile(HERE.with_name('navigation_delivery_20261021_r1')/'GENOS_NAVIGATION_DELIVERY_20261021_R1.zip') as archive:
            archive.extractall(previous)
        call(['bash', previous/'GENOS_NAVIGATION_DELIVERY_20261021_R1_RUN.txt','apply','--root',code], transfer)
    call(['git', 'add', '.'], code)
    call(['git', 'commit', '-qm', 'Synthetic MAIN96 baseline'], code)
    private = code / '.Trash-1001/sample.csv'
    private.parent.mkdir()
    private.write_bytes(b'private fixture\r\n')
    keep['.Trash-1001/sample.csv'] = private.read_bytes()
    package = transfer / NAME
    call([sys.executable, '-m', 'zipfile', '-e', HERE / (NAME + '.zip'), package], transfer)
    assert (package / (NAME + '_RUN.txt')).read_bytes() == (HERE / (NAME + '_RUN.txt')).read_bytes()
    editor = package / 'GENOS_COMPARISON_READABLE_WORKFLOW_ALL.txt'
    assert editor.read_bytes() == (ROOT / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py').read_bytes()
    ast.parse(editor.read_bytes(), feature_version=(3, 10))
    before = {n: (code / n).read_bytes() if (code / n).exists() else None for n in spec['patch']}
    return code, transfer, package, keep, before


def unchanged(code, keep):
    assert all((code / n).read_bytes() == raw for n, raw in keep.items())


with tempfile.TemporaryDirectory(prefix='delivery-', dir=HERE) as temporary:
    base = Path(temporary)
    code, transfer, package, keep, before = fixture(base / 'normal', False)
    fixture_count = copy_test_closure(code)
    run(transfer, package, code, 'check')
    run(transfer, package, code, 'gate', False)
    for action in ['apply', 'apply', 'status', 'gate']:
        run(transfer, package, code, action)
    assert all(sha(code / n) == h for n, h in spec['code'].items())
    unchanged(code, keep)
    run(transfer, package, code, 'gate-code', False)
    call(['git', 'add', '--', *spec['patch']], code)
    call(['git', 'commit', '-qm', 'Synthetic disclosure display correction'], code)
    run(transfer, package, code, 'gate-code')
    run(transfer, package, code, 'gate-sqlite', False)  # No field generation exists locally.
    fixture_count = copy_test_closure(code)
    # All product imports, manifests and service.py come from this installed checkout.
    # The placeholder used solely to prove installer preservation is not a real
    # field selection. The API fixtures provide their own two-document generation.
    config = code / '00_SYSTEM/GENOS_SERVING_PATHS.json'
    held = base / 'preserved-field-placeholder.json'
    config.rename(held)
    try:
        test_output = call([ROOT / '.venv/bin/python', '-m', 'pytest', '-q', '-o', 'cache_dir=' + str(base / 'pytest-cache'),
              '05_TESTS/CONTRACTS/test_bounded_delivered_handoff.py',
              '05_TESTS/CONTRACTS/test_navigation_delivery_recovery.py::test_receipt_cannot_cross_identity_or_bytes',
              '05_TESTS/CONTRACTS/test_navigation_delivery_recovery.py::test_accepted_rejection_never_becomes_fallback',
              '05_TESTS/CONTRACTS/test_judgment_loop_recovery.py::test_bounded_stop_without_adoption_uses_delivered_pages',
              '05_TESTS/CONTRACTS/test_investigation_diagnostics.py',
              '05_TESTS/CONTRACTS/test_comparison_readable_report.py',
              '05_TESTS/CONTRACTS/test_comparison_toggle_compat.py',
              '05_TESTS/CONTRACTS/test_comparison_ten_minute.py'], code, timeout=180)
        installed_test_count = int(re.search(r'(\d+) passed', test_output).group(1))
    finally:
        held.rename(config)
    assert all(sha(code / n) == h for n, h in spec['code'].items())
    unchanged(code, keep)
    target = code / '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py'
    raw = target.read_bytes()
    target.write_bytes(raw + b'\n# later edit\n')
    run(transfer, package, code, 'check', False)
    run(transfer, package, code, 'rollback', False)
    target.write_bytes(raw)
    payload = package / 'payload/02_BACKEND/semantic_runtime/legal_agent/law_navigation.py'
    raw = payload.read_bytes()
    payload.write_bytes(raw + b'\n# changed package\n')
    run(transfer, package, code, 'apply', False)
    payload.write_bytes(raw)
    run(transfer, package, code, 'rollback')
    assert all(((code / n).read_bytes() if (code / n).exists() else None) == raw for n, raw in before.items())
    unchanged(code, keep)
    run(transfer, package, code, 'apply', False)

    code, transfer, package, keep, before = fixture(base / 'overlay-interrupted', True)
    run(transfer, package, code, 'check')
    module_spec = importlib.util.spec_from_file_location('delivered_installer', package / 'runner.py')
    installer = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(installer)
    original = installer.write
    writes = []

    def interrupted(path, value):
        if Path(path).is_relative_to(code):
            if len(writes) == 3:
                raise OSError('synthetic interruption after three code writes')
            writes.append(str(path))
        return original(path, value)

    installer.write = interrupted
    try:
        installer.apply(code, installer.load())
    except OSError as exc:
        assert 'synthetic interruption' in str(exc)
    else:
        raise AssertionError('Interruption did not occur')
    assert read(package / 'INSTALL_STATE.json')['status'] == 'prepared'
    for action in ['apply', 'apply', 'gate']:
        run(transfer, package, code, action)
    assert all(sha(code / n) == h for n, h in spec['code'].items())
    unchanged(code, keep)
    run(transfer, package, code, 'rollback')
    assert all(((code / n).read_bytes() if (code / n).exists() else None) == raw for n, raw in before.items())
    unchanged(code, keep)

    code, transfer, package, keep, before = fixture(base / 'navigation-r1-upgrade', 'navigation-r1')
    for action in ['check', 'apply', 'apply', 'gate']:
        run(transfer, package, code, action)
    assert all(sha(code / n) == h for n, h in spec['code'].items())
    unchanged(code, keep)
    run(transfer, package, code, 'rollback')
    assert all(((code / n).read_bytes() if (code / n).exists() else None) == raw for n, raw in before.items())
    unchanged(code, keep)

result = {'status': 'PASS', 'archive_sha256': sha(HERE / (NAME + '.zip')),
          'commands': len(trace), 'expected_rejections': sum(t['exit_code'] != 0 for t in trace),
          'code_files': len(spec['code']), 'patch_files': len(spec['patch']),
          'scenarios': ['MAIN96 normal', 'MAIN96 + STABLE_COMMANDS + BASIS_FIXED_LOCAL + TEN_MINUTE interrupted', 'MAIN96 + previous overlays + READABLE_R2 + NAVIGATION_R1 upgrade'],
          'installed_service_tests': installed_test_count, 'test_fixture_files': fixture_count, 'model_calls': 0, 'known_old_transport_test_failure': 1,
          'exact_rollback': True, 'existing_config_data_tools_preserved': True,
          'max_child_rss_kib': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
          'GENOS_field_verified': False, 'generation_success_verified': False,
          'selected_main_modified': False}
(HERE / 'DELIVERY_VALIDATION.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False))
