import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
ART=ROOT/'04_EXPERIMENTS/ADR/ADR-1271-source-goal-coordinate-recovery/artifacts'
sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'))
from experiment_json import write_summary as put
sys.dont_write_bytecode=True
import os,time
C=Path(os.environ.get('DIAGNOSTIC_CODE_ROOT',str(ROOT/'02_BACKEND/lawrag/research/candidates/adr_1271/repaired/snapshot')));name=sys.argv[1]
out=ART/name;out.mkdir(parents=True,exist_ok=False)
os.environ.update(WORKFLOW_TEST_CODE_ROOT=str(C),LOOP_TEST_CODE_ROOT=str(C),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0');os.environ.pop('DP',None)
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
import importlib
for n in ('pipeline','core'):
 package=importlib.import_module('lawrag.'+n);package.__path__.append(str(ROOT/'02_BACKEND/lawrag'/n))
import pytest
import conftest
sys.path[:0]=[str(C/'02_BACKEND'),str(C)]
files=['test_source_target_coordinate.py','test_need_continuity.py','test_agent_loop_fault_recovery.py','test_selection_contract_versions.py']
before={n:hashlib.sha256((ROOT/'05_TESTS/CONTRACTS'/n).read_bytes()).hexdigest() for n in files}
rows=[]
class Report:
 def pytest_runtest_logreport(self,report):
  r=report
  if r.when=='call' or r.failed:rows.append({'test':r.nodeid,'when':r.when,'outcome':r.outcome,'error':r.longreprtext if r.failed else None})
code=pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','--show-capture=no','--rootdir='+str(ROOT),'-p','no:cacheprovider','--basetemp='+str(out/'runtime'),*[str(ROOT/'05_TESTS/CONTRACTS'/n) for n in files]],plugins=[conftest,Report()])
put(out/'result.json',{'exit':int(code),'rows':rows,'passed':sum(r['outcome']=='passed' for r in rows),'failed':sum(r['outcome']=='failed' for r in rows),'candidate':str(C),'test_hashes':before,'tests_unchanged':all(hashlib.sha256((ROOT/'05_TESTS/CONTRACTS'/n).read_bytes()).hexdigest()==h for n,h in before.items())})
sys.exit(int(code))
