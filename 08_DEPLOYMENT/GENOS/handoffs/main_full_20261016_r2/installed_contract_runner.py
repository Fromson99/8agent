"""Exercise output/failure/API contracts against the installed full code only."""
import importlib,json,os,sys
from pathlib import Path
R=Path(__file__).resolve().parents[4];C=Path(sys.argv[1]).resolve();sys.dont_write_bytecode=True
# Contract fixtures own their isolated temporary stores; the separate real
# GENOS bootstrap check intentionally retains deployment environment settings.
for key in ('GENOS_RUNTIME_DIR','GENOS_DATA_ROOT','GENOS_GENERATION','GENOS_STATE_DIR','AD_STORE_PATH'):
    os.environ.pop(key,None)
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS')]
sys.path[:0]=[str(R/'06_TOOLS/EXPERIMENTS/adr_0844'),str(R/'06_TOOLS/EXPERIMENTS/adr_0841'),str(R/'06_TOOLS/EXPERIMENTS/adr_0811')]
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(C),LAWRAG_TOOL_WORKSPACE_ROOT=str(C),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0')
os.environ.update(WORKFLOW_TEST_CODE_ROOT=str(C),SOURCE_PROVIDER_PROJECT_ROOT=str(R),LAWRAG_TOKEN_TEST_REPOSITORY=str(R))
import semantic_runtime.app as app
original=app.create_app
def create(*args,**kw):
    if kw.get('contracts_root') is not None and Path(kw['contracts_root']).resolve()==R:kw['contracts_root']=C
    generation=Path(args[1] if len(args)>1 else kw['generation'])
    if 'pytest-' in str(generation):
        from lawrag.pipeline.search_selection import plan,activate
        from semantic_runtime.search_selection import selection_path
        if not selection_path(generation).exists():activate(plan(generation,latest=True))
    return original(*args,**kw)
app.create_app=create
plugin=importlib.import_module('conftest')
class InstalledTests:
    def pytest_collection_modifyitems(self,items):
        for item in items:
            module=item.module
            if getattr(module,'ROOT',None)==R:module.ROOT=C
import pytest
result=pytest.main(['-q','--tb=short','--show-capture=no','-o','pythonpath=','--noconftest',*sys.argv[2:]],plugins=[plugin,InstalledTests()])
imports={name:str(Path(module.__file__).resolve()) for name,module in sys.modules.items()
         if name.startswith(('semantic_runtime','workflow','lawrag')) and getattr(module,'__file__',None)}
assert all(Path(path).is_relative_to(C) for path in imports.values()),imports
print('INSTALLED_CONTRACT_IMPORTS PASS; modules='+str(len(imports)),flush=True)
raise SystemExit(result)
