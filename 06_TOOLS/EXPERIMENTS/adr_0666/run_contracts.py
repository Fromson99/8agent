from pathlib import Path
import sys, importlib
sys.dont_write_bytecode=True
root=Path(__file__).resolve().parents[3]
code=root/'02_BACKEND/lawrag/research/candidates/adr_0666/provider-closure/snapshot'
sys.path.insert(0,str(code/'02_BACKEND'));sys.path.insert(0,str(root/'05_TESTS/CONTRACTS'));sys.path.insert(0,str(code/'05_TESTS/CONTRACTS'));sys.path.insert(0,str(root/'05_TESTS'))
import semantic_runtime
assert str(code) in semantic_runtime.__file__
for name in ('lawrag','lawrag.pipeline'):
 package=importlib.import_module(name);package.__path__.append(str(root/'02_BACKEND'/name.replace('.','/')))
import pytest
files=['test_selection_tool_contracts_adr0665.py','test_search_question_boundary_adr0662.py','test_law_navigation_state_contract_adr0661.py','test_law_grouped_navigation.py']
raise SystemExit(pytest.main(['-q']+[str(code/'05_TESTS/CONTRACTS'/f) for f in files],plugins=[importlib.import_module('conftest')]))
