"""Exercise installed recovery contracts; fixture builders alone use the workspace."""
from pathlib import Path
import importlib, json, os, sys
R=Path(__file__).resolve().parents[4];code=Path(sys.argv[1]).resolve()
sys.dont_write_bytecode=True
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(R),LAWRAG_TOOL_WORKSPACE_ROOT=str(R))
sys.path[:0]=[str(code/'02_BACKEND'),str(code),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS')]
for name in ('semantic_runtime','semantic_runtime.legal_agent.investigation_scope','semantic_runtime.legal_agent.output_contract','semantic_runtime.legal_agent.law_navigation','semantic_runtime.legal_agent.case_repository'):
    module=importlib.import_module(name)
    assert Path(module.__file__).resolve().is_relative_to(code),module.__file__
for name in ('lawrag','lawrag.pipeline'):
    module=importlib.import_module(name)
    module.__path__.append(str(R/'02_BACKEND'/name.replace('.','/')))
plugin=importlib.import_module('conftest')
import pytest
from semantic_runtime.unit_fulltext import UnitFulltextIndex
@pytest.fixture
def prebuilt_unit_tree():
    generation=Path(os.environ['METRICS_TEST_GENERATION'])
    return generation,UnitFulltextIndex(Path(os.environ['METRICS_TEST_UNIT_INDEX']),json.loads((generation/'navigation/manifest.json').read_bytes()))
for name in ('test_focused_input_modality','test_investigation_scope_recovery','test_output_contract_recovery'):
    module=importlib.import_module(name);module.tree=prebuilt_unit_tree
for name,module in list(sys.modules.items()):
    if name.startswith('test_') and getattr(module,'ROOT',None)==R:module.ROOT=code
result=pytest.main(['-q','--tb=short','--show-capture=no','-o','pythonpath=','--noconftest',*sys.argv[2:]],plugins=[plugin])
imports={name:str(Path(module.__file__).resolve()) for name,module in sys.modules.items() if name.startswith('semantic_runtime') and getattr(module,'__file__',None)}
assert all(Path(path).is_relative_to(code) for path in imports.values()),imports
print('INSTALLED_RUNTIME_IMPORTS PASS; modules='+str(len(imports))+'; '+str(code),flush=True)
raise SystemExit(result)
