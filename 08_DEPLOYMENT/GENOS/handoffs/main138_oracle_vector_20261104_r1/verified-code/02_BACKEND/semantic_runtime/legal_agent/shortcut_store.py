"""An explicit store-generation pointer; no latest-directory selection."""
import json
from ..oracle_runtime_paths import Path
from .corrected_memory import MemoryError,digest


def selected_store(runtime):
    import os
    state=os.environ.get('GENOS_STATE_DIR')
    base=((Path(state) if state else Path(runtime))/'case-memory').resolve();pointer=base/'SHORTCUT_CURRENT.json'
    if not pointer.exists():return base/'cases-v4.sqlite'
    value=json.loads(pointer.read_text())
    if value.get('schema_version')!='shortcut-store-pointer-v1':raise MemoryError('unsupported shortcut store pointer')
    path=(base/value['path']).resolve()
    if not path.is_relative_to(base) or path.name!='cases-v4.sqlite' or not path.is_file():raise MemoryError('invalid shortcut store generation')
    if value.get('receipt_hash')!=digest(value['receipt']):raise MemoryError('store cutover receipt changed')
    return path


from contextlib import contextmanager
@contextmanager
def store_owner(runtime, *, exclusive=False):
    import fcntl
    base=selected_store(runtime).parent;base.mkdir(parents=True,exist_ok=True,mode=0o700)
    from ..oracle_runtime_paths import virtual, records
    if virtual(base):
        with records().shared_lease(['store-generation', str(base)], exclusive=exclusive):
            yield
        return
    with (base/'.store-owner').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:yield
        finally:fcntl.flock(lock,fcntl.LOCK_UN)
