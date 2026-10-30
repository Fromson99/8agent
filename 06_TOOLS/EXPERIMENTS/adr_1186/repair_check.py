from common import *
import sys,os,resource,time,importlib,inspect,pytest
sys.dont_write_bytecode=True
f=read(DES/'freeze.json');C=ROOT/f['code_root'];T=Path(__file__).parent
for n,h in f['files'].items():assert sha(C/n)==h,n
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT),WORKFLOW_TEST_CODE_ROOT=str(C),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0')
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS'),str(T)]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for name in ('pipeline','core'):
 pkg=importlib.import_module('lawrag.'+name);pkg.__path__.append(str(ROOT/'02_BACKEND/lawrag'/name))
import conftest
import test_legal_agent_v5
test_legal_agent_v5.ROOT=C
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(T),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS')]
import pytest
class Results:
 rows=[]
 def pytest_runtest_logreport(self,report):
  if report.when=='call' or report.failed:self.rows.append({'test':report.nodeid,'status':report.outcome,'error':report.longreprtext if report.failed else None})
(ART/'test-runtime').mkdir(exist_ok=True)
r=Results();started=time.monotonic()
selected=[str(T/'test_scope_completion.py')+'::test_saved007_false_finish_cannot_skip_actual_heading_sources']
rc=pytest.main(['--noconftest','-c','/dev/null','--confcutdir='+str(T),'-q','--tb=short','-p','no:cacheprovider',*selected],plugins=[r,conftest])
prior_path=ART/'check-rev-001.json';prior=read(prior_path);updates={x['test']:x for x in r.rows};assert len(updates)==1
rows=[updates.get(x['test'],x) for x in prior['rows']]
imports={n:str(Path(m.__file__).resolve()) for n,m in sys.modules.items() if n.startswith('semantic_runtime') and getattr(m,'__file__',None)};leaks={n:p for n,p in imports.items() if not Path(p).is_relative_to(C)}
put(ART/'technical-final.json',{'returncode':int(rc),'rows':rows,'passed':sum(x['status']=='passed' for x in rows),'failed':sum(x['status']=='failed' for x in rows),'seconds':time.monotonic()-started,'import_leaks':leaks,'model_calls':0,'inherited_from':{'path':str(prior_path.relative_to(ROOT)),'sha256':sha(prior_path),'same_product_files':len(f['files']),'inherited_passes':307,'rerun_checks':1,'reason':'Historical replay evaluator reference omitted from new runner setup; copied exact parent reference, same frozen466 product. No model calls.'}})
assert not leaks
raise SystemExit(int(rc))
