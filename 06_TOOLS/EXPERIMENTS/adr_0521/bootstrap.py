import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'02_BACKEND'))
from lawrag.platform.workspace import discover_root
R=discover_root()
A=R/'04_EXPERIMENTS/ADR/ADR-0521-shared-reference-root-workflow'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0521/integrated'
def pin():
    revision=json.loads((C/'candidate.json').read_text())['revisions'][-1]
    for f in revision['files']:
        assert hashlib.sha256((R/f['frozen_path']).read_bytes()).hexdigest()==f['snapshot_sha256']
    snap=C/'revisions'/revision['revision_id']/'snapshot/02_BACKEND/semantic_runtime'
    import semantic_runtime
    semantic_runtime.__path__.insert(0,str(snap))
    import semantic_runtime.legal_agent
    semantic_runtime.legal_agent.__path__.insert(0,str(snap/'legal_agent'))
    import lawrag.pipeline
    lawrag.pipeline.__path__.insert(0,str(snap.parent/"lawrag/pipeline"))
    return snap
if __name__=='__main__':
    pin();sys.path[:0]=[str(R/'05_TESTS'),str(R/'05_TESTS/CONTRACTS'),str(R/'06_TOOLS/EXPERIMENTS/adr_0520')]
    import pytest,fixture_migration
    raise SystemExit(pytest.main(sys.argv[1:] or [str(Path(__file__).with_name('test_integrated.py')),'-q'],plugins=[fixture_migration]))
