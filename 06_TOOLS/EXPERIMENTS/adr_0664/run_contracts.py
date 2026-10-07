from pathlib import Path
import sys, importlib
root=Path(__file__).resolve().parents[3]
code=root/'02_BACKEND/lawrag/research/candidates/adr_0664/patch-repair/snapshot'
sys.path.insert(0,str(code/'02_BACKEND'));sys.path.insert(0,str(root/'05_TESTS/CONTRACTS'));sys.path.insert(0,str(code/'05_TESTS/CONTRACTS'));sys.path.insert(0,str(root/'05_TESTS'))
import semantic_runtime
assert str(code) in semantic_runtime.__file__
for name in ('lawrag','lawrag.pipeline'):
 package=importlib.import_module(name);package.__path__.append(str(root/'02_BACKEND'/name.replace('.','/')))
import pytest
files=['test_law_navigation_patch_repair_adr0664.py','test_law_navigation_one_repair_adr0663.py','test_search_question_boundary_adr0662.py','test_law_navigation_state_contract_adr0661.py','test_law_grouped_navigation.py']
raise SystemExit(pytest.main(['-q']+[str(code/'05_TESTS/CONTRACTS'/f) for f in files],plugins=[importlib.import_module('conftest')]))
