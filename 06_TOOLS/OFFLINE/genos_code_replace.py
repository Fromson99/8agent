#!/usr/bin/env python3
"""Whole maintained code replacement; preserve data, environment and Git history.

Run from the physical DEV root. Uses only Python 3.11 standard library.
The adjacent code.zip is produced by the existing code_ship.py allowlist.
"""
import argparse
import ast
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import uuid
import zipfile

TREES = {'00_SYSTEM', '02_BACKEND', '06_TOOLS'}
PRESERVED = {'01_DATA', '.git', '.venv', 'GENOS_DATA', 'TRANSFER', '90_RUNTIME', '99_ARCHIVE'}
FROZEN_CODE_PREFIXES = ('02_BACKEND/GENERATIONS/', '06_TOOLS/GENERATIONS/',
                        '02_BACKEND/lawrag/research/candidates/')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def plain(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symlink path: ' + str(path))
    return path


def snapshot(path):
    """Only hashes/modes; no file contents appear in the receipt or console."""
    path = plain(path)
    if not path.exists():
        return None
    rows = {}
    for p in [path, *sorted(path.rglob('*'))] if path.is_dir() else [path]:
        if '__pycache__' in p.relative_to(path).parts or p.suffix == '.pyc':
            continue
        plain(p)
        mode = p.stat().st_mode
        key = str(p.relative_to(path))
        if stat.S_ISDIR(mode):
            rows[key] = ['dir', stat.S_IMODE(mode)]
        elif stat.S_ISREG(mode):
            with p.open('rb') as f:
                rows[key] = ['file', stat.S_IMODE(mode), hashlib.file_digest(f, 'sha256').hexdigest()]
        else:
            raise ValueError('Special file in code tree: ' + str(p))
    return rows


def save(path, value):
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(temp, path)


def payload(bundle):
    manifest = json.loads((bundle / 'DELIVERY.json').read_text())
    archive = bundle / 'code.zip'
    if sha(archive.read_bytes()) != manifest['code_zip_sha256']:
        raise ValueError('code.zip SHA256 mismatch')
    result = {}
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive paths')
        code = json.loads(z.read('CODE_MANIFEST.json'))
        expected = {r['path']: r for r in code['files']}
        if set(names) != set(expected) | {'CODE_MANIFEST.json'}:
            raise ValueError('Unlisted archive members')
        for name in names:
            p = PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name:
                raise ValueError('Unsafe archive path')
            if p.parts[0] in PRESERVED or (p.name.startswith('.env') and not p.name.endswith('.example')):
                raise ValueError('Data or credentials in code archive')
            info = z.getinfo(name)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('Archive symlink')
            raw = z.read(name)
            if name in expected and sha(raw) != expected[name]['sha256']:
                raise ValueError('Payload hash mismatch: ' + name)
            if name.endswith('.py'):
                try:
                    # Compile on the actual installing interpreter too. Newer
                    # ast feature_version checks alone miss some f-string rules.
                    compile(raw, name, 'exec', dont_inherit=True)
                    ast.parse(raw, filename=name, feature_version=(3, 11))
                except SyntaxError as exc:
                    raise ValueError(f'Python syntax: {name}:{exc.lineno}: {exc.msg}') from exc
            result[name] = (raw, ((info.external_attr >> 16) & 0o777) or 0o644)
    units = sorted(TREES | {n for n in result if PurePosixPath(n).parts[0] not in TREES})
    return result, units, manifest


def full_payload(archive):
    """Overlay an inventoried full code ZIP; data and old code snapshots stay separate."""
    archive = plain(archive)
    result = {}
    syntax_checked = frozen_preserved = 0
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or 'CODE_MANIFEST.json' not in names:
            raise ValueError('Duplicate archive paths or missing CODE_MANIFEST.json')
        code = json.loads(z.read('CODE_MANIFEST.json'))
        if code.get('format') != '8agent-code/1':
            raise ValueError('Unsupported full code archive')
        expected = {r['path']: r for r in code['files']}
        if len(expected) != len(code['files']) or set(names) != set(expected) | {'CODE_MANIFEST.json'}:
            raise ValueError('Unlisted archive members')
        for name in names:
            p = PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name or str(p) != name:
                raise ValueError('Unsafe archive path')
            data_declaration = (name == '01_DATA/README.md' or
                                name.startswith(('01_DATA/CONTRACTS/', '01_DATA/SOURCE_SETS/')))
            if ((p.parts[0] in PRESERVED and not data_declaration) or
                    (p.name.startswith('.env') and not p.name.endswith('.example')) or
                    p.suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs', '.key', '.pem', '.p12', '.pfx',
                                         '.sqlite', '.sqlite3', '.db', '.log'}):
                raise ValueError('Data, credentials or excluded attachment in code archive: ' + name)
            info = z.getinfo(name)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('Archive symlink')
            raw = z.read(name)
            if name in expected and (len(raw) != expected[name]['bytes'] or sha(raw) != expected[name]['sha256']):
                raise ValueError('Payload hash mismatch: ' + name)
            if name.endswith('.py'):
                if name.startswith(FROZEN_CODE_PREFIXES):
                    frozen_preserved += 1
                else:
                    compile(raw, name, 'exec', dont_inherit=True)
                    ast.parse(raw, filename=name, feature_version=(3, 11))
                    syntax_checked += 1
            result[name] = (raw, ((info.external_attr >> 16) & 0o777) or 0o644)
    print(f'FULL_CODE_SYNTAX current={syntax_checked} frozen_preserved={frozen_preserved}', flush=True)
    digest = sha(archive.read_bytes())
    return result, sorted(result), {'id': 'full-code-' + digest[:20], 'code_zip_sha256': digest,
                                   'syntax_current_checked': syntax_checked,
                                   'frozen_code_preserved_not_certified': frozen_preserved}


