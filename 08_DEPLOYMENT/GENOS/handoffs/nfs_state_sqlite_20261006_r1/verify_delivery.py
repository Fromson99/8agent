"""Exercise the actual TXT against an isolated copy of its inventoried parent."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

R = Path.cwd()
O = Path(__file__).resolve().parent
BASE = R / '08_DEPLOYMENT/GENOS/handoffs/request_input_20261006_r2/GENOS_V6_REQUEST_INPUT_20261006_R2.zip'
NAME = 'GENOS_NFS_STATE_SQLITE_20261006_R1'
SCRIPT = O / (NAME + '_APPLY.txt')
archive = O / (NAME + '.zip')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

with tempfile.TemporaryDirectory(prefix='nfs-sqlite-handoff-') as temporary:
    root = Path(temporary) / 'DEV'
    root.mkdir()
    with zipfile.ZipFile(BASE) as z:
        inventory = json.loads(z.read('CODE_MANIFEST.json'))
        for row in inventory['files']:
            raw = z.read(row['path'])
            assert hashlib.sha256(raw).hexdigest() == row['sha256']
        z.extractall(root)
    runtime = root / '90_RUNTIME/semantic'
    runtime.mkdir(parents=True)
    original_db = runtime / 'case-memory/cases-v4.sqlite'
    original_db.parent.mkdir()
    original_db.write_bytes(b'original-db-must-never-be-opened-by-installer-or-check')
    prior = sha(original_db)
    env = {**os.environ, 'GENOS_DEV': str(root), 'GENOS_RUNTIME_DIR': str(runtime),
           'GENOS_MEMORY_JOURNAL_MODE': 'DELETE', 'GENOS_PYTHON_DIR': str(R / '.venv/bin'),
           'GENOS_HANDOFF_LOG_DIR': str(Path(temporary) / 'logs')}
    env.pop('GENOS_STATE_DIR', None)
    outputs = []
    def run(mode, arg=None, *, success=True):
        done = subprocess.run(['bash', str(SCRIPT), mode] + ([str(arg)] if arg else []),
                              env=env, capture_output=True, text=True, timeout=30)
        outputs.append({'mode': mode, 'exit_code': done.returncode, 'stdout': done.stdout, 'stderr': done.stderr})
        assert (done.returncode == 0) == success, done.stdout + done.stderr
        assert sha(original_db) == prior
        return done
    run('check')
    run('apply')
    run('apply')
    run('state-check')
    cfg = json.loads((root / '00_SYSTEM/PIPELINE.json').read_text())
    for entry in cfg['engines'].values():
        assert sha(root / entry['manifest']) == entry['sha256']
        m = json.loads((root / entry['manifest']).read_text())
        for f, h in m['files'].items(): assert sha(root / f) == h, f
    preserved_reader = json.loads((O / 'HANDOFF.json').read_text())['preserved_compact_reader_sha256']
    assert sha(root / '02_BACKEND/semantic_runtime/full_glossary.py') == preserved_reader
    # A real Git checkout validates all packaged bytes and pinned dependencies.
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    new_files = [r['path'] for r in json.loads((O / 'CODE_MANIFEST.json').read_text())['files']]
    all_files = sorted(set(new_files + [r['path'] for r in inventory['files']]))
    subprocess.run(['git', '-C', str(root), 'add', '-f', '--', *all_files], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Local storage check',
                    '-c', 'user.email=storage-check@example.invalid', 'commit', '-qm', 'Simulated patched checkout'], check=True)
    import importlib.util
    spec = importlib.util.spec_from_file_location('patch_gate', root / '06_TOOLS/COMMANDS/genos_release_gate.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    checked = gate.compare_zip_to_checkout(archive, root)
    backup = next((root / '09_ARTIFACTS/BACKUPS/code-replacement').iterdir())
    run('rollback', backup)
    assert not (root / '02_BACKEND/semantic_runtime/state_sqlite.py').exists()
    for row in inventory['files']:
        if row['path'] in new_files: assert sha(root / row['path']) == row['sha256']
    drift = root / '02_BACKEND/semantic_runtime/ad_store.py'
    drift.write_bytes(drift.read_bytes() + b'\n# unknown field change\n')
    unknown = sha(drift)
    run('check', success=False)
    assert sha(drift) == unknown
    result = {'standalone_txt': 'PASS', 'apply_repeat': 'PASS', 'state_check': 'PASS',
              'operational_db_preserved': 'PASS', 'compact_reader_preserved': 'PASS',
              'all_engine_code_pins': 'PASS', 'git_zip_comparison': checked,
              'rollback': 'PASS', 'unknown_code_preserved': 'PASS',
              'genos_execution': 'NOT_EXECUTED', 'generation_gate': 'NOT_EXECUTED',
              'outputs': outputs}
    (O / 'DELIVERY_VERIFICATION.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('Standalone apply/repeat/state-check/rollback/drift/compact/pins/Git comparison PASS')
