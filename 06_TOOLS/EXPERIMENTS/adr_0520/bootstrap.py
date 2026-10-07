"""Load only the explicitly frozen ADR0520 candidate; never register it for serving."""
import hashlib
import json
import sys
from pathlib import Path
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0520-evidence-bound-relation-exploration'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0520/exploration'
def pin():
    revision=json.loads((C/'candidate.json').read_text())['revisions'][-1]
    for f in revision['files']:
        assert hashlib.sha256((R/f['frozen_path']).read_bytes()).hexdigest()==f['snapshot_sha256']
    snap=C/'revisions'/revision['revision_id']/'snapshot/02_BACKEND/semantic_runtime'
    sys.path.insert(0,str(R/'02_BACKEND'))
    import semantic_runtime
    semantic_runtime.__path__.insert(0,str(snap))
    import semantic_runtime.legal_agent
    semantic_runtime.legal_agent.__path__.insert(0,str(snap/'legal_agent'))
    return snap
if __name__=='__main__':
    pin()
    sys.path[:0]=[str(R/'05_TESTS'),str(R/'05_TESTS/CONTRACTS')]
    import pytest
    raise SystemExit(pytest.main(sys.argv[1:] or [str(Path(__file__).with_name('test_contract.py')),'-q']))
