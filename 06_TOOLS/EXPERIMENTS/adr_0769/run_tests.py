from pathlib import Path
import importlib, sys
R=Path(__file__).resolve().parents[3]
code=Path(sys.argv[1]).resolve()
sys.dont_write_bytecode=True
sys.path[:0]=[str(code/'02_BACKEND'),str(code),str(R/'05_TESTS'),str(code/'05_TESTS/CONTRACTS'),str(R/'05_TESTS/CONTRACTS')]
import semantic_runtime
assert Path(semantic_runtime.__file__).is_relative_to(code)
for name in ('lawrag','lawrag.pipeline'):
    p=importlib.import_module(name);p.__path__.append(str(R/'02_BACKEND'/name.replace('.','/')))
plugin=importlib.import_module('conftest')
for name in ('test_legal_agent_double_harness','test_genos_chat_flow','test_genos_reasoner_display'):
    importlib.import_module(name).ROOT=code
import pytest
raise SystemExit(pytest.main(['-q','--tb=short','--show-capture=no','-o','pythonpath=','--noconftest',*sys.argv[2:]],plugins=[plugin]))
