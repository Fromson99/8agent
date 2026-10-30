"""Bound read-only adapter added to the existing compute service."""
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from lawrag.pipeline.oracle_existing_nfs import Snapshot
import transport as t

GENERATION = '/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation'
_snapshot = None
_guard = threading.Lock()


def handle(data):
    global _snapshot
    code = t.sha(ROOT / 'CODE_PINS.json')
    if data.get('code_sha256') != code:
        raise ValueError('NFS_CODE_MISMATCH')
    with _guard:
        if _snapshot is None:
            import worker
            worker.verify_code(ROOT)
            _snapshot = Snapshot(GENERATION, code)
        source = _snapshot
    # Source changes are errors; never silently rebind an active transfer.
    if data['API_TYPE'] == 'EXISTING_NFS_INFO':
        source.check()
        return source.info
    if data['API_TYPE'] == 'EXISTING_NFS_READ':
        return source.read(data.get('snapshot_sha256'), data.get('file'), data.get('offset'))
    raise ValueError('NFS_OPERATION')
