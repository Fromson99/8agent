import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1090-compact-main-valid-oracle'
f=json.loads((ADR/'artifacts/design/freeze.json').read_text());code=ROOT/f['code_root']
for n,h in f['files'].items():assert hashlib.sha256((code/n).read_bytes()).hexdigest()==h,n
sys.path[:0]=[str(code/'02_BACKEND'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1086')]
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
paths=[str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1085/test_compact_v2.py'),str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1086/test_minimal_api.py')]
paths.extend(str(ROOT/'05_TESTS/CONTRACTS'/p) for p in ['test_navigation_input_compaction.py','test_read_judgment.py','test_read_judgment_keep_recovery.py'])
paths.extend(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1086'/p) for p in ['test_wire_binding.py','test_journal_sql.py'])
if '--api-only' in sys.argv:paths=[str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1086/test_minimal_api.py')]
if '--wire-only' in sys.argv:paths=[str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1086/test_wire_binding.py')]
rc=pytest.main([*paths,'--maxfail=1','-q','--tb=short','--junitxml='+str(ADR/'artifacts/secondary/contracts.xml')])
print('CANDIDATE',semantic_runtime.__file__)
sys.exit(rc)
