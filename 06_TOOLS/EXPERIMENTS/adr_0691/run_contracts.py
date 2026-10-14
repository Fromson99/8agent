"""Tests use one explicit code root, with ordinary synthetic fixture helpers."""
from pathlib import Path
import sys, importlib
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parents[3]
code=Path(sys.argv[1]).resolve()
sys.path[:0]=[str(code/'02_BACKEND'),str(code),str(R/'05_TESTS'),
             str(code/'05_TESTS/CONTRACTS'),str(R/'05_TESTS/CONTRACTS'),str(Path(__file__).parent)]
import semantic_runtime
assert Path(semantic_runtime.__file__).is_relative_to(code)
for name in ('lawrag','lawrag.pipeline'):
 p=importlib.import_module(name)
 fixture=R/'04_EXPERIMENTS/ADR/ADR-0689-judgment-loop-review-repair/artifacts/fixture-code/02_BACKEND'
 p.__path__.append(str(fixture/name.replace('.','/')))
plugin=importlib.import_module('conftest')
for name in ('test_legal_agent_double_harness','test_genos_chat_flow','test_genos_reasoner_display'):
 importlib.import_module(name).ROOT=code
import pytest
raise SystemExit(pytest.main(['-q','--tb=short','--noconftest',*sys.argv[2:]],plugins=[plugin]))
