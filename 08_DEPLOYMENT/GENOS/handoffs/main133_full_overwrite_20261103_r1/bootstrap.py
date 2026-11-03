"""Verify the full R1 delivery, prepare it in TRANSFER, and invoke the installer."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
import zipfile

NAME = 'GENOS_MAIN133_FULL_OVERWRITE_20261103_R1'
ZIP_SHA256 = '__ZIP_SHA256__'
SPEC_SHA256 = '__SPEC_SHA256__'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def plain(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symlink path refused: ' + str(path))
    return path


def verify(package, *, include_generated=True):
    plain(package)
    raw = plain(package / 'PACKAGE.json').read_bytes()
    if digest(raw) != SPEC_SHA256:
        raise ValueError('R1 package manifest changed; existing state preserved')
    for name, expected in json.loads(raw)['payload'].items():
        if not include_generated and name == 'code.zip':
            continue
        if digest(plain(package / name).read_bytes()) != expected:
            raise ValueError('R1 package file changed: ' + name)


def prepare(transfer):
    package = plain(transfer / NAME)
    if package.exists():
        verify(package)
        print('REUSE_PACKAGE: existing backup and install state retained', flush=True)
        return package
    archive = plain(transfer / (NAME + '.zip'))
    if not archive.is_file():
        raise ValueError('Run in the uploaded TRANSFER folder containing ' + archive.name)
    if digest(archive.read_bytes()) != ZIP_SHA256:
        raise ValueError('R1 ZIP hash mismatch; no code changed')
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
    verify(staging, include_generated=False)
    materialize_code_zip(staging)
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
    with plain(transfer / '.main133-full-overwrite-r1.lock').open('a') as lock:
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
        print('MAIN133_FULL_FAILED: ' + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(2)
