"""Inspect/stop only local processes holding this import's exact lock files.

No Oracle session termination. Hidden PID namespaces/permissions fail closed.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import time

from semantic_runtime.oracle_dp_io import DPError


def lock_paths(work, *, include_clean=False):
    work = Path(work).resolve(strict=True)
    if not (work/'restored/full-manifest.json').is_file():
        raise DPError('STOP_WORKDIR: expected the existing restored import work directory')
    result = []
    names = ('oracle-import', 'oracle-import-r3', 'oracle-clean-r1') if include_clean else ('oracle-import', 'oracle-import-r3')
    for name in names:
        directory = work/name
        if directory.exists():
            result.extend(p for p in directory.rglob('*.lock') if p.is_file())
    return sorted(set(result))


def owners(path):
    st = path.stat()
    identity = (os.major(st.st_dev), os.minor(st.st_dev), st.st_ino)
    pids = set()
    for line in Path('/proc/locks').read_text().splitlines():
        fields = line.split()
        if '->' in fields:  # Waiters are not lock owners.
            continue
        if len(fields) < 6:
            continue
        try:
            major, minor, ino = fields[5].split(':')
            if (int(major, 16), int(minor, 16), int(ino)) == identity:
                pid = int(fields[4])
                if pid > 0:
                    pids.add(pid)
        except ValueError:
            continue
    return pids


def inspect(work):
    paths = lock_paths(work, include_clean=True)
    busy, records = [], {}
    for path in paths:
        with path.open('r+') as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                busy.append(str(path))
                for pid in owners(path):
                    records.setdefault(pid, []).append(str(path))
            else:
                fcntl.flock(f, fcntl.LOCK_UN)
    return {'status': 'LOCAL_IMPORT_RUNNING' if busy else 'LOCAL_IMPORT_LOCKS_FREE',
            'processes': [{'pid': pid, 'locks': locks} for pid, locks in sorted(records.items())],
            'busy_locks': busy, 'oracle_sessions_checked': False}


def stop(work, *, grace_seconds=5):
    if not 0 <= grace_seconds <= 30:
        raise DPError('STOP_BUDGET: grace seconds 0..30')
    before = inspect(work)
    if not before['busy_locks']:
        return {**before, 'terminated': [], 'note': 'No local import lock owner; Oracle sessions not checked.'}
    if before['busy_locks'] and not before['processes']:
        raise DPError('STOP_PID_HIDDEN: lock busy but owner invisible; use Dataiku administrator')
    if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise DPError('STOP_PIDFD: Linux pidfd required; use the original notebook Interrupt')
    handles, killed = [], []
    try:
        for item in before['processes']:
            pid = item['pid']
            if pid == os.getpid():
                raise DPError('STOP_SELF: run this in a separate notebook')
            try:
                fd = os.pidfd_open(pid)
            except ProcessLookupError:
                continue
            handles.append(fd)
            proc = Path('/proc')/str(pid)
            try:
                same_user = proc.stat().st_uid == os.getuid()
                command = (proc/'cmdline').read_bytes()
                still_owner = any(pid in owners(Path(p)) for p in item['locks'])
            except FileNotFoundError:
                continue
            if not same_user or b'ipykernel' not in command or not still_owner:
                raise DPError('STOP_IDENTITY: not the same-user notebook holding the selected import lock')
            signal.pidfd_send_signal(fd, signal.SIGTERM)
            poll = select.poll(); poll.register(fd, select.POLLIN)
            forced = not poll.poll(int(grace_seconds*1000))
            if forced:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
                if not poll.poll(5000):
                    raise DPError('STOP_UNCONFIRMED: process exit not observed')
            killed.append({'pid': pid, 'forced': forced})
    finally:
        for fd in handles:
            os.close(fd)
    after = inspect(work)
    if after['busy_locks']:
        raise DPError('STOP_LOCK_BUSY: import locks still owned')
    return {**after, 'terminated': killed, 'note': 'Only local notebook processes checked; Oracle SQL may still be finishing.'}


def unresolved_write(work):
    """A killed/lost-response write needs a DBA resolution before destructive reset."""
    for name in ('oracle-import', 'oracle-import-r3'):
        for path in (Path(work)/name).rglob('*.jsonl'):
            if path.name == 'events.jsonl':
                continue
            latest = None
            with path.open() as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        raise DPError('OLD_JOURNAL_PARTIAL: preserve and inspect '+str(path)) from None
                    if row.get('status') == 'STARTED':
                        latest = row
                    elif (latest and row.get('call') == latest.get('call') and
                          row.get('status') == 'ACKNOWLEDGED'):
                        latest = None
            if latest and latest.get('write') is True:
                raise DPError('OLD_WRITE_UNCONFIRMED: Oracle-side completion/cancellation must be resolved; '+str(path))


@contextmanager
def guard(work):
    """Hold the old import locks throughout reset/load, blocking old-code restart."""
    handles = []
    try:
        for path in lock_paths(work):
            f = path.open('r+'); handles.append(f)
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DPError('OLD_IMPORT_RUNNING: stop the original notebook before replacing data') from None
        unresolved_write(work)
        yield
    finally:
        for f in reversed(handles):
            f.close()
