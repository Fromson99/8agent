from common import *
import sys,os,resource,time,importlib,inspect,pytest
sys.dont_write_bytecode=True
f=read(sorted(DES.glob('freeze-*.json'))[-1]);mode=sys.argv[1];C=ROOT/(read(DES/'baseline.json')['manifest']['code_root'] if mode=='baseline' else read(DES/'parent-freeze.json')['code_root'] if mode=='parent' else f['code_root']);T=Path(__file__).parent
if mode not in ('baseline','parent'):
 for n,h in f['files'].items():assert sha(C/n)==h,n
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT),WORKFLOW_TEST_CODE_ROOT=str(C),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0')
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS'),str(T)]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for name in ('pipeline','core'):
 pkg=importlib.import_module('lawrag.'+name);pkg.__path__.append(str(ROOT/'02_BACKEND/lawrag'/name))
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
import conftest
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(T),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS')]
import pytest
class Results:
 rows=[]
 def pytest_runtest_logreport(self,report):
  if report.when=='call' or report.failed:self.rows.append({'test':report.nodeid,'status':report.outcome,'error':report.longreprtext if report.failed else None})
(ART/'test-runtime').mkdir(exist_ok=True)
names=['test_navigation_scope_memory.py','test_initial_interpreted_scope.py','test_investigation_completion_adr0678.py','test_unattempted_gap_finish.py','test_completion_v4.py','test_source_span_norm.py','test_narrative_answer.py','test_token_answer_stream.py','test_navigation_input_compaction.py','test_nested_minimal_output.py']
for name in names:
 module=importlib.import_module(name[:-3])
 if hasattr(module,'ROOT'):module.ROOT=C
r=Results();started=time.monotonic();rc=pytest.main(['--noconftest','-c','/dev/null','--confcutdir='+str(T),'-q','--tb=short','-p','no:cacheprovider','--basetemp='+str(ART/'test-runtime'/('regression-'+mode+'-'+f.get('execution_id',f['candidate_revision']['revision_id']))),*[str(ROOT/'05_TESTS/CONTRACTS'/n) for n in names]],plugins=[r,conftest])
imports={n:str(Path(m.__file__).resolve()) for n,m in sys.modules.items() if n.startswith('semantic_runtime') and getattr(m,'__file__',None)}
leaks={n:p for n,p in imports.items() if not Path(p).is_relative_to(C)}
put(ART/('regression-'+mode+'-'+f.get('execution_id',f['candidate_revision']['revision_id'])+'.json'),{'returncode':int(rc),'rows':r.rows,'passed':sum(x['status']=='passed' for x in r.rows),'failed':sum(x['status']=='failed' for x in r.rows),'seconds':time.monotonic()-started,'import_leaks':leaks,'model_calls':0,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss});assert not leaks,leaks
raise SystemExit(int(rc))
