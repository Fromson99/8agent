from common import *
import os,time,resource,importlib,inspect
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
f=read(sorted(DES.glob('freeze-*.json'))[-1]);C=ROOT/f['code_root'];T=Path(__file__).parent
for n,h in f['files'].items():assert sha(C/n)==h,n
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT),WORKFLOW_TEST_CODE_ROOT=str(C),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0')
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS'),str(T)]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for name in ('pipeline','core'):
 pkg=importlib.import_module('lawrag.'+name);pkg.__path__.append(str(ROOT/'02_BACKEND/lawrag'/name))
import conftest,pytest
import test_legal_agent_v5
test_legal_agent_v5.ROOT=C
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(T),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS')]
class Results:
 rows=[]
 def pytest_runtest_logreport(self,report):
  if report.when=='call' or report.failed:self.rows.append({'test':report.nodeid,'when':report.when,'status':report.outcome,'error':report.longreprtext if report.failed else None})
r=Results();started=time.monotonic();rev=f['candidate_revision']['revision_id']
(ART/'test-runtime').mkdir(exist_ok=True)
paths=[str(T/'test_requirements.py'),str(T/'test_native.py'),str(ROOT/'05_TESTS/CONTRACTS/test_output_contract_recovery.py'),str(ROOT/'05_TESTS/CONTRACTS/test_nested_minimal_output.py')]
rc=pytest.main(['--noconftest','-c','/dev/null','--confcutdir='+str(T),'-q','--tb=short','-p','no:cacheprovider','--basetemp='+str(ART/'test-runtime'/rev),*paths],plugins=[r,conftest])
leaks={n:str(m.__file__) for n,m in sys.modules.items() if n.startswith('semantic_runtime') and getattr(m,'__file__',None) and not Path(m.__file__).resolve().is_relative_to(C)}
put(ART/('check-'+rev+'.json'),{'returncode':int(rc),'rows':r.rows,'passed':sum(x['status']=='passed' for x in r.rows),'failed':sum(x['status']=='failed' for x in r.rows),'seconds':time.monotonic()-started,'import_leaks':leaks,'external_model_calls':0,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
assert not leaks,leaks
raise SystemExit(int(rc))
