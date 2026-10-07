#!/usr/bin/env python3
"""Apply a small NFS diagnostic hook, prepare/commit/push the exact field code."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile

REVISION = 'nfs-data-probe-20261006-r1'
CONFIG = '00_SYSTEM/GENOS_NFS_PROBE.json'
PROBE = '02_BACKEND/semantic_runtime/nfs_data_probe.py'
WORKFLOW = '08_DEPLOYMENT/GENOS/workflow/genos_nfs_data_probe.py'
DEFAULT_GEN = Path('/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation')
DEFAULT_RUNTIME = Path('/nfs-root/diamo/8-agent/runtime')
BASE = Path('/nfs-root/diamo')
HOOK_FILES = {'service.py': '_ROOT', '08_DEPLOYMENT/GENOS/stream_app.py': 'ROOT'}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def git(root, *args, raw=False):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True)
    if result.returncode:
        # Git stderr can contain an authenticated remote URL; do not log it.
        raise RuntimeError('Git ' + args[0] + ' failed; exit=' + str(result.returncode))
    return result.stdout if raw else result.stdout.decode().strip()


def plain(path, *, mount_base=None):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.is_symlink():
            if mount_base is not None and path.is_relative_to(mount_base) and (part == mount_base or mount_base.is_relative_to(part)):
                if not part.is_dir():
                    raise ValueError('broken/non-directory NFS mount alias: ' + str(part) + ' (requested: ' + str(path) + ')')
                continue
            raise ValueError('symlink refused: ' + str(part) + ' (requested: ' + str(path) + ')')
    return path


def atomic(path, raw, mode=0o644, *, mount_base=None):
    plain(path, mount_base=mount_base)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.nfs-probe-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def hook(raw, root_name):
    text = raw.decode('utf-8')
    marker = '# GENOS_NFS_PROBE_HOOK_V1'
    block = f'''    {marker}
    if isinstance(data, dict) and str(data.get("API_TYPE", "")).strip().upper() == "NFS_DATA_PROBE":
        import importlib.util as _nfs_util
        _nfs_path = {root_name} / "{PROBE}"
        _nfs_spec = _nfs_util.spec_from_file_location("_genos_nfs_data_probe", _nfs_path)
        _nfs_module = _nfs_util.module_from_spec(_nfs_spec)
        _nfs_spec.loader.exec_module(_nfs_module)
        return await _nfs_module.gateway(data, code_root={root_name})
'''
    if marker in text:
        if block not in text:
            raise ValueError('existing diagnostic hook differs')
        return raw
    tree = ast.parse(text)
    nodes = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'service']
    if len(nodes) != 1 or [a.arg for a in nodes[0].args.args][:2] != ['config', 'data']:
        raise ValueError('service(config,data) contract missing')
    body = nodes[0].body
    first = body[0]
    line = first.end_lineno if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str) else first.lineno - 1
    lines = text.splitlines(keepends=True)
    lines.insert(line, block)
    value = ''.join(lines).encode()
    ast.parse(value, feature_version=(3, 11))
    return value


def load_probe(root):
    spec = importlib.util.spec_from_file_location('_field_nfs_probe', plain(root / PROBE))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install(a, run):
    archive = plain(a.archive)
    if load_sha(archive) != a.zip_sha256:
        raise ValueError('attachment ZIP hash mismatch')
    root = plain(a.code_root)
    if Path(git(root, 'rev-parse', '--show-toplevel')) != root:
        raise ValueError('use the existing DEV Git checkout root')
    changes = {}
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        manifest = json.loads(z.read('CODE_MANIFEST.json'))
        rows = manifest['files']
        if manifest.get('format') != '8agent-code/1' or manifest.get('id') != REVISION:
            raise ValueError('unsupported diagnostic ZIP')
        if len(names) != len(set(names)) or set(names) != {r['path'] for r in rows} | {'CODE_MANIFEST.json'}:
            raise ValueError('ZIP member list mismatch')
        for row in rows:
            name = row['path']
            rel = PurePosixPath(name)
            if rel.is_absolute() or '..' in rel.parts or '\\' in name or rel.suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'}:
                raise ValueError('unsafe/forbidden ZIP member')
            raw = z.read(name)
            if len(raw) != row['bytes'] or digest(raw) != row['sha256']:
                raise ValueError('ZIP file hash mismatch: ' + name)
            target = plain(root / name)
            if target.exists() and target.read_bytes() != raw and digest(target.read_bytes()) not in row.get('allowed_predecessors', []):
                raise ValueError('existing helper differs; preserved: ' + name)
            changes[name] = raw
    for name, root_name in HOOK_FILES.items():
        source = plain(root / name)
        if source.exists():
            changes[name] = hook(source.read_bytes(), root_name)
        elif name == 'service.py':
            raise ValueError('existing RAG service.py required')
    backup = run / 'before'
    applied = []
    records = {}
    try:
        for name, raw in changes.items():
            target = plain(root / name)
            before = target.read_bytes() if target.exists() else None
            records[name] = {'before_sha256': digest(before) if before is not None else None, 'after_sha256': digest(raw)}
            if before == raw:
                continue
            if name.endswith('.py'):
                ast.parse(raw, filename=name, feature_version=(3, 11))
            if before is not None:
                saved = backup / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
            atomic(target, raw)
            applied.append((name, before))
        git(root, 'diff', '--check')
    except BaseException:
        for name, before in reversed(applied):
            if before is None:
                (root / name).unlink(missing_ok=True)
            else:
                atomic(root / name, before)
        raise
    return {'status': 'INSTALLED', 'zip_sha256': a.zip_sha256, 'code_root': str(root),
            'checkout_commit_before': git(root, 'rev-parse', 'HEAD'), 'files': records,
            'backup': str(backup), 'commit_performed': False, 'data_generation_changed': False}


def load_sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def choose_paths(a, probe):
    # Reuse the already validated literal-env selector from the earlier data tool.
    path = a.code_root / '06_TOOLS/COMMANDS/genos_rag_data_bundle.py'
    spec = importlib.util.spec_from_file_location('_field_bundle_settings', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    settings = module.selection_settings(a)
    generation = a.generation or settings.get('GENOS_GENERATION')
    if not generation and settings.get('GENOS_DATA_ROOT'):
        value = probe.metadata(Path(settings['GENOS_DATA_ROOT']) / 'generations/CURRENT.json')
        generation = Path(value['path'])
        if value.get('schema_version') != 'genos-current-generation-v1' or probe.sha(generation / 'manifest.json') != value['manifest_sha256']:
            raise ValueError('CURRENT generation binding mismatch')
        if not generation.is_relative_to(Path(settings['GENOS_DATA_ROOT'])):
            raise ValueError('CURRENT outside data root')
    generation = Path(generation or DEFAULT_GEN)
    runtime = Path(a.runtime or settings.get('GENOS_RUNTIME_DIR') or DEFAULT_RUNTIME)
    state = None if getattr(a, 'state_unset', False) else a.state or settings.get('GENOS_STATE_DIR')
    state = Path(state) if state else None
    entries = []
    for name, path in (('generation', generation), ('runtime', runtime), ('state', state)):
        if path is None:
            continue
        entries.append({'name': name, 'logical_path': str(path), 'actual_path': str(path.resolve()),
                        'aliases': [{'path': str(part), 'target': os.readlink(part)}
                                    for part in (path, *path.parents) if part.is_symlink()]})
    print('SELECTED_PATH_ENTRIES=' + json.dumps(entries), flush=True)
    if getattr(a, 'run_dir', None):
        atomic(a.run_dir / 'PATH_ENTRIES.json', encoded(entries))
    generation, runtime = probe.plain(generation), probe.plain(runtime)
    state = probe.plain(state) if state else None
    for path in (generation, runtime, *([state] if state else [])):
        if not path.is_relative_to(a.nfs_base) or path == a.nfs_base:
            raise ValueError('all selected data must retain paths inside /nfs-root/diamo')
    return generation, runtime, state


def prepare(a, run):
    root = plain(a.code_root)
    probe = load_probe(root)
    a.phase = 'nfs_mount_entry'
    mount_entry = probe.configure_mount_root(a.nfs_base)
    atomic(run / 'NFS_MOUNT_ENTRY.json', encoded(mount_entry))
    print('NFS_MOUNT_ENTRY=' + json.dumps(mount_entry), flush=True)
    a.phase = 'select_data_paths'
    generation, runtime, state = choose_paths(a, probe)
    print('SELECTED_DATA_PATHS=' + json.dumps({'generation': str(generation), 'runtime': str(runtime),
          'state': str(state) if state else None}), flush=True)
    identifier = uuid.uuid4().hex
    a.phase = 'copy_probe_code_to_nfs'
    shared = plain(a.nfs_base / '8-agent/code-probes' / identifier, mount_base=a.nfs_base)
    if shared.exists():
        raise ValueError('new probe directory required')
    shared.mkdir(parents=True, mode=0o755)
    os.chmod(shared, 0o755)
    shared_probe = shared / 'code' / PROBE
    atomic(shared_probe, (root / PROBE).read_bytes(), mount_base=a.nfs_base)
    for directory in shared_probe.parents:
        if directory == shared:
            break
        os.chmod(directory, 0o755)
    if load_sha(shared_probe) != load_sha(root / PROBE):
        raise ValueError('initial NFS diagnostic-code copy mismatch')
    # Run pre-commit data checks using the exact reader just placed on NFS.
    spec = importlib.util.spec_from_file_location('_nfs_preflight_reader', shared_probe)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    probe.configure_mount_root(a.nfs_base)
    a.phase = 'generation_asset_paths'
    manifest, metadata_files, databases = probe.asset_paths(generation)
    preflight = []
    for name, path, expected in metadata_files:
        a.phase = 'metadata:' + name + ':' + str(path)
        actual = probe.sha(path)
        if expected and expected != actual:
            raise ValueError('generation metadata binding mismatch: ' + str(path))
        preflight.append({'name': name, 'path': str(path), 'sha256': actual})
    samples = {}
    for name, path, tables, require_row in databases:
        a.phase = 'sqlite_read:' + name + ':' + str(path)
        samples[str(path)] = probe.file_sample(path)
        preflight.append({'name': name, 'path': str(path), 'sql': probe.sqlite_read(path, tables, require_row=require_row)})
    a.phase = 'runtime_and_shortcut_read'
    with os.scandir(runtime) as entries:
        next(entries, None)
    db, pointer = probe.memory_path(runtime, state)
    if db.exists():
        preflight.append({'name': 'shortcut_legal_wiki_sql', 'path': str(db),
                          'sql': probe.sqlite_read(db, ('sw_knowledge', 'knowledge'))})
    atomic(run / 'DATA_READ_PREFLIGHT.json', encoded(preflight))
    a.phase = 'checkout_commit_preflight'
    code_paths = [PROBE, WORKFLOW, '06_TOOLS/COMMANDS/genos_nfs_probe_handoff.py',
                  '06_TOOLS/COMMANDS/genos_rag_data_bundle.py', '06_TOOLS/COMMANDS/genos_pack_rag_data.sh',
                  'service.py', CONFIG]
    code_paths += [name for name in ('service/service.py', 'service/__init__.py',
                  '08_DEPLOYMENT/GENOS/stream_app.py') if (root / name).is_file()]
    cfg = {'schema_version': REVISION, 'probe_id': identifier, 'generation': str(generation),
           'generation_manifest_sha256': probe.sha(generation / 'manifest.json'),
           'runtime': str(runtime), 'state': str(state) if state else None,
           'memory_database_required': db.exists(), 'receipt_path': str(shared / 'DEPLOYMENT.json'),
           'code_paths': sorted(code_paths), 'nfs_base': str(a.nfs_base)}
    staged = set(filter(None, git(root, 'diff', '--cached', '--name-only', '-z', raw=True).decode().split('\0')))
    if staged - set(code_paths):
        raise ValueError('unrelated staged files present; not committed by this script')
    dirty = set(filter(None, git(root, 'diff', '--name-only', '-z', raw=True).decode().split('\0')))
    if dirty - set(code_paths):
        raise ValueError('unrelated tracked changes present; preserve/resolve them before preparing deployment')
    for name in HOOK_FILES:
        if (root / name).exists() and '# GENOS_NFS_PROBE_HOOK_V1' not in (root / name).read_text():
            raise ValueError('install diagnostic hook first: ' + name)
    atomic(root / CONFIG, encoded(cfg))
    a.phase = 'commit_probe_code'
    git(root, 'add', '--', *code_paths)
    git(root, 'diff', '--cached', '--check')
    git(root, 'commit', '-m', 'Add GENOS NFS read probe ' + identifier, '--', *code_paths)
    commit = git(root, 'rev-parse', 'HEAD')
    # Pin the exact committed bytes; never export .env, data or arbitrary worktree files.
    files = {name: git(root, 'show', commit + ':' + name, raw=True) for name in code_paths}
    for name, raw in files.items():
        if plain(root / name).read_bytes() != raw:
            raise ValueError('checkout changed after commit: ' + name)
    for name, raw in files.items():
        target = shared / 'code' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        for directory in target.parents:
            if directory == shared:
                break
            os.chmod(directory, 0o755)
        atomic(target, raw, mount_base=a.nfs_base)
    binding = {'schema_version': REVISION, 'probe_id': identifier, 'commit': commit,
               'code_files': {name: digest(raw) for name, raw in files.items()},
               'immutable_samples': samples, 'generation_manifest_sha256': cfg['generation_manifest_sha256'],
               'prepared_checkout': str(root), 'code_serving_revision': None, 'field_workflow_verified': False}
    atomic(shared / 'DEPLOYMENT.json', encoded(binding), mount_base=a.nfs_base)
    archive = run / 'EFFECTIVE_CODE.zip'
    effective_manifest = {'format': '8agent-code/1', 'id': identifier,
                         'files': [{'path': name, 'bytes': len(raw), 'sha256': digest(raw)} for name, raw in sorted(files.items())]}
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(files.items()):
            z.writestr(name, raw)
        z.writestr('CODE_MANIFEST.json', encoded(effective_manifest))
    gate = root / '06_TOOLS/COMMANDS/genos_release_gate.py'
    if gate.exists() and '--code-only' in gate.read_text():
        env = {**os.environ, 'GENOS_AUTO_WARMUP': '0', 'AD_WORKER_ENABLED': '0'}
        subprocess.run([sys.executable, str(gate), '--code-only', '--code-zip', str(archive),
                        '--deploy-root', str(root)], check=True, cwd=root, env=env)
    elif git(root, 'diff', 'HEAD', '--name-only', '--', *code_paths):
        raise ValueError('committed code check failed')
    # Final diagnostic must execute the committed checkout module, as deployment does.
    report = load_probe(root).probe(code_root=root, stage='code-space', nfs_base=a.nfs_base)
    atomic(run / 'CODESPACE_READ_REPORT.json', encoded(report))
    if not report['ok']:
        raise ValueError('codespace NFS probe failed; inspect CODESPACE_READ_REPORT.json')
    workflow = files[WORKFLOW].decode().replace('__PREPARED_PROBE_ID__', identifier).replace('__PREPARED_COMMIT__', commit)
    ast.parse(workflow, feature_version=(3, 10))
    atomic(run / 'WORKFLOW_PASTE_ALL.txt', workflow.encode())
    atomic(run / 'SERVING_ENV_PATHS.txt', ('GENOS_GENERATION=' + str(generation) + '\nGENOS_RUNTIME_DIR=' + str(runtime)
           + '\nGENOS_STATE_DIR=' + (str(state) if state else '') + '\nGENOS_AUTO_WARMUP=0\nAD_WORKER_ENABLED=0\n').encode())
    return {'status': 'PREPARED_AND_COMMITTED', 'probe_id': identifier, 'commit': commit,
            'code_zip_sha256': load_sha(archive), 'code_manifest_sha256': digest(encoded(effective_manifest)),
            'effective_code_zip': str(archive), 'receipt_path': str(shared / 'DEPLOYMENT.json'),
            'generation': str(generation), 'generation_manifest_sha256': cfg['generation_manifest_sha256'],
            'runtime': str(runtime), 'workflow_paste_all': str(run / 'WORKFLOW_PASTE_ALL.txt'),
            'serving_env_paths': str(run / 'SERVING_ENV_PATHS.txt'), 'code_root': str(root),
            'pushed': False, 'code_serving_revision': None, 'workflow_verified': False,
            'full_rag_generation_gate_verified': False}


def publish(a, run):
    root = plain(a.code_root)
    cfg = json.loads(plain(root / CONFIG).read_text())
    receipt = json.loads(plain(Path(cfg['receipt_path']), mount_base=Path(cfg.get('nfs_base', str(BASE)))).read_text())
    commit = git(root, 'rev-parse', 'HEAD')
    if receipt['commit'] != commit:
        raise ValueError('HEAD differs from prepared NFS commit; do not push a different revision')
    for name, expected in receipt['code_files'].items():
        if digest(plain(root / name).read_bytes()) != expected or digest(git(root, 'show', commit + ':' + name, raw=True)) != expected:
            raise ValueError('code changed since preparation: ' + name)
    if git(root, 'status', '--porcelain=v1', '--untracked-files=no'):
        raise ValueError('uncommitted tracked changes; preserved, push not performed')
    branch = git(root, 'branch', '--show-current')
    if not branch or not re.fullmatch(r'[A-Za-z0-9_.-]+', a.remote):
        raise ValueError('existing branch and named remote required')
    git(root, 'push', a.remote, 'HEAD:refs/heads/' + branch)
    actual = git(root, 'ls-remote', a.remote, 'refs/heads/' + branch).split()
    if not actual or actual[0] != commit:
        raise ValueError('remote commit verification failed')
    return {'status': 'PUSHED', 'commit': commit, 'branch': branch, 'remote': a.remote,
            'probe_id': cfg['probe_id'], 'code_serving_revision': None, 'workflow_verified': False}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    commands = ap.add_subparsers(dest='command', required=True)
    install_parser = commands.add_parser('install')
    install_parser.add_argument('--archive', type=Path, required=True)
    install_parser.add_argument('--zip-sha256', required=True)
    prepare_parser = commands.add_parser('prepare')
    prepare_parser.add_argument('--generation', type=Path)
    prepare_parser.add_argument('--runtime', type=Path)
    state_options = prepare_parser.add_mutually_exclusive_group()
    state_options.add_argument('--state', type=Path)
    state_options.add_argument('--state-unset', action='store_true', help='confirmed field has no separate GENOS_STATE_DIR')
    prepare_parser.add_argument('--nfs-base', type=Path, default=BASE)
    publish_parser = commands.add_parser('push')
    publish_parser.add_argument('--remote', default='origin')
    for sub in (install_parser, prepare_parser, publish_parser):
        sub.add_argument('--code-root', type=Path, default=Path.cwd())
        sub.add_argument('--log-dir', type=Path)
    a = ap.parse_args(argv)
    # GENOS exposes ~/DEV as an alias of /workspace. Resolve the checkout root
    # once, then keep refusing links in code files and all NFS data paths.
    requested_root = a.code_root.absolute()
    a.code_root = plain(a.code_root.resolve(strict=True))
    print('CODE_ROOT_REQUESTED=' + str(requested_root), flush=True)
    print('CODE_ROOT_ACTUAL=' + str(a.code_root), flush=True)
    log_base = plain(a.log_dir or a.code_root / 'TRANSFER/nfs-probe-logs')
    log_base.mkdir(parents=True, exist_ok=True)
    run = log_base / (a.command + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8])
    run.mkdir()
    a.run_dir = run
    print('RUN_DIR=' + str(run), flush=True)
    atomic(run / 'STATUS.json', encoded({'status': 'STARTED', 'operation': a.command, 'python': sys.executable,
                                       'version': sys.version.split()[0]}))
    try:
        function = {'install': install, 'prepare': prepare, 'push': publish}[a.command]
        result = function(a, run)
        atomic(run / 'STATUS.json', encoded(result))
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        result = {'status': 'FAILED', 'operation': a.command, 'phase': getattr(a, 'phase', a.command), 'error_type': type(exc).__name__,
                  'error': str(exc) if not isinstance(exc, subprocess.CalledProcessError) else 'field gate failed',
                  'completed': False, 'code_serving_revision': None}
        atomic(run / 'STATUS.json', encoded(result))
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
