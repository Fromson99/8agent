"""Bounded, hash-pinned transport shared by Dataiku and the pipeline service."""
from __future__ import annotations
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import uuid
import zipfile

CHUNK = 1024 * 1024
FORMAT = 'legal-pipeline-files-v1'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(CHUNK), b''):
            h.update(block)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read(path):
    path = Path(path)
    if path.stat().st_size > 64 * CHUNK:
        raise ValueError('MANIFEST_TOO_LARGE')
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.pipeline-' + uuid.uuid4().hex + '.tmp')
    with temp.open('x', encoding='utf-8') as f:
        os.chmod(temp, 0o600)
        json.dump(value, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


@contextlib.contextmanager
def lock(path, *, blocking=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def relative(name):
    p = PurePosixPath(name)
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or p.is_absolute() or '..' in p.parts or str(p) != name):
        raise ValueError('UNSAFE_PATH')
    return name


def checked(root, name):
    root = Path(root).absolute()
    target = root / relative(name)
    for path in [target, *target.parents]:
        if path.is_symlink():
            raise ValueError('SYMLINK_REFUSED')
    return target


def files(root):
    root = Path(root)
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('SYMLINK_REFUSED: ' + str(path))
        if path.is_file():
            yield path


def pack(paths, output, *, metadata=None):
    """Stream exact files; never overwrite a prior artifact or silently skip one."""
    output = Path(output)
    if output.exists():
        raise ValueError('OUTPUT_EXISTS')
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + '.partial')
    inventory = {}
    with zipfile.ZipFile(temp, 'x', zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as z:
        for name, raw_path in sorted(paths.items()):
            relative(name)
            if name == 'TRANSPORT.json':
                raise ValueError('RESERVED_MEMBER')
            path = Path(raw_path)
            checked(path.parent, path.name)
            before = path.stat()
            h = hashlib.sha256()
            size = 0
            with path.open('rb') as src, z.open(name, 'w', force_zip64=True) as dst:
                for block in iter(lambda: src.read(CHUNK), b''):
                    dst.write(block)
                    h.update(block)
                    size += len(block)
            after = path.stat()
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, size, after.st_mtime_ns):
                raise ValueError('SOURCE_CHANGED: ' + name)
            inventory[name] = {'bytes': size, 'sha256': h.hexdigest()}
        manifest = {'format': FORMAT, 'files': inventory, 'metadata': metadata or {}}
        z.writestr('TRANSPORT.json', json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    temp.rename(output)
    receipt = {'archive': output.name, 'bytes': output.stat().st_size, 'sha256': sha(output),
               'manifest_sha256': digest(manifest), 'files': len(inventory)}
    write(output.with_suffix(output.suffix + '.receipt.json'), receipt)
    return receipt


def unpack(archive, destination, *, prefixes=None, max_bytes=100 * 1024**3):
    """Preflight all members, then restore atomically per file; conflicting bytes fail."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        names = [entry.filename for entry in entries]
        if len(set(names)) != len(names) or 'TRANSPORT.json' not in names:
            raise ValueError('ZIP_MEMBERS')
        if z.getinfo('TRANSPORT.json').file_size > 64 * CHUNK:
            raise ValueError('MANIFEST_TOO_LARGE')
        info = json.loads(z.read('TRANSPORT.json'))
        if info.get('format') != FORMAT or set(names) != {'TRANSPORT.json', *info['files']}:
            raise ValueError('ZIP_MANIFEST')
        total = 0
        needed = 0
        for entry in entries:
            checked(destination, entry.filename)
            if entry.filename == 'TRANSPORT.json':
                continue
            if prefixes and not any(entry.filename.startswith(p) for p in prefixes):
                raise ValueError('ZIP_SCOPE: ' + entry.filename)
            item = info['files'][entry.filename]
            if stat.S_ISLNK(entry.external_attr >> 16) or entry.is_dir() or entry.flag_bits & 1:
                raise ValueError('ZIP_SPECIAL_MEMBER')
            if type(item['bytes']) is not int or item['bytes'] != entry.file_size or item['bytes'] < 0:
                raise ValueError('ZIP_SIZE')
            total += item['bytes']
            target = checked(destination, entry.filename)
            if target.exists():
                if target.stat().st_size != item['bytes'] or sha(target) != item['sha256']:
                    raise ValueError('RESTORE_CONFLICT: ' + entry.filename)
            else:
                needed += item['bytes']
        if total > max_bytes or shutil.disk_usage(destination).free < needed + 512 * CHUNK:
            raise ValueError('RESTORE_CAPACITY')
        for name, item in info['files'].items():
            target = checked(destination, name)
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name('.pipeline-' + uuid.uuid4().hex + '.tmp')
            h = hashlib.sha256()
            size = 0
            try:
                with z.open(name) as src, temp.open('xb') as dst:
                    os.chmod(temp, 0o600)
                    for block in iter(lambda: src.read(CHUNK), b''):
                        size += len(block)
                        if size > item['bytes']:
                            raise ValueError('ZIP_SIZE')
                        dst.write(block)
                        h.update(block)
                if size != item['bytes'] or h.hexdigest() != item['sha256']:
                    raise ValueError('RESTORE_HASH: ' + name)
                temp.rename(target)
            finally:
                temp.unlink(missing_ok=True)
    return info
