"""One supervised temporary full-corpus build using the existing MAIN stages."""
import os
import errno
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import transport as t

ROOT = Path(__file__).resolve().parent


def process_group_rss(group):
    pages = 0
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) == group:
                pages += int(fields[21])
        except (FileNotFoundError, ProcessLookupError):
            pass
    return pages * os.sysconf('SC_PAGE_SIZE')


def verify_code(root):
    pins = t.read(root / 'CODE_PINS.json')
    for name, expected in pins['files'].items():
        if t.sha(t.checked(root, name)) != expected:
            raise ValueError('CODE_CHANGED: ' + name)
    return pins


def stage_commands(root, run):
    pipeline = [sys.executable, '-B', str(root / '06_TOOLS/pipeline.py')]
    policy = t.read(root / '00_SYSTEM/GLOSSARY_PIPELINE.json')
    glossary = root / '01_DATA' / policy['current_draft']['path']
    return [
        ('STRUCTURE', pipeline + ['build-data-stages', '--run-id', run, '--stage', 'structure', '--execute',
         '--latest-internal-versions', '--filename-exceptions', str(root / '01_DATA/INPUT_MAPPING/filename-exceptions.json'),
         '--structure-vlm', 'off', '--pdf-conversion', 'off', '--pdf-parser', 'local']),
        ('PREPARE', pipeline + ['document-release', 'prepare', '--run-id', run,
         '--glossary-dir', str(glossary), '--glossary-corpus-policy', 'replace']),
        ('INDEX', pipeline + ['document-release', 'reindex', '--from-run-id', run,
         '--run-id', run+'-index', '--fulltext-workers', '1']),
        ('RETURN', [sys.executable, '-B', str(root / 'worker.py'), '--export', str(root), run])]


def export_result(workspace, run):
    sys.path.insert(0, str(workspace / '02_BACKEND'))
    from lawrag.pipeline import oracle_full_package as full, oracle_query_package as query
    generation = workspace / '01_DATA/TERM_RELEASES' / (run+'-index') / 'serving/baseline/generation'
    release = t.read(generation.parents[1] / 'release.json')
    if not release.get('completed') or not release.get('serving_verified') or release.get('offline_e2e') != 'PASS':
        raise ValueError('PIPELINE_NOT_VERIFIED')
    output = workspace.parent
    # Heavy SQL projection runs here in GENOS; Dataiku only imports verified rows.
    query.export(generation, output / 'query', seconds=21600, direct_parts=True)
    _, paths, inventory = full.inventory(generation)
    paths['query/query-data.db'] = output / 'query/query-data.db'
    paths['audit/release.json'] = generation.parents[1] / 'release.json'
    paths['audit/input-raw.json'] = output / 'input-raw.json'
    paths['audit/input-support.json'] = output / 'input-support.json'
    for p in t.files(workspace / '01_DATA/LOGS'):
        paths['audit/pipeline-logs/' + str(p.relative_to(workspace / '01_DATA/LOGS'))] = p
    t.pack(paths, output / 'result.zip', metadata={'inventory': inventory,
           'code_sha256': t.sha(workspace / 'CODE_PINS.json'), 'pipeline': 'native-no-models',
           'quality_certified': False, 'active_changed': False, 'model_calls': 0})


