"""Load only the hash-verified frozen candidate; run offline implementation contracts."""
import sys,json,hashlib
from pathlib import Path
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0501-gemma-question-obligation-wiring'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0501/obligations'
def pin():
    design=json.loads((A/'artifacts/frozen-contracts.json').read_text())
    for path,sha in design['files'].items():
        if hashlib.sha256((R/path).read_bytes()).hexdigest()!=sha:raise RuntimeError('Contract input drift: '+path)
    manifest=json.loads((C/'candidate.json').read_text())
    rev=next(r for r in manifest['revisions'] if r['revision_id']==design['revision_id'])
    for row in rev['files']:
        if hashlib.sha256((R/row['frozen_path']).read_bytes()).hexdigest()!=row['snapshot_sha256']:raise RuntimeError('Candidate drift')
    frozen=C/'revisions'/rev['revision_id']/'snapshot/02_BACKEND'
    runtime=R/'04_EXPERIMENTS/ADR/ADR-0498-gemma4-fp8-compatible-schema-cm51-fsc10/artifacts/sealed-runtime/02_BACKEND'
    sys.path[:0]=[str(frozen),str(runtime),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS'),str(Path(__file__).parent)]
    import semantic_runtime,lawrag.research
    assert Path(semantic_runtime.__file__).is_relative_to(frozen)
    lawrag.research.__path__.insert(0,str(frozen/'lawrag/research'))
    return design
if __name__=='__main__':
    pin()
    import pytest
    targets=sys.argv[1:] or [str(Path(__file__).with_name('test_obligations.py')),str(R/'06_TOOLS/EXPERIMENTS/adr_0498/test_workflow.py')]
    raise SystemExit(pytest.main(['-q','-p','no:cacheprovider',*targets]))
