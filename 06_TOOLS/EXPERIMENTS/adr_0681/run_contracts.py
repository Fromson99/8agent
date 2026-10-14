"""Run synthetic contracts against one explicit serving inventory."""
from pathlib import Path
import sys,importlib
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parents[3]
code=Path(sys.argv[1]).resolve();files=sys.argv[2:]
sys.path[:0]=[str(code/'02_BACKEND'),str(code),str(R/'05_TESTS'),
             str(code/'05_TESTS/CONTRACTS'),str(R/'05_TESTS/CONTRACTS')]
import semantic_runtime
assert str(code) in semantic_runtime.__file__
for name in ('lawrag','lawrag.pipeline'):
 p=importlib.import_module(name);p.__path__.append(str(R/'02_BACKEND'/name.replace('.','/')))
plugin=importlib.import_module('conftest')
helper=importlib.import_module('test_legal_agent_double_harness');helper.ROOT=code
import pytest
raise SystemExit(pytest.main(['-q','--tb=short','--noconftest',*files],plugins=[plugin]))
