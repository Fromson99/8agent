#!/usr/bin/env python3
"""Reuse an explicit prepared run for OFF rebuilding with the native reference path."""
import argparse
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import time
import traceback

from genos_reindex_logging import BuildLog, atomic, observe


def process_identity(pid):
    proc = Path('/proc') / str(pid)
    try:
        stat = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
        if stat[0] == 'Z':
            return None
        return {'pid': int(pid), 'start_time': stat[19],
                'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (FileNotFoundError, ProcessLookupError):
        return None


def old_records(data, run):
    root = Path(data) / 'LOGS' / run
    return [root / 'meaning-recovery-r1/off-worker.json', root / 'meaning-recovery-r1/on-worker.json',
            root / 'meaning-variants/worker.json']


def discover_active_builds(run, log, pending):
    dev = Path(os.environ['LAWRAG_WORKSPACE_ROOT']).resolve()
    scripts = {dev / '06_TOOLS/OFFLINE/genos_optimized_rebuild.py', dev / '06_TOOLS/OFFLINE/genos_reindex_runner.py'}
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid(): continue
        try:
            if proc.stat().st_uid != os.getuid(): continue
            argv = [x.decode() for x in (proc / 'cmdline').read_bytes().split(b'\0') if x]
            script_index = next((i for i, x in enumerate(argv) if Path(x).is_absolute() and Path(x).resolve() in scripts), None)
            if script_index is None or argv[script_index + 1] != 'build': continue
            if argv[argv.index('--prepared-run') + 1] != run: continue
            if Path(argv[argv.index('--dev') + 1]).resolve() != dev: continue
            identity = process_identity(int(proc.name))
            if identity is None: continue
            atomic(log.directory / ('stopped-build-' + proc.name + '.json'), {**identity, 'argv': argv})
            if process_identity(int(proc.name)) != identity: continue
            log.emit('stop-existing-rebuild', 'SIGNAL', pid=int(proc.name), prepared_run=run)
            os.kill(int(proc.name), signal.SIGINT); pending.append(identity)
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, IndexError): continue


def stop_recorded(data, run, log, *, timeout=120):
    """Signal only exact recorded process identities; never kill an unknown process."""
    pending = []
    discover_active_builds(run, log, pending)
    for path in old_records(data, run):
        if not path.is_file():
            continue
        record = json.loads(path.read_text())
        ident = {k: record[k] for k in ('pid', 'start_time', 'boot_id')}
        if process_identity(record['pid']) == ident:
            log.emit('stop-old-worker', 'SIGNAL', metadata=str(path), pid=record['pid'], signal='SIGINT')
            os.kill(record['pid'], signal.SIGINT)
            pending.append(record)
    started = time.monotonic()
    while pending:
        pending = [r for r in pending if process_identity(r['pid']) ==
                   {k: r[k] for k in ('pid', 'start_time', 'boot_id')}]
        if not pending:
            break
        if time.monotonic() - started >= timeout:
            raise RuntimeError('Recorded worker still stopping; files preserved, no code applied')
        log.emit('stop-old-worker', 'RUNNING', pids=[r['pid'] for r in pending])
        time.sleep(1)
    log.emit('stop-old-worker', 'DONE', elapsed_seconds=round(time.monotonic() - started, 3))


def check_idle(data, run):
    for path in old_records(data, run):
        if path.is_file():
            row = json.loads(path.read_text())
            if process_identity(row['pid']) == {k: row[k] for k in ('pid', 'start_time', 'boot_id')}:
                raise RuntimeError('Old worker active: ' + str(path))
    # Locks belong to known runs; acquiring them never changes input artifact bytes.
    parent = Path(data) / 'TERM_RELEASES' / run
    parents = [parent, parent / (run + '-bulk-r2')]
    roots = (parents + [root / 'meaning-variants' / mode for root in parents for mode in ('off', 'on')]
             + [parent / name for name in ('serving', 'reindex')])
    handles = []
    try:
        for root in roots:
            if root.is_dir():
                for name in ('.lock', '.meaning-worker.lock'):
                    handle = (root / name).open('a'); handles.append(handle)
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError('A previous run holds its build/review lock; no code applied') from None
    finally:
        for handle in handles:
            handle.close()


