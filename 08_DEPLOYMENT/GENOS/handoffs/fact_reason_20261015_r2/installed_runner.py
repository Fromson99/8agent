"""Exercise installed recovery contracts; fixture builders alone use the workspace."""
from pathlib import Path
import importlib, json, os, sys
R=Path(__file__).resolve().parents[4];code=Path(sys.argv[1]).resolve()
sys.dont_write_bytecode=True
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(R),LAWRAG_TOOL_WORKSPACE_ROOT=str(R))
sys.path[:0]=[str(code/'02_BACKEND'),str(code),str(Path(__file__).resolve().parent),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS')]
for name in ('semantic_runtime','semantic_runtime.legal_agent.completion_contracts'):
    module=importlib.import_module(name)
    assert Path(module.__file__).resolve().is_relative_to(code),module.__file__
for name in ('lawrag','lawrag.pipeline'):
    module=importlib.import_module(name)
    module.__path__.append(str(R/'02_BACKEND'/name.replace('.','/')))
# Generation is a fixture builder, not shipped serving functionality. Build
# synthetic sources in a separate workspace process; runtime imports stay pinned.
import subprocess
fixture_builder=importlib.import_module('lawrag.pipeline.term_generation')
def build_synthetic(source,glossary,output,**kwargs):
    command="import json,sys;from lawrag.pipeline.term_generation import build_generation;args=json.loads(sys.argv[1]);build_generation(*args['paths'],**args['kwargs'])"
    environment={**os.environ,'PYTHONPATH':str(R/'02_BACKEND'),'LAWRAG_WORKSPACE_ROOT':str(R),'LAWRAG_TOOL_WORKSPACE_ROOT':str(R)}
    result=subprocess.run([str(R/'.venv/bin/python'),'-c',command,json.dumps({'paths':list(map(str,(source,glossary,output))),'kwargs':kwargs})],cwd=R,env=environment,text=True,capture_output=True,timeout=60)
    if result.returncode:raise RuntimeError('synthetic fixture builder failed: '+result.stdout+result.stderr)
    return json.loads((Path(output)/'result.json').read_bytes())
fixture_builder.build_generation=build_synthetic
plugin=importlib.import_module('conftest')
import pytest
from semantic_runtime.unit_fulltext import UnitFulltextIndex
@pytest.fixture
def prebuilt_unit_tree():
    generation=Path(os.environ['METRICS_TEST_GENERATION'])
    return generation,UnitFulltextIndex(Path(os.environ['METRICS_TEST_UNIT_INDEX']),json.loads((generation/'navigation/manifest.json').read_bytes()))
# Import only these contract suites before rebinding their declared ROOT.
for path in sys.argv[2:]:
    if path.endswith('.py'):
        importlib.import_module(Path(path).stem)
for name,module in list(sys.modules.items()):
    if name.startswith('test_') and getattr(module,'ROOT',None)==R:module.ROOT=code
result=pytest.main(['-q','--tb=short','--show-capture=no','-o','pythonpath=','--noconftest',*sys.argv[2:]],plugins=[plugin])
imports={name:str(Path(module.__file__).resolve()) for name,module in sys.modules.items() if name.startswith('semantic_runtime') and getattr(module,'__file__',None)}
assert all(Path(path).is_relative_to(code) for path in imports.values()),imports
print('INSTALLED_RUNTIME_IMPORTS PASS; modules='+str(len(imports))+'; '+str(code),flush=True)
raise SystemExit(result)
