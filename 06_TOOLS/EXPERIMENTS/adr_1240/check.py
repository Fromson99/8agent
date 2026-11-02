from common import *
import os,time,importlib,resource,inspect
mode=sys.argv[1] if len(sys.argv)>1 else 'candidate';tag=sys.argv[2] if len(sys.argv)>2 else mode
b=read(DES/'baseline.json')
C=ROOT/b['manifest']['code_root'] if mode=='baseline' else ROOT/read(DES/'freeze.json')['code_root']
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT),WORKFLOW_TEST_CODE_ROOT=str(C),NEED_CONTINUITY_CONTRACT_ROOT=str(C),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0')
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for n in ('pipeline','core'):
 p=importlib.import_module('lawrag.'+n);p.__path__.append(str(ROOT/'02_BACKEND/lawrag'/n))
import conftest,pytest
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(Path(__file__).parent),str(ROOT/'05_TESTS/CONTRACTS')]
class Results:
 def __init__(self):self.rows=[]
 def pytest_collection_modifyitems(self,items):
  # Legacy fixtures hard-code the workspace; bind their contract root to the
  # same frozen code imported in this process. Product validation stays intact.
  for name in ('test_legal_agent_double_harness','test_legal_agent_v5','test_judgment_loop_recovery'):
   module=sys.modules.get(name)
   if module is not None:module.ROOT=C
 def pytest_runtest_logreport(self,report):
  r=report
  if r.when=='call' or r.failed:self.rows.append({'test':r.nodeid,'status':r.outcome,'error':r.longreprtext if r.failed else None})
r=Results();t=time.monotonic();(ART/'test-runtime').mkdir(exist_ok=True)
paths=[str(Path(__file__).parent/'test_ports.py'),str(Path(__file__).parent/'test_gold_rewrite.py')]
if len(sys.argv)<4 or sys.argv[3]!='new-only':
 paths += [str(ROOT/'05_TESTS/CONTRACTS'/n) for n in ('test_initial_interpreted_scope.py','test_multiturn_structured_scope.py','test_fulltext_ranking.py','test_unit_fulltext_adaptive_read.py','test_oracle_query_catalog.py','test_oracle_query.py')]
selection=os.environ.get('CHECK_SELECTION','')
if os.environ.get('CHECK_RECHECK_FROM'):
 prior=read(ART/os.environ['CHECK_RECHECK_FROM'])
 selection=' or '.join(sorted({r['test'].split('::')[-1].split('[')[0] for r in prior['rows'] if r['status']=='failed'}))
code=pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','--show-capture=no','-p','no:cacheprovider','--basetemp='+str(ART/'test-runtime'/tag),'-k',selection,*paths],plugins=[r,conftest])
put(ART/('checks-'+tag+'.json'),{'rows':r.rows,'exit_code':int(code),'seconds':time.monotonic()-t,'passed':sum(x['status']=='passed' for x in r.rows),'failed':sum(x['status']=='failed' for x in r.rows),'external_model_calls':0,'code_root':str(C.relative_to(ROOT))})
raise SystemExit(int(code))
