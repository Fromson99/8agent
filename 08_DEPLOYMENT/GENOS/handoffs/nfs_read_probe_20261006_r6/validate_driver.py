"""Run the actual mail TXT/ZIP against synthetic DEV/NFS/Git fixtures."""
from pathlib import Path
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAME = 'GENOS_NFS_READ_20261006_R6'


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def run(driver, env, *args, expected=0):
    result = subprocess.run(['bash', str(driver), *map(str, args)], env=env,
                            text=True, capture_output=True, timeout=45)
    assert result.returncode == expected, result.stdout[-6000:] + result.stderr[-2000:]
    return result.stdout


def main():
    field_tests = module(ROOT / '05_TESTS/test_genos_nfs_data_probe.py', 'delivery_field_tests')
    data_tests = module(ROOT / '05_TESTS/test_genos_rag_data_bundle.py', 'delivery_data_tests')
    proof = {'actual_GENOS_verified': False, 'synthetic_fixture_only': True}
    fixture = field_tests.FieldContracts()
    fixture.setUp()
    try:
        workspace = fixture.base / 'workspace'
        shutil.move(fixture.root, workspace)
        fixture.root = workspace
        dev = fixture.base / 'home/genos/DEV'
        dev.parent.mkdir(parents=True)
        dev.symlink_to(workspace, target_is_directory=True)
        actual_nfs = fixture.base / 'actual-nfs-volume'
        shutil.move(fixture.nfs, actual_nfs)
        fixture.nfs.symlink_to(actual_nfs, target_is_directory=True)
        (workspace / '.env').write_text('GENOS_DATA_ROOT="$HOME/DEV/GENOS_DATA"\nGENOS_RUNTIME_DIR=/home/genos/DEV/GENOS_DATA/runtime\nGENOS_STATE_DIR=/home/genos/DEV/GENOS_DATA/state\n')
        git = field_tests.handoff.git
        git(workspace, 'add', '.env')
        git(workspace, 'commit', '-m', 'Synthetic stale path settings')
        remote = fixture.base / 'fixture-origin.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        git(workspace, 'remote', 'add', 'origin', str(remote))
        starting_commit = git(workspace, 'rev-parse', 'HEAD')
        transfer = workspace / 'TRANSFER'
        transfer.mkdir()
        old = HERE.parent / 'nfs_read_probe_20261006_r2'
        for suffix in ('.zip', '_RUN.txt'):
            name = 'GENOS_NFS_READ_20261006_R2' + suffix
            shutil.copy2(old / name, transfer / name)
        env = {**os.environ, 'GENOS_DEV': str(dev), 'GENOS_DATA_ROOT': '/home/genos/DEV/GENOS_DATA',
               'GENOS_RUNTIME_DIR': str(fixture.runtime), 'GENOS_STATE_DIR': ''}
        before = {str(path): (path.read_bytes(), path.stat().st_mtime_ns)
                  for path in actual_nfs.rglob('*') if path.is_file()}
        old_output = run(transfer / 'GENOS_NFS_READ_20261006_R2_RUN.txt', env, 'all',
                         '--generation', fixture.gen, '--runtime', fixture.runtime,
                         '--nfs-base', fixture.nfs, expected=1)
        assert '"status": "INSTALLED"' in old_output and 'symlink path refused' in old_output
        assert git(workspace, 'rev-parse', 'HEAD') == starting_commit
        proof['R2_INSTALLED_then_prepare_symlink_error_reproduced_before_commit'] = True
        for suffix in ('.zip', '_RUN.txt'):
            shutil.copy2(HERE / (NAME + suffix), transfer / (NAME + suffix))
        # R6 must ignore the unrelated legacy environment and literal .env paths.
        env['GENOS_STATE_DIR'] = '/home/genos/DEV/GENOS_DATA/state'
        output = run(transfer / (NAME + '_RUN.txt'), env, 'all', '--generation', fixture.gen,
                     '--runtime', fixture.runtime, '--nfs-base', fixture.nfs)
        assert '"status": "PUSHED"' in output
        cfg = json.loads((workspace / field_tests.probe.CONFIG).read_text())
        receipt = json.loads(Path(cfg['receipt_path']).read_text())
        commit = git(workspace, 'rev-parse', 'HEAD')
        branch = git(workspace, 'branch', '--show-current')
        assert git(workspace, 'ls-remote', 'origin', 'refs/heads/' + branch).split()[0] == commit == receipt['commit']
        assert cfg['generation'] == str(fixture.gen) and cfg['runtime'] == str(fixture.runtime) and cfg['state'] is None
        prepare_log = next((workspace / 'TRANSFER/nfs-probe-logs').glob('prepare-*/PATH_ENTRIES.json')).parent
        assert (prepare_log / 'WORKFLOW_PASTE_ALL.txt').is_file()
        assert (prepare_log / 'NFS_MOUNT_ENTRY.json').is_file()
        for path, (raw, mtime) in before.items():
            assert Path(path).read_bytes() == raw and Path(path).stat().st_mtime_ns == mtime
        proof.update(R6_exact_R2_helper_upgrade_and_RUN_all=True,
                     DEV_and_NFS_mount_entry_aliases_supported=True,
                     stale_codespace_settings_bypassed=True,
                     exact_commit_pushed_to_local_fixture_remote=True,
                     workflow_and_path_logs_generated=True,
                     original_data_bytes_and_mtime_preserved=True)
    finally:
        fixture.doCleanups()
    fixture = data_tests.BundleContracts()
    fixture.setUp()
    try:
        transfer = fixture.dev / 'TRANSFER'
        transfer.mkdir()
        for suffix in ('.zip', '_RUN.txt'):
            shutil.copy2(HERE / (NAME + suffix), transfer / (NAME + suffix))
        (fixture.dev / '.env').write_text('GENOS_DATA_ROOT="$HOME/DEV/GENOS_DATA"\nGENOS_STATE_DIR=/home/genos/DEV/GENOS_DATA/state\n')
        env = {**os.environ, 'GENOS_DEV': str(fixture.dev), 'GENOS_RAG_DATA_OUTPUT_DIR': str(fixture.output)}
        output = run(transfer / (NAME + '_RUN.txt'), env, 'pack-data', '--writers-stopped',
                     '--source-prefix', fixture.source)
        archive = next(fixture.output.glob('genos-rag-data-*.zip'))
        assert not list(fixture.dev.glob('genos-rag-data-*'))
        unpack = fixture.base / 'unpacked-delivery'
        with zipfile.ZipFile(archive) as z:
            z.extractall(unpack)
        bundle = next(unpack.iterdir())
        manifest = json.loads((bundle / 'DATA_MANIFEST.json').read_text())
        assert manifest['generation'] == str(data_tests.tool.GENERATION) and manifest['runtime'] == str(data_tests.tool.RUNTIME)
        assert manifest['state'] is None
        run(transfer / (NAME + '_RUN.txt'), env, 'restore-data', '--writers-stopped',
            '--bundle', bundle, '--destination-prefix', fixture.destination,
            '--output-dir', fixture.base / 'restore-logs')
        for path, raw in fixture.before.items():
            assert Path(path).read_bytes() == raw
            assert (fixture.destination / Path(path).relative_to(fixture.source)).read_bytes() == raw
        proof.update(R6_RUN_pack_data_uses_recorded_field_paths_and_external_output=True,
                     R6_RUN_restore_data_preserves_original_structure_and_bytes=True)
        zip_path = transfer / (NAME + '.zip')
        zip_path.write_bytes(zip_path.read_bytes() + b'corrupted attachment')
        output = run(transfer / (NAME + '_RUN.txt'), env, 'install', expected=1)
        assert 'ZIP SHA256 mismatch' in output and not (fixture.dev / '02_BACKEND').exists()
        proof['corrupt_R6_attachment_blocked_before_application'] = True
    finally:
        fixture.doCleanups()
    (HERE / 'DRIVER_VALIDATION.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()