def fork_prepared(context, data, new_run, code_manifest, *, reference_batch=8, reference_cases=10000):
    """Create new execution lineage, retaining immutable prepared inputs by reference."""
    import genos_meaning_variants as variants
    from semantic_runtime.contracts import sha
    from lawrag.pipeline.genos_status import validate_run_id
    validate_run_id(new_run)
    original = context['parent']
    if new_run == original.name:
        raise ValueError('Use a new output run ID; previous plans and outputs are preserved')
    target = Path(data).resolve() / 'TERM_RELEASES' / new_run
    target.mkdir(parents=True, exist_ok=True)
    with variants.locked(target / '.fork.lock'):
        serving = context.get('reindex_settings', {}).get('serving', False)
        expected = {'schema_version': 'genos-prepared-reuse-origin-v1' if serving else 'genos-optimized-prepared-off-v1', 'prepared_run': original.name,
                    'prepared_directory': str(original), 'prepared_pins': context['pins'],
                    'execution_code_pins': context.get('execution_code_pins', {}),
                    'code_manifest_sha256': sha(code_manifest),
                    'runner_sha256': sha(__file__), 'reference_batch': reference_batch,
                    'reference_cases': reference_cases,
                    'meaning_mode': 'reuse_completed' if context.get('reindex_settings', {}).get('completed_glossary') else 'off',
                    'activated': False,
                    'reindex_policy': context.get('reindex_policy'), 'reindex_settings': context.get('reindex_settings'), 'reference_llm': False}
        origin = target / 'origin.json'
        if origin.exists():
            if json.loads(origin.read_text()) != expected:
                raise ValueError('New run inputs/code/settings changed; preserve it and use another run ID')
        else:
            if any(p.name != '.fork.lock' for p in target.iterdir()):
                raise ValueError('Output run already contains unrelated artifacts; preserved')
            atomic(origin, expected)
        selection = target / 'sources/selection.json'
        selection.parent.mkdir(exist_ok=True)
        source_selection = original / 'sources/selection.json'
        if selection.exists():
            if selection.read_bytes() != source_selection.read_bytes():
                raise ValueError('New selection snapshot changed')
        else:
            with selection.open('xb') as out:
                out.write(source_selection.read_bytes()); out.flush(); os.fsync(out.fileno())
    return {**context, 'parent': target,
            'pins': {**context['pins'], **context.get('execution_code_pins', {}),
                     str(origin): sha(origin), str(selection): sha(selection)}}


def verified_code_pins(dev, manifest):
    from semantic_runtime.contracts import sha
    result = {}
    selected = json.loads(Path(manifest).read_text())
    for row in selected['files'] + selected.get('required_files', []):
        if row.get('role', 'code') != 'code':
            continue
        path = (dev / row['path']).resolve(strict=True)
        path.relative_to(dev.resolve())
        if sha(path) != row['sha256']:
            raise ValueError('Applied code differs from selected ZIP: ' + row['path'])
        result[str(path)] = row['sha256']
    return result


def rebuild(context, *, reference_batch=8, reference_cases=10000, shared_root=None, log):
    import genos_reindex_only
    if context.get('reindex_settings', {}).get('serving'):
        if shared_root:
            raise ValueError('Publish the verified serving generation separately; no automatic activation')
        return genos_reindex_only.rebuild_serving(context, log=log)
    if shared_root:
        log.emit('shared-publication', 'NOT_RUN', reason='index-only output; no serving bundle')
    return genos_reindex_only.rebuild(context, log=log)


