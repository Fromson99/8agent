"""Remaining feature verification, isolated from paid ON/OFF measurements."""
from common import *
import os,asyncio,inspect,importlib,time
C=ROOT/read(DES/'candidate.json')['code_root'];out=ART/'supplement';out.mkdir(exist_ok=False)
os.environ.update(LOOP_TEST_CODE_ROOT=str(C),WORKFLOW_TEST_CODE_ROOT=str(C),OPEN_ROUTER='synthetic-disabled-no-model',AD_WORKER_ENABLED='0',GENOS_RUNTIME_DIR=str(out/'runtime'))
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(ROOT),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1274')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for name in ('pipeline','core'):
 p=importlib.import_module('lawrag.'+name);p.__path__.append(str(ROOT/'02_BACKEND/lawrag'/name))
import conftest,pytest
sys.path[:0]=[str(C/'02_BACKEND'),str(C)]
reports=[]
class Results:
 def pytest_collection_modifyitems(self,session,config,items):
  # A production fixture may select the release root; historical input paths stay in ROOT.
  for name in ('test_internal_concept_comparison','concept_general_fixture'):
   m=sys.modules.get(name)
   if m is not None and getattr(m,'ROOT',None)==ROOT:m.ROOT=C
 def pytest_runtest_logreport(self,report):
  if report.when=='call' or report.failed or report.skipped:reports.append({'test':report.nodeid,'phase':report.when,'outcome':report.outcome,'error':report.longreprtext if report.failed else None})
tests=[str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1274/test_recovery.py')+'::test_exhausted_review_delivers_sources_then_fact_followup_in_same_case',
 str(ROOT/'05_TESTS/CONTRACTS/test_multiturn_structured_scope.py')+'::test_followup_scope_keep_replace_add_clear_and_no_cross_document_inheritance',
 str(ROOT/'05_TESTS/CONTRACTS/test_multiturn_structured_scope.py')+'::test_failed_first_question_can_change_query_keep_scope_and_restore',str(Path(__file__).with_name('test_display_supplement.py'))]
start=time.monotonic()
rc=pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','--rootdir='+str(ROOT),'-p','no:cacheprovider','--basetemp='+str(out/'pytest'),*tests],plugins=[conftest,Results()])
origins={n:str(Path(m.__file__).resolve()) for n,m in sys.modules.items() if n.startswith(('semantic_runtime','workflow.')) and getattr(m,'__file__',None)}
result={'exit_code':int(rc),'reports':reports,'passed':sum(r['outcome']=='passed' for r in reports),'failed':sum(r['outcome']=='failed' for r in reports),'seconds':time.monotonic()-start,'external_model_calls':0,'evidence_level':'synthetic fixture/real native API; not natural model quality','origins':origins,'all_candidate':all(Path(p).is_relative_to(C) for p in origins.values())}
put(out/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('reports','origins')},ensure_ascii=False));raise SystemExit(int(rc))
