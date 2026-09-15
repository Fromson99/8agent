#!/usr/bin/env python3
"""Offline three-file patch: hash preflight, backup, apply, and guarded rollback."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid

FILES = ('02_BACKEND/lawrag/pipeline/genos_corpus.py',
         '06_TOOLS/COMMANDS/genos_data_stages.py',
         '02_BACKEND/lawrag/pipeline/genos_build.py')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def plain(path):
    path = Path(path).expanduser().absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('symlink rejected: ' + str(path))
    return path


def replace(path, data, mode):
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def run(root, bundle, *, apply=False, rollback=None):
    root, bundle = plain(root).resolve(strict=True), plain(bundle).resolve(strict=True)
    manifest = json.loads(plain(bundle / 'PATCH_MANIFEST.json').read_text())
    if set(manifest['files']) != set(FILES):
        raise ValueError('unexpected manifest file list')
    before, target, modes = {}, {}, {}
    receipt = None
    if rollback:
        rollback = plain(rollback).resolve(strict=True)
        rollback.relative_to(bundle / 'backups')
        receipt = json.loads(plain(rollback / 'receipt.json').read_text())
        if receipt['root'] != str(root) or set(receipt['files']) != set(FILES):
            raise ValueError('backup belongs to a different installation')
    # Validate every destination, payload, and backup before changing any code.
    for name in FILES:
        path = plain(root / name)
        before[name] = path.read_bytes()
        modes[name] = stat.S_IMODE(path.stat().st_mode)
        entry = manifest['files'][name]
        payload = plain(bundle / 'payload' / name).read_bytes()
        if digest(payload) != entry['after_sha256']:
            raise ValueError('payload hash mismatch: ' + name)
        if receipt:
            target[name] = plain(rollback / name).read_bytes()
            old = receipt['files'][name]['sha256']
            if old not in (entry['before_sha256'], entry['after_sha256']) or digest(target[name]) != old:
                raise ValueError('backup hash mismatch: ' + name)
            if digest(before[name]) not in (old, entry['after_sha256']):
                raise ValueError('code changed since installation: ' + name)
        else:
            target[name] = payload
            if digest(before[name]) not in (entry['before_sha256'], entry['after_sha256']):
                raise ValueError('installed version does not match: ' + name)
    changed = [name for name in FILES if before[name] != target[name]]
    print('CHECK OK: all 3 files and payload hashes verified; changes=' + str(len(changed)))
    if not apply and not rollback:
        print('Preview only. Add --apply to install.')
        return
    if not changed:
        print('Already in requested state.')
        return
    if not receipt:
        backup = plain(bundle / 'backups') / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
        backup.mkdir(parents=True, mode=0o700)
        record = {'root': str(root), 'files': {name: {'sha256': digest(before[name]), 'mode': modes[name]} for name in FILES}}
        for name in FILES:
            path = backup / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(before[name])
        (backup / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
        print('BACKUP: ' + str(backup), flush=True)
    written = []
    try:
        for name in changed:
            path = plain(root / name)
            if path.read_bytes() != before[name]:
                raise ValueError('concurrent code change: ' + name)
            mode = receipt['files'][name]['mode'] if receipt else modes[name]
            replace(path, target[name], mode)
            written.append(name)
        for name in FILES:
            if plain(root / name).read_bytes() != target[name]:
                raise ValueError('post-write verification failed: ' + name)
    except Exception:
        for name in reversed(written):
            replace(root / name, before[name], modes[name])
        raise
    print('ROLLBACK OK' if receipt else 'APPLY OK: 3 file hashes verified')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True)
    group = p.add_mutually_exclusive_group()
    group.add_argument('--apply', action='store_true')
    group.add_argument('--rollback')
    args = p.parse_args()
    bundle = plain(Path(__file__).parent)
    try:
        with plain(bundle / '.install.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(args.root, bundle, apply=args.apply, rollback=args.rollback)
    except Exception as exc:
        p.exit(2, 'STOP: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
