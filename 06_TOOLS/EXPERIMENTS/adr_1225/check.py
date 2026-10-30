from common import *
import importlib,inspect,os,resource,time
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
mode,suite=sys.argv[1:3];tag=sys.argv[3] if len(sys.argv)>3 else 'first'
f=read(DES/'freeze.json');b=read(DES/'baseline.json');C=ROOT/(b['manifest']['code_root'] if mode=='baseline' else f['code_root'])
expected=b['manifest']['files'] if mode=='baseline' else f['files']
assert all(sha(C/n)==h for n,h in expected.items())
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT),WORKFLOW_TEST_CODE_ROOT=str(C),NEED_CONTINUITY_CONTRACT_ROOT=str(C),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0')
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for name in ('pipeline','core'):
 pkg=importlib.import_module('lawrag.'+name);pkg.__path__.append(str(ROOT/'02_BACKEND/lawrag'/name))
import conftest,pytest
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS'),str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1199')]
criteria=read(DES/'criteria.json')
criteria['fixture_hashes'].update(read(DES/'fixture-bindings.json'))
if (DES/'fixture-repair-binding.json').exists():criteria['fixture_hashes'].update(read(DES/'fixture-repair-binding.json'))
sys.path[:0]=[str(Path(__file__).parent),str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1219'),str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1221'),str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1223')]
paths=criteria['suites'][suite] if suite!='features-all' else criteria['suites']['core']+criteria['suites']['features']
for n in paths:assert sha(ROOT/n)==criteria['fixture_hashes'][n],n
for n in paths+['05_TESTS/CONTRACTS/test_legal_agent_v5.py','05_TESTS/CONTRACTS/test_source_span_norm.py','05_TESTS/CONTRACTS/test_assessment_source_reply.py','05_TESTS/CONTRACTS/test_unified_legal_agent.py']:
 module=importlib.import_module(Path(n).stem)
 if hasattr(module,'ROOT'):module.ROOT=C
class Results:
 def __init__(self):self.rows=[]
 def pytest_runtest_logreport(self,report):
  if report.when=='call' or report.failed:self.rows.append({'test':report.nodeid,'when':report.when,'status':report.outcome,'error':report.longreprtext if report.failed else None})
 @pytest.fixture(autouse=True)
 def bound_contract_root(self,monkeypatch):
  original=monkeypatch.setenv
  def setenv(name,value,*a,**kw):return original(name,str(C) if name=='WORKFLOW_TEST_CODE_ROOT' else value,*a,**kw)
  monkeypatch.setattr(monkeypatch,'setenv',setenv)
r=Results();started=time.monotonic();name=mode+'-'+suite+'-'+tag
runtime=ART/'test-runtime'/name;runtime.parent.mkdir(parents=True,exist_ok=True)
selection=sys.argv[4] if len(sys.argv)>4 else 'not actual007'
code=pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','--show-capture=no','-p','no:cacheprovider','--basetemp='+str(runtime),'-k',selection,*[str(ROOT/p) for p in paths]],plugins=[r,conftest])
leaks={n:str(m.__file__) for n,m in sys.modules.items() if n.startswith('semantic_runtime') and getattr(m,'__file__',None) and not Path(m.__file__).resolve().is_relative_to(C)}
result={'exit_code':int(code),'rows':r.rows,'passed':sum(x['status']=='passed' for x in r.rows),'failed':sum(x['status']=='failed' for x in r.rows),'seconds':time.monotonic()-started,'import_leaks':leaks,'external_model_calls':0,'fixed_files_unchanged':all(sha(C/n)==h for n,h in expected.items()),'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
put(ART/('checks-'+name+'.json'),result);print({k:v for k,v in result.items() if k!='rows'})
assert not leaks and result['fixed_files_unchanged']
raise SystemExit(int(code))
