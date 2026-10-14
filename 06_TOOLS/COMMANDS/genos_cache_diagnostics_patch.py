#!/usr/bin/env python3
"""Apply only a verified, reversible serving cache-inspection hook in DEV.

No data rebuild, Git commit/push, revision deployment, or model calls.
Use the sealed diagnostic package directory, not an arbitrary payload.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
import zipfile

REVISION = 'genos-cache-diagnostics-20261008-r1'
MODULE = '02_BACKEND/semantic_runtime/cache_diagnostics.py'
HOOK = '''    # GENOS_CACHE_DIAGNOSTICS_HOOK_V1
    if isinstance(data, dict) and str(data.get("API_TYPE", "")).strip().upper() == "CACHE_DIAGNOSTICS":
        from semantic_runtime.cache_diagnostics import collect as _collect_cache_diagnostics
        return {"status": 200, "body": await asyncio.to_thread(_collect_cache_diagnostics, globals())}

'''
DEPENDENCIES = ('02_BACKEND/semantic_runtime/resident_data.py',
                '02_BACKEND/semantic_runtime/runtime_cache.py',
                '02_BACKEND/semantic_runtime/unit_fulltext.py',
                '02_BACKEND/semantic_runtime/query_latency.py',
                '02_BACKEND/semantic_runtime/document_agent.py',
                '02_BACKEND/semantic_runtime/legal_agent/law_candidates.py',
                '00_SYSTEM/PIPELINE.json', '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def checked_path(root, relative):
    path = root / relative
    path.resolve().relative_to(root)
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError('code path symlink refused: ' + relative)
    return path


def atomic(path, raw, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.cache-diagnostic-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def hook(raw):
    text = raw.decode('utf-8')
    if 'GENOS_CACHE_DIAGNOSTICS_HOOK_V1' in text:
        if text.count(HOOK) != 1:
            raise ValueError('existing diagnostic hook differs; preserved')
        return raw
    tree = ast.parse(text)
    nodes = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'service']
    if len(nodes) != 1 or [arg.arg for arg in nodes[0].args.args] != ['config', 'data']:
        raise ValueError('service(config, data) contract missing')
    if '_PROCESS_INSTANCE_ID = uuid.uuid4().hex' not in text:
        raise ValueError('process identity contract differs')
    first = nodes[0].body[0]
    line = first.end_lineno if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str) else first.lineno - 1
    lines = text.splitlines(keepends=True)
    lines.insert(line, HOOK)
    result = ''.join(lines).encode()
    ast.parse(result, feature_version=(3, 11))
    if result.replace(HOOK.encode(), b'', 1) != raw:
        raise ValueError('patch changed unrelated bytes')
    return result


def plan(root, module_raw, supported):
    entry = checked_path(root, 'service.py')
    original = entry.read_bytes()
    patched = hook(original)
    baseline = original.replace(HOOK.encode(), b'', 1)
    if sha(baseline) not in supported:
        raise ValueError('unrecognized service SHA; preserved: ' + sha(baseline))
    target = checked_path(root, MODULE)
    if target.exists() and target.read_bytes() != module_raw:
        raise ValueError('existing inspection module differs; preserved')
    ast.parse(module_raw, feature_version=(3, 11))
    changes = {'service.py': patched, MODULE: module_raw}
    manifest_path = checked_path(root, 'CODE_MANIFEST.json')
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_bytes())
        if manifest.get('format') != '8agent-code/1' or not isinstance(manifest.get('files'), list):
            raise ValueError('existing code manifest format unsupported; preserved')
        rows = {row['path']: row for row in manifest['files']}
        if len(rows) != len(manifest['files']):
            raise ValueError('existing code manifest has duplicate paths')
        for name in changes:
            path = checked_path(root, name)
            if name in rows and (not path.is_file() or rows[name]['sha256'] != sha(path.read_bytes())):
                raise ValueError('existing code manifest pin differs: ' + name)
        for name, raw in changes.items():
            rows[name] = {**rows.get(name, {}), 'path': name, 'sha256': sha(raw), 'bytes': len(raw)}
        manifest['files'] = [rows[name] for name in sorted(rows)]
        changes['CODE_MANIFEST.json'] = encoded(manifest)
    return changes


def apply(root, changes, run):
    receipt = {'revision': REVISION, 'code_root': str(root), 'state': 'PREPARED', 'files': {}}
    for name, after in changes.items():
        path = checked_path(root, name)
        before = path.read_bytes() if path.exists() else None
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
        receipt['files'][name] = {'before_sha256': sha(before) if before is not None else None,
                                'after_sha256': sha(after), 'mode': mode,
                                'changed': before != after}
        if before is not None:
            atomic(run / 'before' / name, before, mode)
    # Backup and persistent status precede the first checkout write.
    atomic(run / 'RECEIPT.json', encoded(receipt))
    try:
        for name, raw in changes.items():
            path = checked_path(root, name)
            row = receipt['files'][name]
            current = sha(path.read_bytes()) if path.exists() else None
            if current != row['before_sha256']:
                raise ValueError('checkout changed after backup: ' + name)
            if row['changed']:
                atomic(path, raw, row['mode'])
        receipt['state'] = 'APPLIED_NOT_DEPLOYED'
    except BaseException:
        receipt['state'] = 'FAILED_BACKUPS_PRESERVED'
        atomic(run / 'RECEIPT.json', encoded(receipt))
        raise
    atomic(run / 'RECEIPT.json', encoded(receipt))
    rows = [{'path': name, 'sha256': sha(raw), 'bytes': len(raw)} for name, raw in changes.items()
            if name != 'CODE_MANIFEST.json']
    required = [{'path': name, 'sha256': sha(checked_path(root, name).read_bytes())}
                for name in DEPENDENCIES if checked_path(root, name).is_file()]
    with zipfile.ZipFile(run / 'APPLIED_CODE.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('CODE_MANIFEST.json', encoded({'format': '8agent-code/1', 'id': REVISION,
                                                      'files': rows, 'required_files': required}))
        for row in rows:
            archive.writestr(row['path'], changes[row['path']])
    return receipt


def rollback(receipt_path):
    receipt = json.loads(receipt_path.read_bytes())
    if receipt.get('revision') != REVISION:
        raise ValueError('rollback receipt revision differs')
    root = Path(receipt['code_root']).resolve(strict=True)
    if not set(receipt['files']) <= {'service.py', MODULE, 'CODE_MANIFEST.json'}:
        raise ValueError('rollback file scope differs')
    restores = []
    for name, row in receipt['files'].items():
        if not row['changed']:
            continue
        path = checked_path(root, name)
        current = sha(path.read_bytes()) if path.exists() else None
        if current == row['before_sha256']:
            continue  # Partial apply or repeated rollback is safe.
        if current != row['after_sha256']:
            raise ValueError('later code changes preserved: ' + name)
        before = None
        if row['before_sha256'] is not None:
            backup = checked_path(receipt_path.parent, 'before/' + name)
            before = backup.read_bytes()
            if sha(before) != row['before_sha256']:
                raise ValueError('backup hash differs: ' + name)
        restores.append((path, before, row['mode']))
    for path, raw, mode in restores:
        if raw is None:
            path.unlink()
        else:
            atomic(path, raw, mode)
    atomic(receipt_path.parent / 'ROLLBACK.json', encoded({'revision': REVISION, 'state': 'ROLLED_BACK_NOT_DEPLOYED'}))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('check', 'apply', 'rollback'))
    parser.add_argument('--code-root', type=Path, default=Path(os.environ.get('GENOS_DEV_ROOT') or '~/DEV').expanduser())
    parser.add_argument('--package', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    package = args.package.resolve(strict=True)
    run = package / 'runs' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    def emit(value):
        line = json.dumps(value, ensure_ascii=False)
        print(line, flush=True)
        with (run / 'RUN.log').open('a', encoding='utf-8') as stream:
            stream.write(line + '\n')
    emit({'phase': 'START', 'mode': args.mode, 'python': sys.executable})
    try:
        if args.mode == 'rollback':
            if args.receipt is None:
                raise ValueError('--receipt from the applied run is required')
            rollback(args.receipt.resolve(strict=True))
            emit({'state': 'ROLLED_BACK_NOT_DEPLOYED'})
        else:
            manifest = json.loads((package / 'PACKAGE.json').read_bytes())
            if manifest.get('revision') != REVISION:
                raise ValueError('package revision differs')
            for row in manifest['files']:
                raw = checked_path(package, row['path']).read_bytes()
                if len(raw) != row['bytes'] or sha(raw) != row['sha256']:
                    raise ValueError('package file hash differs: ' + row['path'])
            root = args.code_root.resolve(strict=True)  # Existing DEV mount alias is permitted.
            result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
            if result.returncode or Path(result.stdout.strip()).resolve() != root:
                raise ValueError('existing DEV Git checkout required')
            changes = plan(root, (package / 'cache_diagnostics.py').read_bytes(), manifest['supported_service_sha256'])
            emit({'state': 'CHECKED', 'code_root': str(root), 'files': {name: sha(raw) for name, raw in changes.items()}})
            if args.mode == 'apply':
                already = all(checked_path(root, name).exists() and checked_path(root, name).read_bytes() == raw
                              for name, raw in changes.items())
                if already:
                    emit({'state': 'VERIFIED_ALREADY_APPLIED', 'backup_note': 'Keep the original apply receipt for rollback.'})
                else:
                    receipt = apply(root, changes, run)
                    emit({'state': receipt['state'], 'receipt': str(run / 'RECEIPT.json'),
                          'code_zip': str(run / 'APPLIED_CODE.zip')})
        atomic(run / 'EXIT_STATUS.json', encoded({'exit': 0}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, SyntaxError, zipfile.BadZipFile) as exc:
        emit({'state': 'FAILED', 'error_type': type(exc).__name__, 'reason': str(exc)})
        atomic(run / 'EXIT_STATUS.json', encoded({'exit': 1}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
