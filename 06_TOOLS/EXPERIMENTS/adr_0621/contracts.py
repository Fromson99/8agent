"""Run frozen implementation with truthful candidate engine pins and spawn support."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
CODE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0621/bounded-unit/revisions/rev-001/snapshot'
sys.dont_write_bytecode=True
sys.path[:0]=[str(CODE/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS')]

def main():
    import test_unit_fulltext_adaptive_read
    import test_legal_agent_v5,test_unified_legal_agent
    contracts=ROOT/'04_EXPERIMENTS/ADR/ADR-0621-unit-read-canonical-boundaries/artifacts/research-code'
    for module in (test_legal_agent_v5,test_unified_legal_agent):module.ROOT=contracts
    import pytest
    return pytest.main(['-q','05_TESTS/CONTRACTS/test_unit_fulltext_adaptive_read.py',
        '05_TESTS/CONTRACTS/test_unit_read_canonical_boundaries.py',
        '05_TESTS/CONTRACTS/test_unified_legal_agent.py'])

if __name__=='__main__':raise SystemExit(main())
