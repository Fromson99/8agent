"""SQLite state policy shared by shortcut, AD and their case adapter.

Network filesystems use rollback journaling. SQLite's file locks and existing
BEGIN IMMEDIATE transactions serialize writes; no lock bypass is permitted.
This policy does not certify a deployment's NFS locking or fsync behaviour.
"""
from .legal_agent import journal_storage
from pathlib import Path
import os
import re
import sqlite3


NETWORK_FILESYSTEMS = {'nfs', 'nfs4', 'cifs', 'smb3'}


def filesystem(path):
    """Use the deepest actual mount, including escaped mount-point names."""
    path = Path(path).resolve()
    mounts = Path('/proc/mounts')
    matched = []
    if mounts.is_file():
        for line in mounts.read_text().splitlines():
            parts = line.split()
            if len(parts) < 3: continue
            target = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), parts[1])
            if path.is_relative_to(Path(target)):
                matched.append((len(Path(target).parts), target, parts[2]))
    if matched:
        _, target, kind = max(matched, key=lambda item: item[0])
        if target != '/' or not path.is_relative_to(Path('/nfs-root')): return kind
    # Keep the documented GENOS NFS path conservative when proc is unavailable.
    return 'nfs' if path.is_relative_to(Path('/nfs-root')) else 'unknown'


def network_storage(path):
    return filesystem(path) in NETWORK_FILESYSTEMS


def journal_policy(path, requested=None):
    network = network_storage(path)
    if requested is None: requested = os.environ.get('GENOS_MEMORY_JOURNAL_MODE')
    mode = (requested or ('DELETE' if network else 'WAL')).upper()
    if mode not in {'DELETE', 'WAL'}:
        raise ValueError('STATE_SQLITE: journal mode must be DELETE or WAL')
    if network and mode != 'DELETE':
        raise ValueError('STATE_SQLITE: journal mode must be DELETE on /nfs-root or other NFS/CIFS mounts; WAL is unsupported')
    return mode


def configure(db, path, *, requested=None, borrowed=False):
    mode = journal_policy(path, requested)
    current = db.execute('PRAGMA journal_mode').fetchone()[0].upper()
    if borrowed and not network_storage(path) and requested is None and not os.environ.get('GENOS_MEMORY_JOURNAL_MODE'):
        if current in {'DELETE', 'WAL'}: mode = current
    if current != mode:
        if borrowed:
            raise ValueError('STATE_SQLITE: shared case connection has a different journal mode')
        # Conversion is performed by SQLite under its exclusive database lock.
        # Never delete WAL/SHM/journal sidecars or copy only the database file.
        current = db.execute('PRAGMA journal_mode=' + mode).fetchone()[0].upper()
    if current != mode:
        raise ValueError('STATE_SQLITE: requested journal mode was not applied')
    db.execute('PRAGMA synchronous=FULL')
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=30000')
    return mode


def connect(path, *, requested=None):
    path = Path(path).resolve()
    mode = journal_policy(path, requested)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = journal_storage.connect(path, isolation_level=None, timeout=30)
    try:
        configure(db, path, requested=mode)
        return db
    except BaseException:
        db.close()
        raise


def readonly(path):
    """Feature/session inspection never initializes or changes the authority."""
    path = Path(path).resolve()
    return journal_storage.connect(path.as_uri() + '?mode=ro', uri=True, timeout=30)
