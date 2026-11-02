import inspect
from pathlib import Path
import json,os,sys,importlib,time
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1251-general-evidence-review';D=A/'artifacts/design';mode=sys.argv[1];tag=sys.argv[2]
read=lambda p:json.loads(p.read_text())
C=R/read(D/'baseline.json')['release']['code_root'] if mode=='baseline' else R/read(D/'freeze.json')['code_root'] if mode=='candidate' else R/'02_BACKEND/lawrag/research/candidates/adr_1251/generalized-isolated/snapshot' if mode=='draft' else R
os.environ.update(WORKFLOW_TEST_CODE_ROOT=str(C),LAWRAG_WORKSPACE_ROOT=str(R),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0')
sys.dont_write_bytecode=True
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS'),str(Path(__file__).parent),str(R/'06_TOOLS/EXPERIMENTS/adr_1190')]
import lawrag
lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
for name in ('pipeline','core'):
 m=importlib.import_module('lawrag.'+name);m.__path__.append(str(R/'02_BACKEND/lawrag'/name))
import lawrag.research
lawrag.research.__path__.insert(0,str(C/'02_BACKEND/lawrag/research'))
import conftest,pytest
sys.path[:0]=[str(C),str(C/'02_BACKEND')]
class Results:
 def __init__(self):self.rows=[]
 def pytest_collection_modifyitems(self,items):
  for name,module in list(sys.modules.items()):
   if name.startswith('test_') and getattr(module,'ROOT',None)==R:module.ROOT=C
 def pytest_runtest_logreport(self,report):
  r=report
  if r.when=='call' or r.failed:self.rows.append({'test':r.nodeid,'status':r.outcome,'error':r.longreprtext if r.failed else None})
(A/'artifacts/test-runtime').mkdir(exist_ok=True)
x=Results();files=sys.argv[3:] or [str(Path(__file__).parent/'test_faults.py')]
status=pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','--show-capture=no','-p','no:cacheprovider','--basetemp='+str(A/'artifacts/test-runtime'/tag),*files],plugins=[x,conftest])
p=A/'artifacts'/('checks-'+tag+'.json');p.write_text(json.dumps({'exit_code':int(status),'rows':x.rows,'passed':sum(r['status']=='passed' for r in x.rows),'failed':sum(r['status']=='failed' for r in x.rows),'real_model_calls':0},ensure_ascii=False,indent=2));raise SystemExit(int(status))
