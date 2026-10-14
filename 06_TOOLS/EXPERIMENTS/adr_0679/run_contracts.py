"""Ordinary synthetic contracts, no model/evaluation call."""
from pathlib import Path
import sys,importlib
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_0679/integrated/snapshot'
sys.path[:0]=[str(S/'02_BACKEND'),str(R/'05_TESTS'),str(S/'05_TESTS/CONTRACTS'),str(R/'05_TESTS/CONTRACTS')]
import semantic_runtime
assert str(S) in semantic_runtime.__file__
for name in ('lawrag','lawrag.pipeline'):
 p=importlib.import_module(name);p.__path__.append(str(R/'02_BACKEND'/name.replace('.','/')))
import pytest
extra=sys.argv[1:]
files=extra or [str(S/'05_TESTS/CONTRACTS/test_investigation_completion_adr0678.py')]
raise SystemExit(pytest.main(['-q','--tb=short',*files],plugins=[importlib.import_module('conftest')]))
