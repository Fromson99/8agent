"""Deterministic contracts against isolated candidate; each invocation is small."""
from common import *
import sys,resource,inspect,pytest
sys.dont_write_bytecode=True
code=ROOT/read(ART/'stage.json')['roots']['candidate']
sys.path[:0]=[str(code/'02_BACKEND'),str(ROOT/'02_BACKEND'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import lawrag,lawrag.pipeline
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'));lawrag.pipeline.__path__.append(str(ROOT/'02_BACKEND/lawrag/pipeline'))
import semantic_runtime.app as app_module
original=app_module.create_app
def create(*args,**kwargs):
 if Path(kwargs.get('contracts_root',ROOT)).resolve()==ROOT:kwargs['contracts_root']=code
 return original(*args,**kwargs)
app_module.create_app=create
import test_legal_agent_double_harness as fixture
fixture.ROOT=code
resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
raise SystemExit(pytest.main(sys.argv[1:]))
