from pathlib import Path
import sys,resource,os,json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1037-uncapped-judgment-live-question/artifacts'
C=R/json.loads((A/'stage.json').read_text())['root']
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(R),LAWRAG_TOOL_WORKSPACE_ROOT=str(R),OUTPUT_LIMIT_TEST_CODE_ROOT=str(C))
sys.dont_write_bytecode=True
sys.path[:0]=[str(C/'02_BACKEND'),str(R/'02_BACKEND'),str(R/'05_TESTS'),str(R/'05_TESTS/CONTRACTS')]
import lawrag
lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
import lawrag.pipeline,lawrag.core
lawrag.pipeline.__path__.append(str(R/'02_BACKEND/lawrag/pipeline'))
lawrag.core.__path__.append(str(R/'02_BACKEND/lawrag/core'))
import lawrag.core.structure
lawrag.core.structure.__path__.append(str(R/'02_BACKEND/lawrag/core/structure'))
import semantic_runtime.app as app_module
original=app_module.create_app
def create(*a,**kw):
 if Path(kw.get('contracts_root',R)).resolve()==R:kw['contracts_root']=C
 return original(*a,**kw)
app_module.create_app=create
import test_legal_agent_double_harness as fixture
fixture.ROOT=C
resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
assert Path(app_module.__file__).is_relative_to(C)
print('Runtime module:',app_module.__file__,flush=True)
import pytest
raise SystemExit(pytest.main(['-o','pythonpath=',*sys.argv[1:]]))
