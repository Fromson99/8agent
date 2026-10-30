from pathlib import Path
import json,sys,os,resource,hashlib,importlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1108-genos-applied-mode-main';S=A/'artifacts/staged-code'
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(R),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0',WORKFLOW_TEST_CODE_ROOT=str(S))
resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3));sys.dont_write_bytecode=True
f=json.loads((A/'artifacts/design/staging.json').read_text())
assert all(hashlib.sha256((S/n).read_bytes()).hexdigest()==h for n,h in f['files'].items())
sys.path[:0]=[str(S),str(S/'02_BACKEND'),str(R/'02_BACKEND'),str(R/'05_TESTS/CONTRACTS')]
import lawrag
lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
import lawrag.pipeline
lawrag.pipeline.__path__.append(str(R/'02_BACKEND/lawrag/pipeline'))
import main
import pytest
class Roots:
 def pytest_collection_modifyitems(self,session,config,items):
  for name,m in list(sys.modules.items()):
   if name.startswith('test_') and getattr(m,'ROOT',None)==R:m.ROOT=S
 def pytest_sessionfinish(self,session,exitstatus):
  assert all(hashlib.sha256((S/n).read_bytes()).hexdigest()==h for n,h in f['files'].items())
args=sys.argv[1:] or ['05_TESTS/CONTRACTS/test_genos_applied_mode.py']
raise SystemExit(pytest.main(['-q','--tb=short',*args],plugins=[Roots()]))
