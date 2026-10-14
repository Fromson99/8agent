"""Apply only the verified DB diagnostic rollback; preserve search and data.

Uses Python's standard library. The accompanying Bash TXT embeds this file and
its hash-bound patch specification so it can run without unpacking an archive.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import subprocess
import sys
import uuid
import zipfile

VERSION = 'GENOS_DB_LOG_ROLLBACK_20261007_R2'
MODULE = '02_BACKEND/semantic_runtime/query_latency.py'
INDEX = '02_BACKEND/semantic_runtime/unit_fulltext.py'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def path_at(root, name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or str(p) != name:
        raise ValueError('Unsafe relative path: ' + name)
    out = root / name
    for part in (out, *out.parents):
        if part == root.parent:
            break
        if part.is_symlink():
            raise ValueError('Symlink preserved: ' + name)
    out.resolve().relative_to(root)
    return out


def atomic(path, raw, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.rollback-' + uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode if mode is not None else 0o600)
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(root):
    lock = path_at(root, '.genos-code-replacement.lock')
    with lock.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def inventory(root, manifest):
    names = set()
    payload = {}
    for row in manifest['files']:
        name = row['path']
        if name in names:
            raise ValueError('Duplicate inventory path: ' + name)
        names.add(name)
        raw = path_at(root, name).read_bytes()
        if sha(raw) != row['sha256'] or len(raw) != row['bytes']:
            raise ValueError('CHECKOUT_DRIFT: ' + name + '; existing files preserved')
        payload[name] = raw
    return payload


def rebind(value, updates):
    if isinstance(value, dict):
        for name, (old, new) in updates.items():
            if value.get(name) == old:
                value[name] = new
            if value.get('path') == name and value.get('sha256') == old:
                value['sha256'] = new
        for child in value.values():
            rebind(child, updates)
    elif isinstance(value, list):
        for child in value:
            rebind(child, updates)


def prepared(root, spec):
    before_raw = path_at(root, 'CODE_MANIFEST.json').read_bytes()
    if sha(before_raw) not in spec['inventories']:
        raise ValueError('Unknown installed CODE_MANIFEST.json; existing files preserved')
    before = json.loads(before_raw)
    payload = inventory(root, before)
    after = json.loads(before_raw)
    changes = {}
    updates = {}
    for name in (MODULE, INDEX):
        old = payload[name]
        item = spec['patches'][name].get(sha(old))
        if item is None:
            raise ValueError('Unknown code bytes; preserved: ' + name)
        if 'replacement' in item:
            new = base64.b64decode(item['replacement'], validate=True)
        else:
            cut = base64.b64decode(item['remove'], validate=True)
            if old.count(cut) != 1:
                raise ValueError('Diagnostic block differs; preserved: ' + name)
            new = old.replace(cut, b'', 1)
        if sha(new) != item['after_sha256']:
            raise ValueError('Patch result hash differs: ' + name)
        compile(new, name, 'exec')
        changes[name] = new
        updates[name] = (sha(old), sha(new))
    # Replace only the existing two dependency hashes, preserving all other
    # engine fields and formatting. Do not rehash arbitrary changed code.
    for name, old in payload.items():
        if not name.startswith('02_BACKEND/ENGINES/') or not name.endswith('.json'):
            continue
        document = json.loads(old)
        files = document.get('files', {})
        new = old
        for target, (prior, current) in updates.copy().items():
            if target not in files:
                continue
            if files[target] != prior:
                raise ValueError('Existing engine pin mismatch: ' + name + ': ' + target)
            needle = (json.dumps(target) + ': ' + json.dumps(prior)).encode()
            replacement = (json.dumps(target) + ': ' + json.dumps(current)).encode()
            if new.count(needle) != 1:
                raise ValueError('Unexpected engine formatting: ' + name)
            new = new.replace(needle, replacement, 1)
        if new != old:
            changes[name] = new
            updates[name] = (sha(old), sha(new))
    rebind(after, updates)
    for row in after['files']:
        if row['path'] in changes:
            row.update(bytes=len(changes[row['path']]), sha256=sha(changes[row['path']]))
    # The unmailed latency R1 used path strings here. Normalize its inventory
    # to the current gate contract without altering any serving code.
    file_hashes = {row['path']: row['sha256'] for row in after['files']}
    after['required_files'] = [
        {'path': row, 'sha256': file_hashes[row]} if isinstance(row, str) else row
        for row in after.get('required_files', [])]
    after['id'] = VERSION
    after['db_log_rollback'] = {
        'revision': VERSION, 'prior_inventory_sha256': sha(before_raw),
        'modified_paths': sorted(changes), 'diagnostic_logging': False,
        'search_policy_changed': False, 'requires_rebuilt_generation': False,
        'field_deployment_status': 'NOT_VERIFIED',
    }
    after['query_latency'] = {'enabled': False, 'revision': 'query-latency-rollback-20261007-r1'}
    changes['CODE_MANIFEST.json'] = encoded(after)
    return before_raw, payload, changes, after


def local_verification(root):
    # Execute only the two compatibility helpers; no service import or model
    # calls. This also verifies they no longer use the timing environment flag.
    raw = path_at(root, MODULE).read_bytes()
    tree = __import__('ast').parse(raw)
    allowed = [n for n in tree.body if isinstance(n, (__import__('ast').FunctionDef,
                __import__('ast').AsyncFunctionDef)) or
               isinstance(n, __import__('ast').ImportFrom) and n.module == 'contextlib']
    module = __import__('ast').Module(body=allowed, type_ignores=[])
    namespace = {}
    exec(compile(module, MODULE, 'exec'), namespace)
    with namespace['span']('db.test', pressure=True, example=True) as metrics:
        assert metrics == {'example': True}
    def identity():
        return 7
    assert namespace['timed']('db.test')(identity) is identity
    with sqlite3.connect(':memory:') as db:
        assert namespace['rows'](db, 'SELECT ?', [7], 'verify') == [(7,)]
        try:
            namespace['rows'](db, 'SELECT * FROM missing_table', [], 'verify')
        except sqlite3.OperationalError:
            pass
        else:
            raise ValueError('SQL errors were swallowed')
    index = path_at(root, INDEX).read_bytes()
    assert b'unit_fts.connection' not in index and b'latency.obs' not in index
    compile(index, INDEX, 'exec')
    print('DB_DIAGNOSTIC_ROLLBACK PASS; SQL results/errors preserved', flush=True)


def field_identity(root, generation=None):
    result = {'code_root': str(root), 'sys_executable': sys.executable,
              'python': sys.version.split()[0], 'generation': None,
              'generation_manifest_sha256': None, 'git_commit': None,
              'code_serving_revision': None, 'workflow_test': 'NOT_RUN'}
    selected = generation or os.environ.get('GENOS_GENERATION')
    if selected:
        p = Path(selected)
        if not p.is_absolute() or p.is_symlink() or not p.is_dir():
            raise ValueError('Existing absolute generation path required')
        result.update(generation=str(p.resolve()),
                      generation_manifest_sha256=sha((p/'manifest.json').read_bytes()))
    if (root/'.git').exists():
        commit = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                capture_output=True, text=True, check=True)
        result['git_commit'] = commit.stdout.strip()
    return result


def verify(root):
    raw = path_at(root, 'CODE_MANIFEST.json').read_bytes()
    manifest = json.loads(raw)
    if manifest.get('db_log_rollback', {}).get('revision') != VERSION:
        raise ValueError('Rollback has not been applied')
    payload = inventory(root, manifest)
    for name, data in payload.items():
        if name.startswith('02_BACKEND/ENGINES/') and name.endswith('.json'):
            for target, pinned in json.loads(data).get('files', {}).items():
                if target in (MODULE, INDEX) and pinned != sha(payload[target]):
                    raise ValueError('Updated engine pin mismatch: ' + name)
    local_verification(root)
    return manifest


def apply(root, spec, artifacts):
    current = json.loads(path_at(root, 'CODE_MANIFEST.json').read_bytes())
    if current.get('db_log_rollback', {}).get('revision') == VERSION:
        verify(root)
        print('ALREADY_APPLIED; no files changed', flush=True)
        return
    before_raw, payload, changes, after = prepared(root, spec)
    identity = field_identity(root)
    backup = artifacts / ('backup-' + uuid.uuid4().hex)
    backup.mkdir(parents=True)
    receipt = {'revision': VERSION, 'root': str(root), 'state': 'PREPARED',
               'created_at': datetime.now(timezone.utc).isoformat(),
               'identity': identity, 'files': []}
    for name, new in changes.items():
        old = before_raw if name == 'CODE_MANIFEST.json' else payload[name]
        target = path_at(root, name)
        mode = target.stat().st_mode & 0o777
        atomic(path_at(backup, name), old, mode)
        receipt['files'].append({'path': name, 'before_sha256': sha(old),
                                 'after_sha256': sha(new), 'mode': mode})
    atomic(backup/'receipt.json', encoded(receipt))
    print('BACKUP=' + str(backup), flush=True)
    # All validations precede the first code write; journal state exists before
    # mutation so interruption can be undone using the exact printed backup.
    for row in receipt['files']:
        name = row['path']
        if sha(path_at(root, name).read_bytes()) != row['before_sha256']:
            raise ValueError('Code changed during preparation; preserved: ' + name)
    for row in receipt['files']:
        atomic(path_at(root, row['path']), changes[row['path']], row['mode'])
    receipt['state'] = 'APPLIED'
    atomic(backup/'receipt.json', encoded(receipt))
    verify(root)
    # Build an exact gate ZIP from the installed checkout, preserving every
    # other code file in the selected prior inventory.
    archive = backup/'APPLIED_CODE.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        out.writestr('CODE_MANIFEST.json', changes['CODE_MANIFEST.json'])
        for name, old in sorted(payload.items()):
            if Path(name).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'}:
                raise ValueError('Unexpected JavaScript in code inventory')
            out.writestr(name, changes.get(name, old))
    receipt.update(state='VERIFIED', code_zip=str(archive), code_zip_sha256=sha(archive.read_bytes()),
                   code_manifest_sha256=sha(changes['CODE_MANIFEST.json']))
    atomic(backup/'receipt.json', encoded(receipt))
    print('APPLIED_CODE_ZIP=' + str(archive), flush=True)
    print('CODE_ZIP_SHA256=' + receipt['code_zip_sha256'], flush=True)
    print('CODE_APPLIED; Git push/revision deployment/workflow test pending', flush=True)


def undo(root, backup):
    receipt = json.loads((backup/'receipt.json').read_bytes())
    if receipt['revision'] != VERSION or receipt['root'] != str(root):
        raise ValueError('Backup root/revision mismatch')
    # Verify every current and backup byte before any restore. Interrupted
    # partial application may contain either the original or patched bytes.
    for row in receipt['files']:
        name = row['path']
        actual = sha(path_at(root, name).read_bytes())
        if actual not in (row['before_sha256'], row['after_sha256']):
            raise ValueError('Later code change preserved; cannot restore: ' + name)
        if sha(path_at(backup, name).read_bytes()) != row['before_sha256']:
            raise ValueError('Backup hash mismatch: ' + name)
    for row in receipt['files']:
        atomic(path_at(root, row['path']), path_at(backup, row['path']).read_bytes(), row['mode'])
    receipt['state'] = 'UNDONE'
    atomic(backup/'receipt.json', encoded(receipt))
    print('CODE_RESTORED; redeploy original revision separately', flush=True)


def main(spec, argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['check', 'apply', 'verify', 'undo', 'gate'])
    parser.add_argument('backup', nargs='?')
    parser.add_argument('--root', default=str(Path.home()/'DEV'))
    parser.add_argument('--generation')
    args = parser.parse_args(argv)
    configured = Path(args.root).expanduser()
    print('CHECKOUT_PATH ' + json.dumps({
        'configured': str(configured), 'cwd': str(Path.cwd()),
        'exists': configured.exists(), 'is_directory': configured.is_dir(),
        'is_symlink': configured.is_symlink()}, ensure_ascii=False), flush=True)
    try:
        root = configured.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError('DEV path cannot be resolved: ' + str(configured)) from exc
    if not root.is_dir():
        raise ValueError('DEV path is not a directory: ' + str(root))
    # GENOS may mount the existing checkout through ~/DEV -> shared storage.
    # Resolve that root once; path_at still rejects symlinks inside its code.
    if not path_at(root, 'CODE_MANIFEST.json').is_file():
        raise ValueError('Installed CODE_MANIFEST.json missing from DEV: ' + str(root))
    print('CHECKOUT_RESOLVED=' + str(root), flush=True)
    artifacts = path_at(root, 'TRANSFER/db-log-rollback-r2')
    artifacts.mkdir(parents=True, exist_ok=True)
    with locked(root):
        if args.mode == 'check':
            value = json.loads(path_at(root, 'CODE_MANIFEST.json').read_bytes())
            if value.get('db_log_rollback', {}).get('revision') == VERSION:
                verify(root)
            else:
                _, _, changes, _ = prepared(root, spec)
                print('CHECK PASS; modified paths=' + str(len(changes)), flush=True)
        elif args.mode == 'apply':
            apply(root, spec, artifacts)
        elif args.mode == 'verify':
            verify(root)
        elif args.mode == 'undo':
            if not args.backup:
                raise ValueError('Supply the exact BACKUP path printed by apply')
            undo(root, Path(args.backup).resolve(strict=True))
        elif args.mode == 'gate':
            verify(root)
            if not args.backup or not args.generation:
                raise ValueError('gate requires exact BACKUP path and --generation')
            backup = Path(args.backup).resolve(strict=True)
            receipt = json.loads((backup/'receipt.json').read_bytes())
            if receipt['root'] != str(root) or receipt['revision'] != VERSION or receipt['state'] != 'VERIFIED':
                raise ValueError('Verified backup for this checkout required')
            archive = backup/'APPLIED_CODE.zip'
            if sha(archive.read_bytes()) != receipt['code_zip_sha256']:
                raise ValueError('Applied code archive hash mismatch')
            identity = field_identity(root, args.generation)
            subprocess.run([sys.executable, str(root/'06_TOOLS/COMMANDS/genos_release_gate.py'),
                '--code-zip', str(archive), '--deploy-root', str(root),
                '--generation', identity['generation']], cwd=root, check=True)
            atomic(backup/'gate-receipt.json', encoded({'state': 'PASS', 'identity': identity,
                'code_zip_sha256': receipt['code_zip_sha256']}))
            print('RELEASE_GATE PASS; push/deploy/workflow test pending', flush=True)
    print(json.dumps(field_identity(root, args.generation), ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    try:
        spec = json.loads(Path(__file__).with_name('PATCH_SPEC.json').read_bytes())
        raise SystemExit(main(spec))
    except Exception as exc:
        print('DB_LOG_ROLLBACK FAILED: ' + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(1)
