"""Explicit candidate bootstrap for ordinary contract tests."""
import sys
from pathlib import Path

if __name__ == '__main__':
    sys.dont_write_bytecode = True
    root = Path(__file__).resolve().parents[3]
    arm = sys.argv[1]
    sys.path[:0] = [str(root/'02_BACKEND'),str(root/'05_TESTS/CONTRACTS')]
    import semantic_runtime.legal_agent as package
    package.__path__.insert(0,str(root/'02_BACKEND/lawrag/research/candidates/adr_0558'/arm/
        'snapshot/02_BACKEND/semantic_runtime/legal_agent'))
    import pytest
    raise SystemExit(pytest.main(['-q','06_TOOLS/EXPERIMENTS/adr_0558/test_presentation.py',
        '05_TESTS/CONTRACTS/test_bounded_source_selection.py',
        '05_TESTS/CONTRACTS/test_legal_agent_v5_numbers.py',
        '05_TESTS/CONTRACTS/test_model_decision_repair.py',
        '--disable-warnings','--maxfail=2', *sys.argv[2:]]))
