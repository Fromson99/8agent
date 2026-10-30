"""Prepare the pinned installer beside the uploaded ZIP and invoke its original CLI."""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
import zipfile
import zlib

NAME = 'GENOS_MAIN123_TRANSFER_20261030_R2'
SOURCE_NAME = 'GENOS_MAIN123_FULL_20261030_R1'
SOURCE_SHA256 = '__SOURCE_SHA256__'
SPEC_SHA256 = '__SPEC_SHA256__'
OVERRIDES = json.loads(zlib.decompress(base64.b64decode('__OVERRIDES__')))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def plain(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symlink path refused: ' + str(path))
    return path


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def verify(package):
    plain(package)
    raw = plain(package / 'PACKAGE.json').read_bytes()
    if digest(raw) != SPEC_SHA256:
        raise ValueError('R2 package manifest changed; existing state preserved')
    spec = json.loads(raw)
    for name, expected in spec['payload'].items():
        if digest(plain(package / name).read_bytes()) != expected:
            raise ValueError('R2 package file changed: ' + name)


def prepare(transfer):
    package = plain(transfer / NAME)
    if package.exists():
        verify(package)
        print('REUSE_PACKAGE: existing backup and install state retained', flush=True)
        return package
    prior_state = transfer / SOURCE_NAME / 'INSTALL_STATE.json'
    if prior_state.exists() or prior_state.is_symlink():
        raise ValueError('R1 installation state already exists; preserve its recovery history: ' + str(prior_state))
    archive = plain(transfer / (SOURCE_NAME + '.zip'))
    if not archive.is_file():
        raise ValueError('Run in the uploaded TRANSFER folder containing ' + archive.name)
    if digest(archive.read_bytes()) != SOURCE_SHA256:
        raise ValueError('R1 ZIP hash mismatch; no code changed')
    # A preparation failure is retained here; the final package is published atomically.
    staging = Path(tempfile.mkdtemp(prefix='.' + NAME + '.prepare-', dir=transfer))
    print('PREPARING_PACKAGE=' + str(staging), flush=True)
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        names = [i.filename for i in members]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive member')
        for member in members:
            path = PurePosixPath(member.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in member.filename
                    or stat.S_ISLNK(member.external_attr >> 16)):
                raise ValueError('Unsafe archive member: ' + member.filename)
        source.extractall(staging)
    spec = json.loads((staging / 'PACKAGE.json').read_bytes())
    for name, expected in spec['payload'].items():
        if digest(plain(staging / name).read_bytes()) != expected:
            raise ValueError('R1 payload mismatch: ' + name)
    for name, text in OVERRIDES.items():
        raw = text.encode()
        (staging / name).write_bytes(raw)
        spec['payload'][name] = digest(raw)
    spec['version'] = NAME
    raw = encoded(spec)
    if digest(raw) != SPEC_SHA256:
        raise ValueError('Derived R2 manifest mismatch; no code changed')
    (staging / 'PACKAGE.json').write_bytes(raw)
    verify(staging)
    staging.rename(package)
    return package


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', nargs='?', default='apply',
                        choices=['check', 'apply', 'gate', 'gate-code', 'gate-sqlite', 'rollback', 'status'])
    parser.add_argument('--root', type=Path, default=Path.home() / 'DEV')
    args = parser.parse_args()
    transfer = Path.cwd().resolve(strict=True)
    plain(transfer)
    with plain(transfer / '.main123-transfer-r2.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        package = prepare(transfer)
        print('TRANSFER=' + str(transfer), flush=True)
        print('PACKAGE=' + str(package), flush=True)
        print('DEV_REQUESTED=' + str(args.root), flush=True)
        command = [sys.executable, '-u', str(package / 'runner.py')]
        if args.command == 'apply':
            checked = subprocess.call(command + ['check', '--root', str(args.root)])
            if checked:
                return checked
        return subprocess.call(command + [args.command, '--root', str(args.root)])


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print('MAIN123_TRANSFER_FAILED: ' + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(2)
