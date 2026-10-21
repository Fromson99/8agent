"""Prepare a DEV ZIP, then apply its generation-bound selection on NFS.

Uses the existing plan/activate/rollback implementation from the chosen DEV.
No source/database/code copying, model calls, or generation-pointer changes.
"""
import argparse
from contextlib import closing
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import stat
import subprocess
import sys
import time
import traceback
import zipfile

HERE = Path(__file__).resolve().parent
VERSION = 'GENOS_SEARCH_SELECTION_TRANSFER_20261021_R1'
DATA_ZIP = 'GENOS_LATEST_SELECTION_DATA_20261021_R1.zip'
DEFAULT_GENERATION = '/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation'
MAX_MEMBER = 32 * 1024 * 1024


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def plain(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('symlink path refused: ' + str(path))
    return path


def optional_sha(path):
    plain(path)
    return sha(path) if path.exists() else None


def stat_signature(path):
    s = plain(path).stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def emit(event, **fields):
    print(json.dumps({'event': event, **fields}, ensure_ascii=False), flush=True)


def commit(root):
    p = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                       capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def preflight(args):
    # ~/DEV may itself be a platform alias for /workspace. Data paths may not.
    root = args.root.expanduser().resolve(strict=True)
    generation = plain(args.generation).resolve(strict=True)
    spec = read(HERE / 'CODE_MANIFEST.json')
    actual = {}
    for name, expected in spec['required_existing_code'].items():
        path = plain(root / name)
        actual[name] = sha(path)
        if actual[name] != expected:
            raise ValueError('existing DEV selection code differs from tested code: ' + name)
    sys.path.insert(0, str(root / '02_BACKEND'))
    from semantic_runtime import deployment_paths
    from lawrag.pipeline import search_selection as selection
    from semantic_runtime.storage import Store
    from semantic_runtime.resident_data import available_memory
    if os.environ.get('DP', '').strip().lower() in {'oracle', '1', 'true'}:
        raise ValueError('Oracle mode is outside this NFS selection handoff')
    env = dict(os.environ)
    config = deployment_paths.install(root, environment=env)
    selected = env.get('GENOS_GENERATION', '').strip()
    if not selected:
        raise ValueError('selected GENOS_GENERATION is not explicit; check DEV/00_SYSTEM/GENOS_SERVING_PATHS.json')
    if plain(selected).resolve(strict=True) != generation:
        raise ValueError('photo/explicit generation differs from current DEV serving selection: ' + selected)
    deployment_paths.verify_generation(config, generation)
    manifest = read(generation / 'manifest.json')
    if manifest.get('schema_version') not in {'term-source-generation-v1', 'term-source-generation-v2'}:
        raise ValueError('unsupported immutable generation')
    for suffix in ('-wal', '-journal'):
        if Path(str(generation / 'store.sqlite') + suffix).exists():
            raise ValueError('live SQLite WAL/journal present; immutable data required')
    free = available_memory()
    if free and free < 1024 * 1024 * 1024:
        raise MemoryError('less than 1 GiB available RAM; stop other heavy work before retrying')
    for path in (root, generation.parent):
        if shutil.disk_usage(path).free < 64 * 1024 * 1024:
            raise OSError('less than 64 MiB disk space available: ' + str(path))
    target = selection.selection_path(generation)
    plain(target)
    binding = {'version': VERSION, 'code_root': str(root), 'commit': commit(root),
        'code_files': actual, 'generation': str(generation),
        'generation_manifest_sha256': sha(generation / 'manifest.json'),
        'store_sha256_declared': manifest['store_sha256'],
        'database_state': stat_signature(generation / 'store.sqlite'),
        'target': str(target), 'python': sys.executable, 'python_version': sys.version,
        'code_serving_revision': None, 'field_workflow_test': 'NOT_RUN',
        'full_database_hash_recomputed': False}
    emit('binding', **binding)
    return root, generation, target, binding, selection, Store


def unchanged(generation, binding):
    if (sha(generation / 'manifest.json') != binding['generation_manifest_sha256'] or
            stat_signature(generation / 'store.sqlite') != binding['database_state']):
        raise ValueError('source generation changed during operation')


def consumer(Store, generation, *, latest):
    # Same Store/Selection used by create_app; avoid whole-dataset resident cache.
    with closing(Store(generation, verify=False)) as store:
        if latest:
            store.selection.require_latest()
        store.check_unchanged()
        return {'latest_verified': latest,
            'selection_sha256': store.selection.fingerprint,
            'visible_documents': store.db.execute('SELECT count(*) FROM document').fetchone()[0]}


def comparable(value):
    value = json.loads(json.dumps(value))
    value['exceptions'].pop('path', None)
    return value


def make_zip(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in members.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 21, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, raw)
    return stream.getvalue()


def save_new_or_same(selection, path, raw):
    plain(path)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('existing output differs; preserve it and use another --archive name: ' + str(path))
        return
    selection.atomic(path, raw)


def load_bundle(path):
    plain(path)
    with zipfile.ZipFile(path) as archive:
        if sorted(archive.namelist()) != ['BUNDLE.json', 'generation.json']:
            raise ValueError('unexpected ZIP members; extraction refused')
        if any(i.file_size > MAX_MEMBER for i in archive.infolist()):
            raise ValueError('ZIP metadata exceeds 32 MiB per member')
        bundle = json.loads(archive.read('BUNDLE.json'))
        raw = archive.read('generation.json')
    if bundle.get('version') != VERSION or bundle.get('selection_sha256') != digest(raw):
        raise ValueError('selection ZIP hash/version mismatch')
    return bundle, json.loads(raw)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['build', 'check', 'apply', 'status', 'rollback'])
    p.add_argument('--root', type=Path, default=Path.home() / 'DEV')
    p.add_argument('--generation', type=Path, default=Path(DEFAULT_GENERATION))
    p.add_argument('--archive', type=Path)
    a = p.parse_args()
    root, generation, target, binding, selection, Store = preflight(a)
    archive = plain(a.archive.expanduser() if a.archive else root / DATA_ZIP)
    archive.parent.mkdir(parents=True, exist_ok=True)
    # Serialize copies of this handoff on the same DEV archive. The common
    # activate/rollback additionally locks the actual NFS selection target.
    with plain(archive.with_suffix('.transfer.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if a.action == 'build':
            before = optional_sha(target)
            if target.exists():
                consumer(Store, generation, latest=False)  # malformed/stale state is not overwritten
            value = selection.plan(generation, latest=True)
            if target.exists() and read(target).get('schema_version') == 'filename-search-selection-v2':
                if comparable(read(target)) != comparable(value):
                    raise ValueError('existing v2 selection differs from current approved plan; preserve and review')
            raw = selection.encode(value)
            bundle = {'version': VERSION, 'generation': str(generation),
                'generation_manifest_sha256': binding['generation_manifest_sha256'],
                'store_sha256_declared': binding['store_sha256_declared'],
                'code_files': binding['code_files'], 'selection_sha256': digest(raw),
                'source_selection_sha256': before, 'counts': value['counts']}
            unchanged(generation, binding)
            if optional_sha(target) != before:
                raise ValueError('source selection changed while building ZIP')
            if archive.exists():
                old_bundle, old_value = load_bundle(archive)
                same = {k: v for k, v in old_bundle.items() if k != 'source_selection_sha256'} == {
                    k: v for k, v in bundle.items() if k != 'source_selection_sha256'}
                if not same or old_value != value:
                    raise ValueError('existing ZIP differs; preserve it and use another --archive filename')
            else:
                save_new_or_same(selection, archive, make_zip({'BUNDLE.json': encoded(bundle), 'generation.json': raw}))
            selection.atomic(archive.with_suffix('.build-receipt.json'), encoded({
                **binding, 'state': 'ZIP_CREATED_NFS_UNCHANGED', 'archive': str(archive),
                'archive_sha256': sha(archive), 'source_selection_sha256': before, 'counts': value['counts']}))
            emit('ZIP_CREATED_NFS_UNCHANGED', archive=str(archive), archive_sha256=sha(archive),
                 target=str(target), counts=value['counts'])
            return
        bundle, archived = load_bundle(archive)
        for key in ('generation', 'generation_manifest_sha256', 'store_sha256_declared', 'code_files'):
            if bundle.get(key) != binding[key]:
                raise ValueError('ZIP differs from selected data/code: ' + key)
        # A deployment may move DEV; only the exceptions file LOCATION is rebound.
        value = selection.plan(generation, latest=True)
        if comparable(value) != comparable(archived):
            raise ValueError('ZIP plan does not match current metadata and approved rules')
        raw = selection.encode(value)
        after = digest(raw)
        state_path = archive.with_suffix('.apply-state.json')
        plain(state_path)
        state = read(state_path) if state_path.exists() else None
        ident = {'archive_sha256': sha(archive), 'target': str(target), 'after_sha256': after}
        if state and any(state.get(k) != v for k, v in ident.items()):
            raise ValueError('saved apply state belongs to another archive/target')
        current = optional_sha(target)
        if a.action == 'rollback':
            if not state or not state.get('receipt'):
                raise ValueError('no owned apply receipt; nothing may be rolled back')
            restored = selection.rollback(state['receipt'])
            if target.exists() and state.get('before_mode') is not None:
                os.chmod(target, state['before_mode'])
            state.update(state='RESTORED_RESTART_REQUIRED', rollback=restored)
            selection.atomic(state_path, encoded(state))
            unchanged(generation, binding)
            emit('RESTORED_RESTART_REQUIRED', target=str(target))
            return
        if state and state.get('state') == 'RESTORED_RESTART_REQUIRED' and a.action == 'apply':
            raise ValueError('this operation was rolled back; preserve it and build to a new --archive filename')
        expected_before = state['before_sha256'] if state else bundle['source_selection_sha256']
        if current not in (expected_before, after):
            raise ValueError('NFS selection changed after ZIP creation; preserve current file')
        if a.action in ('check', 'status'):
            if current == after:
                detail = consumer(Store, generation, latest=True)
                emit('READY_RESTART_REQUIRED', target=str(target), **detail)
            else:
                if target.exists(): consumer(Store, generation, latest=False)
                emit('READY_TO_APPLY', target=str(target), current_sha256=current, counts=value['counts'])
            unchanged(generation, binding)
            return
        if state is None:
            state = {**ident, 'version': VERSION, 'state': 'PREPARED',
                     'before_sha256': current, 'binding': binding, 'receipt': None,
                     'before_mode': stat.S_IMODE(target.stat().st_mode) if target.exists() else None,
                     'applied_mode': stat.S_IMODE(target.stat().st_mode) if target.exists()
                         else (stat.S_IMODE((generation/'manifest.json').stat().st_mode) & 0o666) | 0o600}
            selection.atomic(state_path, encoded(state))
        unchanged(generation, binding)
        # Ownership recovery after abrupt exit: only accept the receipt matching
        # this archive's before/after hashes and exact generation target.
        if not state.get('receipt') and state['before_sha256'] != after:
            found = []
            for item in target.parent.glob('receipts/' + target.stem + '-*/receipt.json'):
                r = read(plain(item))
                if (r.get('target') == str(target) and r.get('generation') == str(generation)
                        and r.get('before_sha256') == state['before_sha256']
                        and r.get('after_sha256') == after
                        and r.get('state') in {'PREPARED', 'APPLIED_RESTART_REQUIRED'}):
                    found.append(str(item))
            if len(found) > 1:
                raise ValueError('multiple recovery receipts; manual receipt review required')
            if found: state['receipt'] = found[0]
        try:
            if not target.parent.exists():
                target.parent.mkdir()
                os.chmod(target.parent, stat.S_IMODE(generation.parent.stat().st_mode) & 0o2777)
            applied = selection.activate(value)
            if applied.get('receipt'): state['receipt'] = applied['receipt']
            os.chmod(target, state['applied_mode'])
            selection.atomic(state_path, encoded(state))
            if state['before_sha256'] != after and not state['receipt']:
                raise ValueError('applied selection has no owned rollback receipt')
            detail = consumer(Store, generation, latest=True)
            if detail['visible_documents'] != value['counts']['searchable_documents']:
                raise ValueError('consumer document count differs from ZIP plan')
            unchanged(generation, binding)
        except BaseException:
            if (state.get('before_mode') is not None and
                    optional_sha(target) == state['before_sha256']):
                os.chmod(target, state['before_mode'])
            state['state'] = 'FAILED_REVIEW_LOG_AND_RECEIPT'
            selection.atomic(state_path, encoded(state))
            raise
        state.update(state='APPLIED_RESTART_REQUIRED', consumer=detail)
        selection.atomic(state_path, encoded(state))
        emit('APPLIED_RESTART_REQUIRED', target=str(target), receipt=state.get('receipt'), **detail)


if __name__ == '__main__':
    start = time.monotonic()
    try:
        # Single lightweight metadata process; no fulltext/model workers.
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        cap = 2 * 1024 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (min(cap, hard) if hard != -1 else cap, hard))
        def expired(*_):
            raise TimeoutError('900 second operation deadline reached; saved state and receipts are retained')
        signal.signal(signal.SIGALRM, expired)
        signal.alarm(900)
        main()
    except BaseException as exc:
        emit('TRANSFER_FAILED', error_type=type(exc).__name__, detail=str(exc))
        traceback.print_exc()
        sys.exit(1)
    finally:
        signal.alarm(0)
        emit('resource_usage', seconds=round(time.monotonic() - start, 3),
             max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