def move(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.rename(destination)


def rollback(folder):
    folder = plain(folder)
    receipt_path = folder / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    root = plain(receipt['root'])
    if receipt['status'] == 'ROLLED_BACK':
        print('Already rolled back.'); return
    # Validate ALL files before restoring anything. Concurrent edits are retained.
    actions = []
    for name, row in receipt['units'].items():
        target, old = root / name, folder / 'old' / name
        current, backup = snapshot(target), snapshot(old)
        if backup is not None:
            if backup != row['before'] or current not in (None, row['after']):
                raise ValueError('Changed code/backup; preserve and inspect: ' + name)
            actions.append((name, True))
        elif row['before'] is None:
            if current not in (None, row['after']):
                raise ValueError('Changed new code: ' + name)
            if current is not None:
                actions.append((name, False))
        elif current != row['before']:
            raise ValueError('Original code/backup missing: ' + name)
    receipt['status'] = 'ROLLING_BACK'; save(receipt_path, receipt)
    for name, restore in reversed(actions):
        target = root / name
        if target.exists():
            move(target, folder / 'discarded' / name)
        if restore:
            move(folder / 'old' / name, target)
    for name, row in receipt['units'].items():
        if snapshot(root / name) != row['before']:
            raise ValueError('Rollback verification failed: ' + name)
    receipt['status'] = 'ROLLED_BACK'; save(receipt_path, receipt)
    print('ROLLBACK OK: original code restored; data/environment unchanged')


def install(root, bundle, apply=False, archive=None):
    root, bundle = plain(root), plain(bundle)
    if not (root / 'service.py').is_file() or not (root / '02_BACKEND').is_dir():
        raise ValueError('Run from the existing physical DEV project root')
    content, units, delivery = full_payload(archive) if archive is not None else payload(bundle)
    if archive is not None:
        for name, (raw, _) in content.items():
            target = plain(root / name)
            if name.startswith(FROZEN_CODE_PREFIXES) and target.exists() and sha(target.read_bytes()) != sha(raw):
                raise ValueError('Immutable code snapshot differs; preserve and inspect: ' + name)
    base = plain(root / '09_ARTIFACTS/BACKUPS/code-replacement')
    # Unfinished transactions require recovery, never a second blind installation.
    for p in sorted(base.glob('*/receipt.json')) if base.exists() else []:
        r = json.loads(plain(p).read_text())
        if r['status'] not in ('APPLIED', 'ROLLED_BACK'):
            raise ValueError('Recover previous installation with --rollback ' + str(p.parent))
        if r['status'] == 'APPLIED' and r['delivery'] == delivery['id']:
            if all(snapshot(root / n) == row['after'] for n, row in r['units'].items()):
                print('ALREADY INSTALLED: ' + delivery['id']); return p.parent
            raise ValueError('Installed code changed; inspect before another replacement')
    before = {name: snapshot(root / name) for name in units}
    for name in units:
        target = plain(root / name)
        if target.exists() and target.stat().st_dev != root.stat().st_dev:
            raise ValueError('Code target is a different mount: ' + name)
    print('CHECK OK: package verified; no Git baseline required; files=' + str(len(content)))
    if not apply:
        print('Preview only. Use --apply to replace maintained code.'); return
    folder = base / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, mode=0o700)
    for name, (raw, mode) in content.items():
        p = folder / 'new' / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw); p.chmod(mode)
    record = {'delivery': delivery['id'], 'root': str(root), 'status': 'PREPARED',
              'code_zip_sha256': delivery.get('code_zip_sha256'),
              'generation': None, 'generation_manifest_sha256': None,
              'deployment_commit': None, 'code_serving_revision': None,
              'onsite_workflow_verified': False,
              'units': {n: {'before': before[n], 'after': snapshot(folder / 'new' / n)} for n in units}}
    receipt = folder / 'receipt.json'
    save(receipt, record)
    print('BACKUP/RECOVERY: ' + str(folder), flush=True)
    record['status'] = 'APPLYING'; save(receipt, record)
    try:
        for name in units:
            target = root / name
            if snapshot(target) != before[name]:
                raise ValueError('Concurrent change: ' + name)
            if target.exists():
                move(target, folder / 'old' / name)
            move(folder / 'new' / name, target)
        for name, row in record['units'].items():
            if snapshot(root / name) != row['after']:
                raise ValueError('Installed code hash mismatch: ' + name)
        record['status'] = 'APPLIED'; save(receipt, record)
    except BaseException:
        rollback(folder)
        raise
    print('INSTALL OK: ' + delivery['id'])
    print('Preserved: 01_DATA, GENOS_DATA, .env, .venv, .git, TRANSFER; no deployment/activation')
    return folder


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--archive', type=Path, help='Full code_ship.py ZIP; back up and overlay its inventoried files')
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--rollback', type=Path)
    args = p.parse_args()
    os.umask(0o077)
    if sys.version_info < (3, 11):
        p.exit(2, 'Python 3.11+ required\n')
    root = plain(args.root)
    try:
        # Keep the lock outside all replacement units and retain its inode.
        with plain(root / '.genos-code-replacement.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.rollback:
                if json.loads((args.rollback / 'receipt.json').read_text())['root'] != str(root):
                    raise ValueError('Backup belongs to a different project root')
                rollback(args.rollback)
            else:
                install(root, Path(__file__).resolve().parent, args.apply, archive=args.archive)
    except Exception as exc:
        p.exit(2, 'STOP: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
