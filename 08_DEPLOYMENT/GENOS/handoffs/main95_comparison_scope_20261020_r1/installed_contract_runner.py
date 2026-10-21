"""Exercise output/failure/API contracts against the installed full code only."""
import importlib,json,os,sys,tempfile,re
import pytest
from pathlib import Path
R=Path(__file__).resolve().parents[4];C=Path(sys.argv[1]).resolve();sys.dont_write_bytecode=True
# Contract fixtures own their isolated temporary stores; the separate real
# GENOS bootstrap check intentionally retains deployment environment settings.
for key in list(os.environ):
    if key.startswith(('GENOS_','ORACLE_','LLMOPS_','DP_')) or key in ('DP','AD_STORE_PATH'):
        os.environ.pop(key,None)
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS')]
sys.path[:0]=[str(R/'06_TOOLS/EXPERIMENTS/adr_0847'),str(R/'06_TOOLS/EXPERIMENTS/adr_0844'),str(R/'06_TOOLS/EXPERIMENTS/adr_0841'),str(R/'06_TOOLS/EXPERIMENTS/adr_0811')]
sys.path[:0]=[str(R/'06_TOOLS/EXPERIMENTS/adr_0936'),str(R/'06_TOOLS/EXPERIMENTS/adr_0930')]
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(C),LAWRAG_TOOL_WORKSPACE_ROOT=str(C),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_TEST_INSTALLED_TRANSPORT='1')
os.environ.update(WORKFLOW_TEST_CODE_ROOT=str(C),SOURCE_PROVIDER_PROJECT_ROOT=str(R),LAWRAG_TOKEN_TEST_REPOSITORY=str(R))
import semantic_runtime.app as app
original=app.create_app
def create(*args,**kw):
    if kw.get('contracts_root') is not None and Path(kw['contracts_root']).resolve()==R:kw['contracts_root']=C
    generation_value=args[1] if len(args)>1 else kw.get('generation')
    generation=Path(generation_value) if generation_value is not None else None
    if generation is not None and 'pytest-' in str(generation):
        from lawrag.pipeline.search_selection import plan,activate
        from semantic_runtime.search_selection import selection_path
        if not selection_path(generation).exists():activate(plan(generation,latest=True))
    return original(*args,**kw)
app.create_app=create
plugin=importlib.import_module('conftest')
sys.path[:0]=[str(C/'02_BACKEND'),str(C)]
import workflow
for row in json.loads((C/'00_SYSTEM/WORKSPACE.json').read_bytes())['roots']:
    (C/row['canonical_path']).mkdir(parents=True,exist_ok=True)
class InstalledTests:
    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(self,item):
        # Importing deployed service.py intentionally installs its field config.
        # A different synthetic test must not inherit that prior test's store.
        for key in list(os.environ):
            if key.startswith(('GENOS_','ORACLE_','LLMOPS_','DP_')) or key in ('DP','AD_STORE_PATH'):
                os.environ.pop(key,None)
        os.environ.update(AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_TEST_INSTALLED_TRANSPORT='1')

    def pytest_collection_modifyitems(self,items):
        # Pytest may prepend fixture folders; product imports must use this checkout.
        sys.path[:0]=[str(C/'02_BACKEND'),str(C)]
        # Imported fixture modules also load service.py. Point those at the
        # installed checkout; the standalone Dataiku cell remains a test asset.
        for name,module in list(sys.modules.items()):
            if name.startswith('test_') and name!='test_oracle_dp' and getattr(module,'ROOT',None)==R:
                module.ROOT=C
if __name__=='__main__':
    # The durable-review tests share module-scoped synthetic transports and fixtures.
    # Match the already verified MAIN runner's import identity; product modules
    # still must all resolve to C in the explicit check below.
    result=pytest.main(['-q','--import-mode=prepend','--tb=short','--show-capture=no','-o','pythonpath=','--noconftest',*sys.argv[2:]],plugins=[plugin,InstalledTests()])
    imports={name:str(Path(module.__file__).resolve()) for name,module in sys.modules.items()
             if (name.startswith(('semantic_runtime','workflow','lawrag')) or name in ('main','main_workflow','service')) and getattr(module,'__file__',None)}
    outside={n:p for n,p in imports.items() if not Path(p).is_relative_to(C)}
    assert not outside,outside
    print('INSTALLED_CONTRACT_IMPORTS PASS; modules='+str(len(imports)),flush=True)
    raise SystemExit(result)
