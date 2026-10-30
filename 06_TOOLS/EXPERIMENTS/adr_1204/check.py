from common import *
import os,resource,importlib,time,inspect
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
mode, suite=sys.argv[1:3]
attempt=sys.argv[3] if len(sys.argv)>3 else 'final'
(ART/'test-runtime').mkdir(parents=True,exist_ok=True)
b=read(DES/'baseline.json');f=read(DES/'freeze.json')
C=ROOT/(b['manifest']['code_root'] if mode=='baseline' else f['code_root']) if mode!='working' else ROOT
files=b['manifest']['files'] if mode=='baseline' else f['files']
if mode!='working':
 for n,h in files.items():assert sha(C/n)==h,n
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT),WORKFLOW_TEST_CODE_ROOT=str(C),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0')
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for name in ('pipeline','core'):
 pkg=importlib.import_module('lawrag.'+name);pkg.__path__.append(str(ROOT/'02_BACKEND/lawrag'/name))
import conftest,pytest,test_legal_agent_v5
test_legal_agent_v5.ROOT=C
sys.path[:0]=[str(C),str(C/'02_BACKEND')]
class Results:
 rows=[]
 def pytest_runtest_logreport(self,report):
  if report.when=='call' or report.failed:self.rows.append({'test':report.nodeid,'when':report.when,'status':report.outcome,'error':report.longreprtext if report.failed else None})
r=Results();started=time.monotonic()
criteria=read(DES/'criteria.json')
for path,h in criteria['fixture_hashes'].items():assert sha(ROOT/path)==h,path
paths=[str(ROOT/p) for p in criteria['suites'][suite]]
rc=pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','-p','no:cacheprovider','--basetemp='+str(ART/'test-runtime'/(mode+'-'+suite+'-'+attempt)),*paths],plugins=[r,conftest])
leaks={n:str(m.__file__) for n,m in sys.modules.items() if n.startswith('semantic_runtime') and getattr(m,'__file__',None) and not Path(m.__file__).resolve().is_relative_to(C)}
from semantic_runtime.chat_adapter import views
assert Path(views().__file__).resolve()==C/PRODUCT
put(ART/('checks-'+mode+'-'+suite+'-'+attempt+'.json'),{'returncode':int(rc),'rows':r.rows,'passed':sum(x['status']=='passed' for x in r.rows),'failed':sum(x['status']=='failed' for x in r.rows),'seconds':time.monotonic()-started,'import_leaks':leaks,'source_sha256':sha(C/PRODUCT),'external_model_calls':0,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
assert not leaks,leaks
raise SystemExit(int(rc))
