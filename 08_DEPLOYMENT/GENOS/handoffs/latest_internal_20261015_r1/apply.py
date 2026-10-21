"""Narrow hash-bound build patch. Keep checkout, configuration, RAW and generations."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
VERSION = 'GENOS_LATEST_INTERNAL_20261015_R1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def at(root, relative):
    pure = PurePosixPath(relative)
    if pure.is_absolute() or '..' in pure.parts or '\\' in relative or str(pure) != relative:
        raise ValueError('Unsafe path: ' + relative)
    path = root / relative
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symlink refused: ' + str(path))
    return path


def atomic(path, raw, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists(): temporary.unlink()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def payload():
    spec = json.loads((HERE / 'PATCH_SPEC.json').read_bytes())
    archive = (HERE / 'CODE.zip').read_bytes()
    if sha(archive) != spec['code_zip_sha256']:
        raise ValueError('CODE.zip changed')
    result = {}
    with zipfile.ZipFile(HERE / 'CODE.zip') as z:
        if len(z.namelist()) != len(set(z.namelist())):
            raise ValueError('Duplicate archive member')
        manifest = json.loads(z.read('CODE_MANIFEST.json'))
        if sha(z.read('CODE_MANIFEST.json')) != spec['code_manifest_sha256']:
            raise ValueError('Code manifest changed')
        if set(z.namelist()) != {'CODE_MANIFEST.json', *[r['path'] for r in manifest['files']]}:
            raise ValueError('Archive inventory mismatch')
        if {r['path'] for r in spec['files']} != {r['path'] for r in manifest['files']}:
            raise ValueError('Patch inventory mismatch')
        for row in manifest['files']:
            at(HERE, row['path'])
            raw = z.read(row['path'])
            if sha(raw) != row['sha256'] or len(raw) != row['bytes']:
                raise ValueError('Payload hash mismatch')
            compile(raw, row['path'], 'exec')
            result[row['path']] = raw
        for row in spec['files']:
            if sha(result[row['path']]) != row['after']:
                raise ValueError('Patch hash mismatch')
    return spec, result


def check(root, spec, *, after=False):
    bad = []
    for row in spec['files']:
        path = at(root, row['path'])
        actual = sha(path.read_bytes()) if path.is_file() else None
        allowed = [row['after']] if after else [row['before'], row['after']]
        if actual not in allowed:
            bad.append({'path': row['path'], 'actual': actual, 'expected': allowed})
    for row in spec['required_files']:
        path = at(root, row['path'])
        if not path.is_file() or sha(path.read_bytes()) != row['sha256']:
            bad.append({'path': row['path'], 'reason': 'dependency differs'})
    manifest = at(root, 'CODE_MANIFEST.json')
    if manifest.exists():
        changes = {r['path']: r['after'] for r in spec['files']}
        for row in json.loads(manifest.read_bytes()).get('files', []):
            if row['path'] in changes and row['sha256'] != changes[row['path']]:
                bad.append({'path': row['path'], 'reason': 'full inventory requires a separate rebase'})
    if bad:
        raise ValueError('REBASE_REQUIRED; files preserved: ' + json.dumps(bad, ensure_ascii=False))


def verify(root, spec):
    check(root, spec, after=True)
    subprocess.run([sys.executable, '-B', str(HERE / 'smoke_check.py'), str(root)],
                   cwd=root, check=True, env={**os.environ, 'LAWRAG_WORKSPACE_ROOT': str(root),
                                            'LAWRAG_TOOL_WORKSPACE_ROOT': str(root)})


def restore(root, backup, spec):
    receipt_path = at(backup, 'receipt.json')
    receipt = json.loads(receipt_path.read_bytes())
    if receipt['version'] != VERSION or receipt['root'] != str(root):
        raise ValueError('Backup belongs to another checkout/patch')
    expected = {r['path']: r for r in spec['files']}
    for row in receipt['files']:
        if row['path'] not in expected or any(row[k] != expected[row['path']][k] for k in ('before', 'after')):
            raise ValueError('Backup inventory changed')
        target, saved = at(root, row['path']), at(backup, row['path'])
        if sha(saved.read_bytes()) != row['before'] or sha(target.read_bytes()) not in (row['before'], row['after']):
            raise ValueError('Backup or current code changed: ' + row['path'])
    for row in receipt['files']:
        atomic(at(root, row['path']), at(backup, row['path']).read_bytes(), row['mode'])
    receipt['state'] = 'RESTORED'
    atomic(receipt_path, encoded(receipt))
    print('RESTORED ' + str(backup), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['check', 'apply', 'verify', 'undo'])
    p.add_argument('backup', nargs='?', type=Path)
    p.add_argument('--root', type=Path, default=Path.home() / 'DEV')
    args = p.parse_args()
    original = args.root.expanduser().absolute()
    if any(v.is_symlink() for v in (original, *original.parents)):
        raise ValueError('Checkout path cannot use symlinks')
    root = original.resolve(strict=True)
    top = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
                         check=True, text=True, capture_output=True).stdout.strip()
    if Path(top).resolve() != root:
        raise ValueError('Apply target must be the existing Git checkout root')
    spec, files = payload()
    backups = at(root, '08_DEPLOYMENT/GENOS/backups/latest-internal-r1')
    backups.mkdir(parents=True, exist_ok=True)
    with at(backups, 'apply.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print('TARGET=' + str(root) + ' PYTHON=' + sys.executable, flush=True)
        if args.action == 'undo':
            if args.backup is None: raise ValueError('Exact BACKUP path is required')
            backup = args.backup.absolute()
            at(backup, 'receipt.json')
            backup.resolve(strict=True).relative_to(backups)
            restore(root, backup, spec)
            return
        check(root, spec, after=args.action == 'verify')
        if args.action == 'check':
            print('CHECK PASS; code only, generation not changed'); return
        if args.action == 'verify':
            verify(root, spec); return
        pending = [r for r in spec['files'] if sha(at(root, r['path']).read_bytes()) != r['after']]
        if not pending:
            verify(root, spec); print('ALREADY_APPLIED'); return
        backup = at(backups, uuid.uuid4().hex)
        receipt = {'version': VERSION, 'root': str(root), 'state': 'PREPARED', 'files': []}
        for row in pending:
            target = at(root, row['path']); mode = stat.S_IMODE(target.stat().st_mode)
            atomic(at(backup, row['path']), target.read_bytes(), mode)
            receipt['files'].append({**row, 'mode': mode})
        atomic(backup / 'receipt.json', encoded(receipt))
        print('BACKUP=' + str(backup), flush=True)
        try:
            for row in pending:
                atomic(at(root, row['path']), files[row['path']], next(r['mode'] for r in receipt['files'] if r['path'] == row['path']))
            verify(root, spec)
        except BaseException:
            receipt['state'] = 'FAILED'
            atomic(backup / 'receipt.json', encoded(receipt))
            restore(root, backup, spec)
            raise
        receipt['state'] = 'VERIFIED'
        atomic(backup / 'receipt.json', encoded(receipt))
        print('APPLIED; new build/generation/deployment still required')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
