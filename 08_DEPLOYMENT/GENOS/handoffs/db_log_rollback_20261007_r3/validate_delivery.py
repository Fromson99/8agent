"""Exercise the exact independent TXT on all 15 recorded source inventories."""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
NAME = 'GENOS_DB_LOG_ROLLBACK_20261007_R3'
RUN = OUT/(NAME+'_RUN.txt')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(folder):
    loader = importlib.util.spec_from_file_location(folder.name, folder/'rollback_db_logs.py')
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


def main():
    transcript = []
    results = []
    folders = [OUT.with_name('query_latency_20261007_r'+str(i)) for i in range(1, 5)]
    folders.append(OUT.with_name('system_logging_20261007_r1'))
    parents = [load(OUT.with_name('db_log_rollback_20261007_r'+str(i))) for i in (1, 2)]
    parent_specs = [json.loads((OUT.with_name('db_log_rollback_20261007_r'+str(i))/'PATCH_SPEC.json').read_bytes())
                    for i in (1, 2)]
    runtime_probe = """
from types import SimpleNamespace
from semantic_runtime.contracts import Contracts
from semantic_runtime.stage_runner import StageRunner
import json,sys
c=Contracts(sys.argv[1])
if sys.argv[2]=='broken':
    try: StageRunner(SimpleNamespace(contracts=c,profile_id='legal-agent-rag-v6')).verify_profile()
    except ValueError as exc:
        assert str(exc)=='engine manifest hash mismatch',str(exc)
        print('PHOTO_ERROR_REPRODUCED '+str(exc))
    else: raise AssertionError('R2 should reproduce photo failure')
else:
    for profile in c.pipeline['profiles']:
        StageRunner(SimpleNamespace(contracts=c,profile_id=profile)).verify_profile()
    print('ACTUAL_STAGE_RUNNER_ALL_PROFILES PASS')
"""
    for folder in folders:
        record = json.loads((folder/'HANDOFF.json').read_bytes())
        for predecessor in ('original', 'rollback-r1', 'rollback-r2'):
            label = record['version']+'/'+predecessor
            with TemporaryDirectory(prefix='db-log-r3-validation-') as temporary:
                tmp = Path(temporary)
                dev = tmp/'DEV'
                dev.mkdir()
                with zipfile.ZipFile(folder/(record['version']+'.zip')) as z:
                    z.extractall(dev)
                    before = {n: z.read(n) for n in z.namelist()}
                if predecessor != 'original':
                    i = int(predecessor[-1])-1
                    _, payload, changes, _ = parents[i].prepared(dev, parent_specs[i])
                    before = {**payload, **changes}
                    for path, raw in changes.items():
                        (dev/path).write_bytes(raw)
                linked = tmp/'linked-DEV'
                linked.symlink_to(dev, target_is_directory=True)
                env = {**os.environ, 'GENOS_DEV_ROOT': str(linked),
                    'GENOS_PYTHON_DIR': str(Path(sys.executable).parent),
                    'GENOS_QUERY_LATENCY': '1', 'PYTHONPATH': str(dev/'02_BACKEND'),
                    'LAWRAG_WORKSPACE_ROOT': str(dev), 'LAWRAG_TOOL_WORKSPACE_ROOT': str(dev)}
                env.pop('GENOS_GENERATION', None)
                runtime = dev/'runtime/preserved.sqlite'
                runtime.parent.mkdir()
                runtime.write_bytes(b'synthetic-existing-runtime-preserve')
                current = dev/'CURRENT.json'
                current.write_bytes(b'{"generation":"preserve"}\n')
                command_count = 0
                def run(*args, ok=True):
                    nonlocal command_count
                    command_count += 1
                    r = subprocess.run(['bash', str(RUN), *args], cwd=dev, env=env,
                        capture_output=True, text=True, timeout=60)
                    transcript.append(label+' '+str(args)+' exit='+str(r.returncode)+'\n'+r.stdout+r.stderr)
                    assert (r.returncode == 0) == ok, transcript[-1]
                    return r
                def probe(mode):
                    r = subprocess.run([sys.executable, '-c', runtime_probe, str(dev), mode],
                        cwd=dev, env=env, capture_output=True, text=True, timeout=60)
                    transcript.append(label+' runtime-'+mode+'\n'+r.stdout+r.stderr)
                    assert r.returncode == 0, transcript[-1]
                if predecessor != 'original':
                    probe('broken')
                run('check')
                assert all((dev/n).read_bytes() == b for n, b in before.items())
                run('apply')
                backup = next((dev/'TRANSFER/db-log-rollback-r3').glob('backup-*'))
                receipt = json.loads((backup/'receipt.json').read_bytes())
                assert receipt['state'] == 'VERIFIED'
                modified = {r['path'] for r in receipt['files']}
                assert '00_SYSTEM/PIPELINE.json' in modified and 'CODE_MANIFEST.json' in modified
                assert all((dev/n).read_bytes() == b for n, b in before.items() if n not in modified)
                if predecessor != 'original':
                    assert all((dev/n).read_bytes() == b for n, b in before.items() if n.endswith('.py'))
                    assert len(modified) == (26 if folder.name.startswith('system_logging') else 2)
                probe('fixed')
                run('apply')
                run('verify')
                assert len(list((dev/'TRANSFER/db-log-rollback-r3').glob('backup-*'))) == 1
                assert runtime.read_bytes() == b'synthetic-existing-runtime-preserve'
                assert current.read_bytes() == b'{"generation":"preserve"}\n'
                subprocess.run(['git', 'init', '-q', str(dev)], check=True)
                subprocess.run(['git', '-C', str(dev), 'add', '-f', '--', *before], check=True)
                subprocess.run(['git', '-C', str(dev), '-c', 'user.name=Synthetic validation',
                    '-c', 'user.email=validation@example.invalid', 'commit', '-qm', 'R3 fixture'], check=True)
                loader = importlib.util.spec_from_file_location('gate_fixture',
                    dev/'06_TOOLS/COMMANDS/genos_release_gate.py')
                gate = importlib.util.module_from_spec(loader)
                loader.loader.exec_module(gate)
                comparison = gate.compare_zip_to_checkout(backup/'APPLIED_CODE.zip', dev)
                # Arbitrary later changes must block verify/undo before restoration.
                pipeline = dev/'00_SYSTEM/PIPELINE.json'
                applied = pipeline.read_bytes()
                pipeline.write_bytes(applied+b'\n ')
                inventory = (dev/'CODE_MANIFEST.json').read_bytes()
                run('verify', ok=False)
                run('undo', str(backup), ok=False)
                assert (dev/'CODE_MANIFEST.json').read_bytes() == inventory
                assert pipeline.read_bytes() == applied+b'\n '
                pipeline.write_bytes(applied)
                # A corrupted backup must also leave current code untouched.
                backup_pipeline = backup/'00_SYSTEM/PIPELINE.json'
                saved = backup_pipeline.read_bytes()
                backup_pipeline.write_bytes(saved+b'\n ')
                run('undo', str(backup), ok=False)
                assert pipeline.read_bytes() == applied
                backup_pipeline.write_bytes(saved)
                run('undo', str(backup))
                assert all((dev/n).read_bytes() == b for n, b in before.items())
                # An unrecorded source edit cannot be repaired by arbitrary rehashing.
                original_pipeline = pipeline.read_bytes()
                pipeline.write_bytes(original_pipeline+b'\n ')
                run('check', ok=False)
                run('apply', ok=False)
                assert (dev/'CODE_MANIFEST.json').read_bytes() == before['CODE_MANIFEST.json']
                assert pipeline.read_bytes() == original_pipeline+b'\n '
                results.append({'label': label, 'passed': True, 'txt_commands': command_count,
                    'actual_runtime_profiles_verified': True, 'photo_error_reproduced': predecessor != 'original',
                    'modified_files': len(modified), 'runtime_and_current_preserved': True,
                    'same_committed_checkout_comparison': comparison})
                print(label+' PASS', flush=True)
    raw = '\n'.join(transcript).encode()
    (OUT/'DELIVERY_TESTS.log.gz').write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    report = {'status': 'PASS', 'inventories': len(results),
        'txt_commands': sum(r['txt_commands'] for r in results),
        'actual_stage_runner_all_profiles': len(results), 'photo_error_reproductions': 10,
        'basis_results': results, 'external_model_calls': 0,
        'transcript_sha256': sha(raw), 'transcript_restore': 'gzip -dc DELIVERY_TESTS.log.gz',
        'field_applied': False, 'field_deployed': False, 'workflow_test': 'NOT_RUN'}
    (OUT/'VALIDATION.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('status', 'inventories', 'txt_commands',
                                          'actual_stage_runner_all_profiles', 'photo_error_reproductions')}))


if __name__ == '__main__':
    main()
