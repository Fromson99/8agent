"""Exercise the final TXT on known field inventories and a committed checkout."""
import base64
import contextlib
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
NAME = 'GENOS_INVESTIGATION_BUDGET_20261007_R1'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
dump = lambda value: (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(root, payload):
    for name, raw in payload.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)


def main():
    installer = load('budget_installer_validation', OUT / 'install_budget.py')
    spec = json.loads((OUT / 'PATCH_SPEC.json').read_bytes())
    handoff = json.loads((OUT / 'HANDOFF.json').read_bytes())
    archive = OUT / (NAME + '.zip')
    assert sha(archive.read_bytes()) == handoff['zip_sha256']
    transcript = []
    results = []
    commands = 0
    bases = []
    legacy = OUT.parent / 'query_latency_20261007_r4/GENOS_QUERY_LATENCY_20261007_R4.zip'
    with zipfile.ZipFile(legacy) as zipped:
        bases.append(('latency-r4', {name: zipped.read(name) for name in zipped.namelist()}))
    cm_folder = OUT.parent / 'cm_shortcut_oneclick_20261007_r8'
    cm_test = json.loads(gzip.decompress((cm_folder / 'TEST_BASES.json.gz').read_bytes()))
    cm_spec = json.loads(gzip.decompress((cm_folder / 'PATCH_SPEC.json.gz').read_bytes()))
    cm = load('cm_recipe_validation', ROOT / '06_TOOLS/COMMANDS/genos_cm_oneclick.py')
    cm_lib = cm.library(cm_spec)
    basis = next(item for item in cm_test['bases'] if '/nfs-list-r1' in item['label'])
    cm_payload = {name: base64.b64decode(cm_test['blobs'][fingerprint]) for name, fingerprint in basis['files'].items()}
    with tempfile.TemporaryDirectory(prefix='budget-cm-recipe-') as directory:
        root = Path(directory)
        write(root, cm_payload)
        paths = {'schema_version': 'genos-serving-paths-v1', 'selection': 'operator-fixed',
                 'generation': '/fixed/generation', 'runtime': '/fixed/runtime', 'state': None,
                 'generation_manifest_sha256': '0' * 64}
        with contextlib.redirect_stdout(io.StringIO()):
            _, _, changes, _ = cm.prepare(root, cm_spec, cm_lib, paths)
        # The recipe's path config is deliberately preserved in the test. No field NFS writes.
        cm_payload.update(changes)
        bases.append(('cm-oneclick-r8-with-nfs-list', cm_payload))
    selected = json.loads((ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())
    release = json.loads((ROOT / selected['manifest_path']).read_bytes())
    release_root = ROOT / release['code_root']
    payload = {name: (release_root / name).read_bytes() for name in release['files']}
    payload['CODE_MANIFEST.json'] = dump({'format': '8agent-code/1', 'id': release['release_id'],
        'files': [{'path': name, 'sha256': sha(raw), 'bytes': len(raw)} for name, raw in sorted(payload.items())]})
    bases.append(('selected-main-45', payload))
    source_generation = ROOT / release['data_path']
    original_pointer = (ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()
    for label, payload in bases:
        with tempfile.TemporaryDirectory(prefix='budget-field-validation-') as directory:
            prefix = Path(directory)
            root = prefix / 'DEV'
            root.mkdir()
            write(root, payload)
            link = prefix / 'DEV-link'
            link.symlink_to(root, target_is_directory=True)
            unpacked = prefix / 'delivery'
            with zipfile.ZipFile(archive) as zipped:
                assert zipped.testzip() is None
                assert all(Path(name).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'} for name in zipped.namelist())
                assert set(zipped.namelist()) == set(handoff['zip_members'])
                zipped.extractall(unpacked)
            assert (unpacked / (NAME + '_RUN.txt')).read_bytes() == (OUT / (NAME + '_RUN.txt')).read_bytes()
            subprocess.run(['sha256sum', '-c', 'SHA256SUMS.txt'], cwd=unpacked, check=True, capture_output=True)
            subprocess.run(['bash', '-n', str(unpacked / (NAME + '_RUN.txt'))], check=True)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True)
            git('init', '-q')
            git('add', '-f', '--', *payload)
            git('-c', 'user.name=Offline fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'field fixture')
            env = {**os.environ, 'PATH': str(ROOT / '.venv/bin') + ':' + os.environ['PATH'],
                'GENOS_DEV_ROOT': str(link), 'GENOS_BUDGET_LOG_ROOT': str(prefix / 'logs'),
                'GENOS_GENERATION': str(source_generation), 'GENOS_RUNTIME_DIR': str(prefix / 'runtime'),
                'GENOS_SYSTEM_LOG_DIR': str(prefix / 'system-logs'), 'GENOS_LOG_SPOOL_DIR': str(prefix / 'spool'),
                'GENOS_AUTO_WARMUP': '0', 'AD_WORKER_ENABLED': '0'}
            for name in spec['settings']:
                env.pop(name, None)
            for name in ('GENOS_LLM_URL', 'GENOS_LLM_SERVING_ID', 'GENOS_LLM_KEY', 'GENOS_LLM_MODEL',
                         'LEGAL_AGENT_PROFILE', 'LEGAL_AGENT_PROFILE_SHA256', 'GENOS_DATA_ROOT', 'GENOS_RAG_IMPLEMENTATION'):
                env.pop(name, None)
            def run(*args, success=True):
                nonlocal commands
                commands += 1
                result = subprocess.run(['bash', str(unpacked / (NAME + '_RUN.txt')), *map(str, args)],
                    cwd=prefix, env=env, capture_output=True, text=True, timeout=120)
                transcript.append(label + ' ' + ' '.join(map(str, args)) + '\n' + result.stdout + result.stderr)
                assert (result.returncode == 0) == success, transcript[-1]
                log_dir = Path(re.search(r'^RUN_DIR=(.+)$', result.stdout, re.M)[1])
                assert json.loads((log_dir / 'EXIT_STATUS.json').read_bytes())['exit_code'] == result.returncode
                assert (log_dir / 'RUN.log').exists()
                return result
            run('check')
            result = run('apply')
            backup = Path(re.search(r'^BACKUP=(.+)$', result.stdout, re.M)[1])
            patched = {name: (root / name).read_bytes() for name in payload}
            assert {name for name in payload if payload[name] != patched[name]} == {'service.py', 'CODE_MANIFEST.json'}
            run('verify')
            assert 'ALREADY_APPLIED' in run('apply').stdout
            # Installed inventory and exact fragments detect unexpected field edits before writing.
            service_path = root / 'service.py'
            service_path.write_bytes(patched['service.py'] + b'\n# later unrelated change\n')
            run('check', success=False)
            run('undo', backup, success=False)
            assert service_path.read_bytes().endswith(b'# later unrelated change\n')
            assert (root / 'CODE_MANIFEST.json').read_bytes() == patched['CODE_MANIFEST.json']
            service_path.write_bytes(patched['service.py'])
            # Partial application can be rolled back using the PREPARED receipt.
            (root / 'CODE_MANIFEST.json').write_bytes(payload['CODE_MANIFEST.json'])
            run('undo', backup)
            assert all((root / name).read_bytes() == raw for name, raw in payload.items())
            result = run('apply')
            backup = Path(re.search(r'^BACKUP=(.+)$', result.stdout, re.M)[1])
            if label == 'latency-r4':
                run('gate', backup, '--generation', source_generation, success=False)
                git('add', '--', 'service.py', 'CODE_MANIFEST.json')
                git('-c', 'user.name=Offline fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'budget settings')
                gate_result = run('gate', backup, '--generation', source_generation)
                assert 'GENOS_RELEASE_GATE PASS' in gate_result.stdout
                receipt = json.loads((backup / 'gate-receipt.json').read_bytes())
                assert receipt['identity']['generation'] == str(source_generation)
                assert receipt['identity']['git_commit'] == git('rev-parse', 'HEAD').stdout.strip()
                remote = prefix / 'remote.git'
                subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True)
                git('remote', 'add', 'origin', str(remote))
                git('push', '-u', 'origin', 'HEAD')
                pushed = subprocess.run(['git', '--git-dir', str(remote), 'rev-parse', 'HEAD'],
                    check=True, capture_output=True, text=True).stdout.strip()
                assert pushed == receipt['identity']['git_commit']
            run('undo', backup)
            assert all((root / name).read_bytes() == raw for name, raw in payload.items())
            results.append({'basis': label, 'apply_repeat_verify_rollback': True,
                'only_service_and_inventory_changed': True, 'unexpected_changes_preserved': True,
                'same_committed_checkout_generation_gate': label == 'latency-r4',
                'mock_local_remote_push': label == 'latency-r4'})
            print('DELIVERY PASS', label, flush=True)
    assert (ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes() == original_pointer
    # Failure before locating DEV still has durable first-step logs/status.
    with tempfile.TemporaryDirectory(prefix='budget-early-failure-') as directory:
        env = {**os.environ, 'GENOS_DEV_ROOT': directory + '/missing', 'GENOS_BUDGET_LOG_ROOT': directory + '/logs',
               'PATH': str(ROOT / '.venv/bin') + ':' + os.environ['PATH']}
        result = subprocess.run(['bash', str(OUT / (NAME + '_RUN.txt')), 'check'], env=env, capture_output=True, text=True)
        assert result.returncode != 0
        log_dir = Path(re.search(r'^RUN_DIR=(.+)$', result.stdout, re.M)[1])
        assert json.loads((log_dir / 'EXIT_STATUS.json').read_bytes())['exit_code'] != 0
        transcript.append('early-missing-checkout\n' + result.stdout + result.stderr)
        commands += 1
    record = {'version': NAME, 'final_txt_commands': commands, 'basis_results': results,
        'zip_sha256': handoff['zip_sha256'], 'python311_grammar': True, 'bash_syntax': True,
        'zip_extract_checksum_and_no_javascript': True, 'early_failure_logging': True,
        'source_generation_readonly_reused': str(source_generation), 'external_model_calls': 0,
        'actual_genos_access': False, 'actual_remote_push': False, 'genos_deployed': False,
        'local_main_pointer_changed': False}
    (OUT / 'VALIDATION.json').write_bytes(dump(record))
    (OUT / 'DELIVERY_TESTS.log.gz').write_bytes(gzip.compress('\n'.join(transcript).encode(), mtime=0))
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
