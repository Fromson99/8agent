"""Native API/contracts against the explicit isolated snapshot and its pins."""
from common import *
import sys,resource,pytest,os
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT))
sys.dont_write_bytecode=True
arm='candidate'
if '--baseline' in sys.argv:
 arm='baseline';sys.argv.remove('--baseline')
C=ROOT/read(ART/'stage.json')['root']
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND'),str(C/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
import lawrag.pipeline,lawrag.core
lawrag.pipeline.__path__.append(str(ROOT/'02_BACKEND/lawrag/pipeline'))
lawrag.core.__path__.append(str(ROOT/'02_BACKEND/lawrag/core'))
import lawrag.core.structure
lawrag.core.structure.__path__.append(str(ROOT/'02_BACKEND/lawrag/core/structure'))
import semantic_runtime.app as app_module
original=app_module.create_app
def create(*a,**kw):
 if Path(kw.get('contracts_root',ROOT)).resolve()==ROOT:kw['contracts_root']=C
 return original(*a,**kw)
app_module.create_app=create
import test_legal_agent_double_harness as fixture
fixture.ROOT=C
resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
assert str(C) in app_module.__file__
print('Candidate API module:',app_module.__file__,flush=True)
raise SystemExit(pytest.main(['-o','pythonpath=',*sys.argv[1:]]))
