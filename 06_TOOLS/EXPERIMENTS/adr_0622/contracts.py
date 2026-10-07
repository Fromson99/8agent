"""Saved guarded candidate test entrypoint supports spawned source builds."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
CODE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0622/batch-reference/snapshot'
if '--frozen' in sys.argv:CODE=CODE.parent/'revisions/rev-001/snapshot'
sys.dont_write_bytecode=True
sys.path[:0]=[str(CODE/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS')]
def main():
    import test_unit_fulltext_adaptive_read,test_batch_reference_navigation
    import test_legal_agent_v5,test_unified_legal_agent
    import importlib.util
    spec=importlib.util.spec_from_file_location('research_packager',ROOT/'06_TOOLS/EXPERIMENTS/adr_0622/package.py')
    package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
    target=ROOT/'04_EXPERIMENTS/ADR/ADR-0622-batch-reference-navigation/artifacts/research-code'
    if not target.exists():package.materialize(CODE,target)
    for module in (test_legal_agent_v5,test_unified_legal_agent):module.ROOT=target
    import pytest
    return pytest.main(['-q','05_TESTS/CONTRACTS/test_unit_fulltext_adaptive_read.py',
        '05_TESTS/CONTRACTS/test_unit_read_canonical_boundaries.py',
        '05_TESTS/CONTRACTS/test_batch_reference_navigation.py',
        '05_TESTS/CONTRACTS/test_unified_legal_agent.py'])
if __name__=='__main__':raise SystemExit(main())
