from pathlib import Path
import importlib,os,sys,json,hashlib
R=Path(__file__).resolve().parents[3];code=Path(sys.argv[1]).resolve();sys.dont_write_bytecode=True
os.environ.update(SOURCE_PROVIDER_PROJECT_ROOT=str(R),LAWRAG_WORKSPACE_ROOT=str(R),LAWRAG_TOOL_WORKSPACE_ROOT=str(R),LAWRAG_TOKEN_TEST_REPOSITORY=str(R))
sys.path[:0]=[str(code/'02_BACKEND'),str(code),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS'),str(R/'02_BACKEND')]
import semantic_runtime
assert Path(semantic_runtime.__file__).is_relative_to(code)
for name in ('lawrag','lawrag.pipeline','lawrag.core','lawrag.core.structure'):
 module=importlib.import_module(name);module.__path__.insert(0,str(code/'02_BACKEND'/name.replace('.','/')));module.__path__.append(str(R/'02_BACKEND'/name.replace('.','/')))
# Older tests use their repository ROOT as a configuration path. Bind that
# configuration to the selected arm too; fixtures and raw test data stay local.
import semantic_runtime.app as app_module
original_create_app=app_module.create_app
def pinned_create_app(*args,**kwargs):
    if kwargs.get('contracts_root') is not None and Path(kwargs['contracts_root']).resolve()==R:
        kwargs['contracts_root']=code
    return original_create_app(*args,**kwargs)
app_module.create_app=pinned_create_app
plugin=importlib.import_module('conftest')
import pytest
class SelectedFixtureRoots:
    """Legacy materializers must copy the tested arm's config and engine pins."""
    @pytest.hookimpl(tryfirst=True,hookwrapper=True)
    def pytest_runtest_setup(self,item):
        names={'test_related_originals_reach_shared_assessment_after_confirmation',
               'test_pipeline_cli_uses_coordinator_and_finishes_journal'}
        if item.name in names:
            module=(importlib.import_module('test_legal_agent_double_harness')
                    if item.name=='test_related_originals_reach_shared_assessment_after_confirmation' else item.module)
            item._arm_root_module=module
            item._original_arm_root=module.ROOT
            module.ROOT=code
        yield
    def pytest_runtest_teardown(self,item):
        if hasattr(item,'_original_arm_root'):
            item._arm_root_module.ROOT=item._original_arm_root
result=pytest.main(['-q','--import-mode=importlib','--tb=short','--show-capture=no','-o','pythonpath=','--noconftest',*sys.argv[2:]],plugins=[plugin,SelectedFixtureRoots()])
paths={n:str(Path(m.__file__).resolve()) for n,m in list(sys.modules.items()) if n.startswith('semantic_runtime') and getattr(m,'__file__',None)}
assert all(Path(p).is_relative_to(code) for p in paths.values()),paths
Path(os.environ['ADR_IMPORT_RECEIPT']).write_text(json.dumps(paths,indent=2)+'\n')
raise SystemExit(result)