def run(folder):
    folder = Path(folder).resolve(strict=True)
    parent = folder.parent
    # Wait for the parent to commit the worker identity.
    with t.lock(parent / 'dispatch.lock', blocking=True):
        state = t.read(folder / 'state.json')
    def update(**fields):
        with t.lock(parent / 'dispatch.lock', blocking=True):
            state = t.read(folder / 'state.json')
            state.update(**fields)
            t.write(folder / 'state.json', state)
    try:
        pins = verify_code(ROOT)
        workspace = folder / 'workspace'
        workspace.mkdir()
        for name in pins['files']:
            destination = t.checked(workspace, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(ROOT / name, destination)
            except OSError as exc:
                if exc.errno != errno.EXDEV:
                    raise
                shutil.copyfile(ROOT / name, destination)
        shutil.copyfile(ROOT / 'CODE_PINS.json', workspace / 'CODE_PINS.json')
        layout = t.read(workspace / '00_SYSTEM/WORKSPACE.json')
        for item in layout['roots']:
            (workspace / item['canonical_path']).mkdir(exist_ok=True)
        for slot, name, prefixes in [
                ('raw', 'RAW_INPUT.zip', ('01_DATA/RAW/', '01_DATA/INPUT_MAPPING/')),
                ('support', 'PIPELINE_SUPPORT.zip', ('01_DATA/LEXICON/', '01_DATA/CATALOG/'))]:
            if t.sha(folder / name) != state['archives'][slot]['sha256']:
                raise ValueError('INPUT_ARCHIVE_HASH')
            info = t.unpack(folder / name, workspace, prefixes=prefixes)
            t.write(folder / ('input-' + slot + '.json'), info)
        support = t.read(folder / 'input-support.json')
        if support['metadata']['glossary_config_sha256'] != t.sha(workspace / '00_SYSTEM/GLOSSARY_PIPELINE.json'):
            raise ValueError('GLOSSARY_POLICY_CHANGED: export and serving must use the same selected support')
        env = {k: v for k, v in os.environ.items() if k not in {'LAWRAG_WORKSPACE_ROOT', 'LAWRAG_TOOL_WORKSPACE_ROOT', 'PYTHONPATH'}}
        env.update(LAWRAG_WORKSPACE_ROOT=str(workspace), LAWRAG_TOOL_WORKSPACE_ROOT=str(workspace),
                   PYTHONPATH=str(workspace / '02_BACKEND'), PYTHONDONTWRITEBYTECODE='1',
                   PATH=str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH', ''),
                   OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        run_id = 'dku-' + folder.name
        t.write(folder / 'execution.json', {'commands': stage_commands(workspace, run_id),
                'deadline': state['deadline'], 'code_sha256': t.sha(ROOT / 'CODE_PINS.json')})
        for phase, command in stage_commands(workspace, run_id):
            update(phase=phase)
            with (folder / (phase.lower()+'.log')).open('ab') as log:
                child = subprocess.Popen(command, cwd=workspace, env=env, stdout=log,
                                         stderr=subprocess.STDOUT, start_new_session=True)
                from service import pid_identity
                update(child=pid_identity(child.pid))
                try:
                    while child.poll() is None:
                        if (folder / 'cancel.json').exists():
                            raise ValueError('CANCELLED')
                        if time.time() >= state['deadline']:
                            raise ValueError('DEADLINE_EXHAUSTED')
                        if shutil.disk_usage(folder).free < 512*t.CHUNK:
                            raise ValueError('DISK_LOW')
                        if process_group_rss(child.pid) > int(os.environ.get('PIPELINE_MAX_RSS_MB', '6144'))*t.CHUNK:
                            raise ValueError('MEMORY_LIMIT: attempt retained; size resources before a new run')
                        time.sleep(1)
                    if child.returncode:
                        raise ValueError('STAGE_FAILED: ' + phase + '; inspect phase log')
                finally:
                    if child.poll() is None:
                        os.killpg(child.pid, signal.SIGTERM)
                        try:
                            child.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            os.killpg(child.pid, signal.SIGKILL)
                            child.wait()
                update(child=None)
        verify_code(ROOT)
        result = t.read(folder / 'result.zip.receipt.json')
        update(status='COMPLETE', phase='RETURN_READY', result=result, completed=time.time())
    except BaseException as exc:
        # Preserve input, source/audit outputs and exact attempt. No semantic/model retry.
        update(status='CANCELLED' if str(exc) == 'CANCELLED' else 'FAILED', error=str(exc), ended=time.time())
        print(type(exc).__name__ + ': ' + str(exc), flush=True)
        raise


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--export':
        export_result(Path(sys.argv[2]), sys.argv[3])
    else:
        run(Path(sys.argv[1]))
