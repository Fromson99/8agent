"""Run the attached TXT verbatim against synthetic data; no field access."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import zipfile

R = Path(__file__).resolve().parents[4]
O = Path(__file__).resolve().parent
NAME = 'GENOS_DATA_ZIP_ONLY_20261007_R1.txt'
spec = importlib.util.spec_from_file_location('bundle_fixtures', R / '05_TESTS/test_genos_rag_data_bundle.py')
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
results = []
for case in ('pack_restore_dirty_checkout', 'sqlite_sidecar', 'tool_hash_mismatch', 'missing_dev'):
    fixture = tests.BundleContracts()
    fixture.setUp()
    try:
        root = fixture.dev
        def git(*args):
            return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()
        git('init', '-q')
        git('config', 'user.name', 'ZIP only validation')
        git('config', 'user.email', 'validation@example.invalid')
        pending = root / 'pending.txt'
        pending.write_text('original')
        git('add', '--', pending.name)
        git('commit', '-qm', 'Synthetic checkout')
        pending.write_text('preserved pending change')
        git('add', '--', pending.name)
        head = git('rev-parse', 'HEAD')
        index = (root / '.git/index').read_bytes()
        (root / '.env').write_text('GENOS_DATA_ROOT="$HOME/DEV/GENOS_DATA"\nGENOS_RUNTIME_DIR=/old/path\nGENOS_STATE_DIR=/old/state\nSECRET_TEST_TOKEN=must_not_print\n')
        alias = fixture.base / 'home/genos/DEV'
        alias.parent.mkdir(parents=True)
        alias.symlink_to(root, target_is_directory=True)
        attachment_dir = fixture.base / 'attachments'
        attachment_dir.mkdir()
        script = attachment_dir / NAME
        shutil.copyfile(O / NAME, script)
        if case == 'sqlite_sidecar':
            Path(str(fixture.db) + '-wal').write_bytes(b'preserve live marker')
        elif case == 'tool_hash_mismatch':
            text = script.read_text().replace('7378ad62e31369ea48a2f1512750f3891bd15be0d9a382128e4b47fed0347ee8', '0' * 64)
            script.write_text(text)
        env = {**os.environ, 'GENOS_DEV': str(alias if case != 'missing_dev' else fixture.base / 'absent'),
               'GENOS_PYTHON_DIR': str(R / '.venv/bin')}
        done = subprocess.run(['bash', str(script), '--source-prefix', str(fixture.source)],
                              env=env, capture_output=True, text=True, timeout=45)
        (O / (case + '.log')).write_text(done.stdout + done.stderr)
        assert 'must_not_print' not in done.stdout + done.stderr
        assert done.returncode == (0 if case == 'pack_restore_dirty_checkout' else 1), done.stdout + done.stderr
        assert pending.read_text() == 'preserved pending change'
        assert git('rev-parse', 'HEAD') == head and (root / '.git/index').read_bytes() == index
        for path, raw in fixture.before.items():
            assert Path(path).read_bytes() == raw
        status = json.loads(next(attachment_dir.glob('data-zip-only-logs/*/EXIT_STATUS.json')).read_text())
        assert status['exit_code'] == done.returncode
        if case == 'pack_restore_dirty_checkout':
            archive = next((root / 'TRANSFER').glob('genos-rag-data-*.zip'))
            assert archive.parent == root / 'TRANSFER'
            assert archive.with_suffix('.zip.sha256').read_text().split()[0] == sha(archive)
            unpack = fixture.base / 'unpacked'
            with zipfile.ZipFile(archive) as z:
                assert not any(Path(n).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'} for n in z.namelist())
                z.extractall(unpack)
            bundle = next(unpack.iterdir())
            restored = subprocess.run(['bash', str(bundle / 'RESTORE.sh'), '--writers-stopped',
                                       '--destination-prefix', str(fixture.destination),
                                       '--output-dir', str(fixture.base / 'restore-logs')],
                                      env={**env, 'PATH': str(R / '.venv/bin') + ':' + os.environ['PATH']}, capture_output=True, text=True, timeout=45)
            assert restored.returncode == 0, restored.stdout + restored.stderr
            for path, raw in fixture.before.items():
                assert (fixture.destination / Path(path).relative_to(fixture.source)).read_bytes() == raw
        else:
            assert not list((root / 'TRANSFER').glob('*.zip'))
            if case == 'sqlite_sidecar':
                assert Path(str(fixture.db) + '-wal').read_bytes() == b'preserve live marker'
            if case == 'tool_hash_mismatch':
                assert 'Embedded data tool hash mismatch' in done.stdout
        results.append({'case': case, 'passed': True, 'exit_code': done.returncode,
                        'original_data_preserved': True, 'git_head_and_staged_bytes_preserved': True})
    finally:
        fixture.doCleanups()
record = {'tests_passed': len(results), 'tests_failed': 0, 'cases': results,
          'attachment_sha256': sha(O / NAME), 'synthetic_data_only': True,
          'genos_accessed': False, 'field_data_zip_created': False}
(O / 'VALIDATION.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(record, ensure_ascii=False))