def arguments(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['check', 'stop-old', 'build', 'publish'])
    p.add_argument('--dev', type=Path, required=True)
    p.add_argument('--data-root', type=Path, required=True)
    p.add_argument('--prepared-run', required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--code-manifest', type=Path, required=True)
    p.add_argument('--log-dir', type=Path, required=True)
    p.add_argument('--shared-root', type=Path)
    p.add_argument('--serving', action='store_true', help='reuse prepared inputs to build and verify a complete serving generation')
    p.add_argument('--storage-profile', choices=['legacy','compact-v1','compact-v2'], default='legacy')
    p.add_argument('--completed-glossary', type=Path, help='explicit completed review derived from the prepared glossary')
    p.add_argument('--fulltext-granularity', choices=['article', 'unit'], default=None)
    p.add_argument('--reference-batch', type=int, default=8)
    p.add_argument('--reference-cases', type=int, default=10000)
    p.add_argument('--heartbeat', type=float, default=5)
    a = p.parse_args(argv)
    if a.storage_profile != 'legacy' and not a.serving:
        p.error('--storage-profile compact requires --serving')
    if a.serving and a.fulltext_granularity is None:
        p.error('--serving requires explicit --fulltext-granularity')
    if a.action == 'publish' and (not a.serving or not a.shared_root):
        p.error('publish requires --serving and --shared-root')
    if a.serving and a.shared_root and a.action != 'publish':
        p.error('Use the separate publish action for shared publication')
    if a.fulltext_granularity and not a.serving:
        p.error('--fulltext-granularity requires --serving')
    if a.completed_glossary and not a.serving:
        p.error('--completed-glossary requires --serving')
    if not 1 <= a.reference_batch <= 32 or not 1 <= a.reference_cases <= 10000 or a.heartbeat <= 0:
        p.error('Invalid reference limit or heartbeat interval')
    if a.prepared_run == a.run_id:
        p.error('Prepared run and output run must differ')
    return a


def main(argv=None):
    a = arguments(argv)
    dev = a.dev.resolve(strict=True)
    os.environ['LAWRAG_WORKSPACE_ROOT'] = str(dev)
    os.environ['PYTHONUNBUFFERED'] = '1'
    sys.path.insert(0, str(dev / '02_BACKEND'))
    os.environ['GENOS_VARIANTS_TOOL_PATH'] = str(Path(__file__).resolve())
    from lawrag.core.llm import load_env
    load_env()
    from semantic_runtime.genos_backend import safe
    from lawrag.pipeline.genos_status import validate_run_id
    import genos_meaning_variants as variants
    import genos_reindex_only
    log = BuildLog(a.log_dir, interval=a.heartbeat)
    status = 1
    try:
        validate_run_id(a.prepared_run); validate_run_id(a.run_id)
        log.emit('run', 'START', action=a.action, python=sys.executable, version=sys.version,
                 code_root=str(dev), data_root=str(a.data_root.resolve()),
                 prepared_run=a.prepared_run, output_run=a.run_id,
                 reference_batch=a.reference_batch, reference_cases=a.reference_cases,
                 meaning_review='NOT_RUN', reference_llm=False)
        if a.action == 'stop-old':
            with log.phase('stop-old-workers'):
                stop_recorded(a.data_root, a.prepared_run, log)
        else:
            with log.phase('prepared-input-verification'):
                check_idle(a.data_root, a.prepared_run)
                context = genos_reindex_only.prepared(a.data_root, a.prepared_run)
                if a.completed_glossary:
                    context = genos_reindex_only.select_completed_glossary(context, a.completed_glossary)
                if a.serving:
                    if not context['knowledge']:
                        raise ValueError('Completed full knowledge bundle required for serving reuse')
                    context['code_root'] = dev
                    context['reindex_policy'] = 'prepared-reuse-serving-v1'
                    context['reindex_settings'] = {**context['reindex_settings'], 'serving': True,
                                                   'fulltext_granularity': a.fulltext_granularity,
                                                   'storage_profile': a.storage_profile}
                log.emit('prepared-input', 'VERIFIED', documents=len(context['selection']['document_ids']),
                         source=str(context['source']), glossary=str(context['draft']), reindex_policy=context['reindex_policy'])
            if a.action in ('build', 'publish'):
                with log.phase('verify-applied-optimization-code'):
                    context['execution_code_pins'] = verified_code_pins(dev, a.code_manifest)
                with log.phase('freeze-new-output-run'):
                    context = fork_prepared(context, a.data_root, a.run_id, a.code_manifest,
                                            reference_batch=a.reference_batch, reference_cases=a.reference_cases)
                if a.action == 'publish':
                    genos_reindex_only.publish_serving(context, a.shared_root, log=log)
                else:
                    rebuild(context, reference_batch=a.reference_batch, reference_cases=a.reference_cases,
                            shared_root=a.shared_root, log=log)
        status = 0
    except BaseException as error:
        status = 130 if isinstance(error, KeyboardInterrupt) else 1
        log.emit('run', 'INTERRUPTED' if status == 130 else 'FAILED', error=str(error), exception=type(error).__name__)
        print(safe(traceback.format_exc()), file=sys.stderr, flush=True)
    finally:
        log.close(status)
    return status


if __name__ == '__main__':
    raise SystemExit(main())
