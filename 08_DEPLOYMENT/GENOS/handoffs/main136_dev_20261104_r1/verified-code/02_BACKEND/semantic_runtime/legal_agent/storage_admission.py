"""Bound growth by stopping new work, never by deleting decision history.

Reservations are advisory headroom, not a filesystem hard quota: an already
received response/failure must still be recorded. Reads and recovery remain
available at the limit. flock leases recover automatically after process exit.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import fcntl
import os
from ..oracle_runtime_paths import Path
import shutil
import time
import uuid

from .errors import AdmissionRejected, ContractError
from .journal_storage import enabled

MIB = 1024 * 1024
ACTIVE = ContextVar('genos_storage_reservation', default=None)


class StorageCapacity(AdmissionRejected):
    code = 'STORAGE_CAPACITY'


def settings():
    values = []
    for name, default in [('GENOS_RUNTIME_LIMIT_MIB', 20480),
                          ('GENOS_RUNTIME_RESERVE_MIB', 1024),
                          ('GENOS_RUNTIME_MIN_FREE_MIB', 2048)]:
        try:
            value = int(os.environ.get(name, default))
            if value <= 0:
                raise ValueError()
        except ValueError as exc:
            raise ContractError(name + ' must be a positive integer') from exc
        values.append(value * MIB)
    if values[1] >= values[0]:
        raise ContractError('GENOS_RUNTIME_RESERVE_MIB must be smaller than limit')
    return tuple(values)


def used_bytes(root):
    from ..oracle_runtime_paths import virtual, records
    if virtual(root): return records().allocated_bytes()
    total = 0
    for parent, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d != '.storage-admission' and not (Path(parent)/d).is_symlink()]
        for name in files:
            path = Path(parent)/name
            try:
                if not path.is_symlink():
                    total += path.stat().st_size
            except FileNotFoundError:
                pass  # A completed request may remove its temporary file.
    return total


def storage_roots(root):
    roots = [Path(root).resolve()]
    state = os.environ.get('GENOS_STATE_DIR')
    if state:
        if not Path(state).is_absolute():
            raise ContractError('GENOS_STATE_DIR must be absolute')
        roots.append(Path(state).resolve())
    # Count overlapping trees once, including separately mounted case state.
    return [p for p in set(roots) if not any(p != q and p.is_relative_to(q) for q in roots)]


def free_bytes(root):
    root = Path(root)
    while not root.exists():
        root = root.parent
    return shutil.disk_usage(root).free


def check(root, limit, reserve, min_free, active=0):
    roots = storage_roots(root)
    used = sum(used_bytes(p) for p in roots)
    if used + (active + 1) * reserve > limit or min(free_bytes(p) for p in roots) < min_free + reserve:
        raise StorageCapacity('STORAGE_CAPACITY: 기록 보관 한도에 도달했습니다. '
            '기존 판단·실패 기록은 유지됩니다. 관리자가 외부 보관/용량을 확인한 뒤 재개하세요.')


@contextmanager
def admission(root):
    from ..oracle_runtime_paths import virtual, records
    if virtual(root):
        if ACTIVE.get() is not None:
            yield
            return
        store=records();limit,reserve,min_free=settings()
        from ..oracle_agent_records import STATE,UTC_SECONDS
        key='a1:reserve:'+uuid.uuid4().hex
        with store.lease(['storage-admission',store.scope],wait=30):
            active=store._query(f'SELECT COUNT(*) AS N FROM {STATE} WHERE SCOPE_HASH_VAL=:scope '
                f"AND ST_KEY_ID LIKE 'a1:reserve:%' AND JSON_VALUE(ST_JSON_CN,'$.token') IS NOT NULL "
                f"AND JSON_VALUE(ST_JSON_CN,'$.expires' RETURNING NUMBER)>{UTC_SECONDS}",limit=1)[0]['N']
            if store.allocated_bytes()+(active+1)*reserve>limit:
                raise StorageCapacity('STORAGE_CAPACITY: Oracle 기록 저장 예산에 도달했습니다. 기존 기록은 보존됩니다.')
            lease=store.lease(['storage-reservation',key],key=key,ephemeral=True,track=False)
            lease.__enter__()
        token=ACTIVE.set({'oracle':True,'store':store,'limit':limit,'checked':time.monotonic()})
        try:yield
        finally:
            ACTIVE.reset(token);lease.__exit__(None,None,None)
        return
    if ACTIVE.get() is not None or not (enabled() or os.environ.get('GENOS_RUNTIME_DIR') or os.environ.get('GENOS_RUNTIME_LIMIT_MIB')):
        yield
        return
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    limit, reserve, min_free = settings()
    directory = root/'.storage-admission'
    directory.mkdir(exist_ok=True)
    lease = None
    lease_path = directory/(uuid.uuid4().hex+'.lease')
    try:
        with (directory/'admission.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            active = 0
            for path in directory.glob('*.lease'):
                try:
                    with path.open('r+b') as prior:
                        try:
                            fcntl.flock(prior, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            active += 1
                        else:
                            path.unlink()  # Dead owner; no user data in a lease.
                except FileNotFoundError:
                    pass
            check(root, limit, reserve, min_free, active)
            lease = lease_path.open('xb')
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        token = ACTIVE.set({'root': root, 'limit': limit, 'reserve': reserve,
                            'min_free': min_free, 'checked': time.monotonic()})
        try:
            yield
        finally:
            ACTIVE.reset(token)
    finally:
        if lease is not None:
            # Unlink while still holding the lease; another admission cannot
            # mistake an exiting request for a live reservation.
            lease_path.unlink(missing_ok=True)
            lease.close()


def checkpoint():
    slot = ACTIVE.get()
    if slot is None or time.monotonic() - slot['checked'] < 5:
        return
    if slot.get('oracle'):
        if slot['store'].allocated_bytes()>=slot['limit']:
            raise StorageCapacity('STORAGE_CAPACITY: Oracle 저장 예산으로 추가 실행을 중단합니다. 기록은 보존됩니다.')
        slot['checked']=time.monotonic()
        return
    # Do not prevent persisting an answer already received or a failure. Check
    # before dispatching another model/tool action, not inside the final write.
    roots = storage_roots(slot['root'])
    if sum(used_bytes(p) for p in roots) >= slot['limit'] or min(free_bytes(p) for p in roots) < slot['min_free']:
        raise StorageCapacity('STORAGE_CAPACITY: 저장 한도 도달로 추가 실행을 중단합니다. 기록은 보존됩니다.')
    slot['checked'] = time.monotonic()
