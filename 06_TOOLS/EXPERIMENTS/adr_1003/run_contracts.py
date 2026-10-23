"""Native API/contracts against the explicit isolated snapshot and its pins."""
from common import *
import sys,resource,pytest
sys.dont_write_bytecode=True
arm='candidate'
if '--baseline' in sys.argv:
 arm='baseline';sys.argv.remove('--baseline')
C=ROOT/read(ART/'stage.json')['roots'][arm]
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
raise SystemExit(pytest.main(sys.argv[1:]))
