from pathlib import Path
import sys,os,json,time,resource,importlib,inspect
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1227-source-first-authoring-semantics';ART=ADR/'artifacts'
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1227/source-first/snapshot'
if (ART/'design/freeze.json').exists():C=ROOT/json.loads((ART/'design/freeze.json').read_text())['code_root']
if (ART/'design/freeze-current.json').exists():C=ROOT/json.loads((ART/'design/freeze-current.json').read_text())['code_root']
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT),WORKFLOW_TEST_CODE_ROOT=str(C),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0')
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for name in ('pipeline','core'):
 p=importlib.import_module('lawrag.'+name);p.__path__.append(str(ROOT/'02_BACKEND/lawrag'/name))
import conftest,pytest
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(Path(__file__).parent),str(ROOT/'05_TESTS/CONTRACTS')]
import test_domain_profile_workflow as legacy
legacy.ROOT=C
from test_semantics import wire_normalization
from semantic_runtime.ontology_work.domain_workflow import DomainWorkflow
class Results:
 def __init__(self):self.rows=[]
 def pytest_runtest_logreport(self,report):
  if report.when=='call' or report.failed:self.rows.append({'test':report.nodeid,'status':report.outcome,'error':report.longreprtext if report.failed else None})
 @pytest.fixture(autouse=True)
 def wire_fixture(self,monkeypatch):
  original=DomainWorkflow._job
  def job(self,stage,context,prompt,schema,validator,binding_check=None):
   generate=self.generate
   if stage=='NORMALIZE' and generate is not None:
    def translated(*args):
     value,receipt=generate(*args)
     return wire_normalization(value,context['raw']),receipt
    self.generate=translated
   try:return original(self,stage,context,prompt,schema,validator,binding_check)
   finally:self.generate=generate
  monkeypatch.setattr(DomainWorkflow,'_job',job)
  original_set=monkeypatch.setenv
  monkeypatch.setattr(monkeypatch,'setenv',lambda n,v,*a,**k:original_set(n,str(C) if n=='WORKFLOW_TEST_CODE_ROOT' else v,*a,**k))
r=Results();tag=sys.argv[1] if len(sys.argv)>1 else 'first';t=time.monotonic()
(ART/'test-runtime').mkdir(parents=True,exist_ok=True)
paths=[str(Path(__file__).parent/'test_semantics.py')]+[str(ROOT/'05_TESTS/CONTRACTS'/n) for n in ('test_domain_profile_workflow.py','test_domain_profile_native.py','test_domain_profile_ui.py')]
code=pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','--show-capture=no','-p','no:cacheprovider','--basetemp='+str(ART/'test-runtime'/tag),'-k',sys.argv[2] if len(sys.argv)>2 else '',*paths],plugins=[r,conftest])
sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'));from experiment_json import write_summary
write_summary(ART/('checks-'+tag+'.json'),{'rows':r.rows,'exit_code':int(code),'seconds':time.monotonic()-t,'passed':sum(x['status']=='passed' for x in r.rows),'failed':sum(x['status']=='failed' for x in r.rows),'external_model_calls':0,'fixture_adapter':'Absent canonical reason/purpose and exact locators translated to new wire for legacy mocked generators only'})
raise SystemExit(int(code))
