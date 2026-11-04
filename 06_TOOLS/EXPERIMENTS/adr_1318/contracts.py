"""Run small synthetic conversation contracts against frozen serving modules."""
from common import *
import os,importlib
C=ROOT/read(DES/'candidate-public.json')['code_root']
os.environ.update(LOOP_TEST_CODE_ROOT=str(C),PYTHONDONTWRITEBYTECODE='1',GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0',LAWRAG_WORKSPACE_ROOT=str(ROOT))
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(ROOT/'02_BACKEND'),str(ROOT)]
# Release bundles omit build-only fixture utilities. Add those as fallbacks;
# serving modules remain first and their origins are checked after pytest.
for name in ('lawrag','lawrag.pipeline','lawrag.core','lawrag.research'):
 module=importlib.import_module(name)
 fallback=str(ROOT/'02_BACKEND'/name.replace('.','/'))
 if fallback not in module.__path__:module.__path__.append(fallback)
import semantic_runtime,pytest
assert Path(semantic_runtime.__file__).resolve().is_relative_to(C)
rows=[]
class Recorder:
 def pytest_runtest_logreport(self,report):
  if report.when=='call' or report.failed:
   rows.append({'test':report.nodeid,'when':report.when,'outcome':report.outcome,'error':str(report.longrepr) if report.failed else None})
files=['test_multiturn_structured_scope.py','test_scoped_multiturn_api.py','test_genos_applied_mode.py','test_followup_structure_lookup.py']
code=pytest.main(['-q','-p','no:cacheprovider','-o','pythonpath=']+[str(ROOT/'05_TESTS/CONTRACTS'/f) for f in files],plugins=[Recorder()])
loaded={name:str(Path(mod.__file__).resolve()) for name,mod in sys.modules.items() if name.startswith('semantic_runtime') and getattr(mod,'__file__',None)}
assert all(Path(p).is_relative_to(C) for p in loaded.values()),loaded
put(ART/'contracts-frozen-result.json',{'exit_code':code,'rows':rows,'loaded_serving_modules':loaded,'serving_origin_checked':True,'model_calls':0})
raise SystemExit(code)
