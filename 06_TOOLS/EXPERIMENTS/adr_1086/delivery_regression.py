import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1086-compact-wire-binding'
f=json.loads((ADR/'artifacts/design/freeze.json').read_text());code=ROOT/f['code_root']
for n,h in f['files'].items():assert hashlib.sha256((code/n).read_bytes()).hexdigest()==h,n
sys.path[:0]=[str(code/'02_BACKEND'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import semantic_runtime,lawrag,lawrag.core,lawrag.pipeline
for pkg,rel in [(lawrag,'lawrag'),(lawrag.core,'lawrag/core'),(lawrag.pipeline,'lawrag/pipeline')]:pkg.__path__.append(str(ROOT/'02_BACKEND'/rel))
import semantic_runtime.app as app
create=app.create_app
def candidate_app(*a,**kw):
 kw['contracts_root']=code
 kw.setdefault('workspace_root',ROOT)
 return create(*a,**kw)
app.create_app=candidate_app
import pytest
paths=[str(ROOT/'05_TESTS/CONTRACTS/test_navigation_delivery_recovery.py')]
rc=pytest.main([*paths,'-q','--tb=short','--junitxml='+str(ADR/'artifacts/run-001/contracts.xml')])
print('CANDIDATE',semantic_runtime.__file__)
sys.exit(rc)
