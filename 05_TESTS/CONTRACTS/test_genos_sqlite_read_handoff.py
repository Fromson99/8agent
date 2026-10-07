"""Exercise the actual handoff TXT against a disposable copy of field R4 code."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '06_TOOLS/OFFLINE'))
import package_genos_sqlite_read_reuse as package


def test_field_patch_script_apply_idempotence_dependencies_and_rollback(tmp_path):
    dev = tmp_path / 'DEV'; dev.mkdir()
    base = package.BASE.parent / 'GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4.zip'
    with zipfile.ZipFile(base) as z: z.extractall(dev)
    data = dev / '01_DATA'; data.mkdir(exist_ok=True)
    (dev / '.env').write_text('PRESERVE_TEST=1\n')
    archive = package.OUT / (package.STEM + '.zip')
    with zipfile.ZipFile(archive) as z: manifest = json.loads(z.read('CODE_MANIFEST.json'))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {r['path']: sha(dev/r['path']) for r in manifest['files']}
    env = {**os.environ, 'GENOS_DEV': str(dev), 'GENOS_DATA_ROOT': str(data),
           'GENOS_HANDOFF_LOG_DIR': str(tmp_path/'logs'), 'GENOS_PREPARED_RUN': 'prepared',
           'GENOS_REUSE_RUN': 'new-serving'}
    def run(mode, *args, ok=True):
        result = subprocess.run(['bash', str(package.OUT/(package.STEM+'.txt')), mode, *args],
                                env=env, text=True, capture_output=True)
        assert (result.returncode == 0) == ok, result.stdout + result.stderr
        return result.stdout + result.stderr
    run('check'); assert all(sha(dev/n) == h for n,h in before.items())
    run('apply'); run('verify'); assert 'ALREADY INSTALLED' in run('apply')
    assert all(sha(dev/r['path']) == r['sha256'] for r in manifest['files'])
    spec = importlib.util.spec_from_file_location('package_gate', dev/'06_TOOLS/COMMANDS/genos_release_gate.py')
    gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
    def git(*args): subprocess.run(['git','-C',str(dev),*args],check=True,capture_output=True)
    git('init','-q');git('config','user.name','Test');git('config','user.email','test@example.invalid')
    tracked = [r['path'] for r in manifest['files']+manifest['required_files']]
    git('add','--force','--',*tracked);git('commit','-qm','verified patch fixture')
    assert gate.compare_zip_to_checkout(archive, dev)['code_files'] == len(manifest['files'])
    dependency = '02_BACKEND/semantic_runtime/fulltext.py'
    (dev/dependency).write_text((dev/dependency).read_text()+'\n# subsequent field edit\n')
    git('add',dependency);git('commit','-qm','field drift')
    with pytest.raises(ValueError,match='dependency differs'):
        gate.compare_zip_to_checkout(archive,dev)
    assert 'CHECKOUT_DRIFT' in run('check',ok=False)
    changed = sha(dev/dependency)
    receipt = next((dev/'09_ARTIFACTS/BACKUPS/code-replacement').glob('*/receipt.json'))
    run('rollback',str(receipt.parent))
    assert all(sha(dev/n) == h for n,h in before.items())
    assert sha(dev/dependency) == changed
    assert (dev/'.env').read_text() == 'PRESERVE_TEST=1\n'
    assert all('HANDOFF_EXIT=' in p.read_text() for p in (tmp_path/'logs').glob('*.log'))
