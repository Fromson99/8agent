from common import *
import os,time,importlib,argparse
p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--baseline',action='store_true');p.add_argument('tests',nargs='*');args=p.parse_args()
freeze=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1282-lossless-assessment-contract/artifacts/design/freeze.json' if args.baseline else DES/'freeze.json');C=ROOT;out=ART/args.name;out.mkdir(exist_ok=False)
assert all(sha(C/n)==h for n,h in freeze['files'].items())
os.environ.update(LOOP_TEST_CODE_ROOT=str(C),WORKFLOW_TEST_CODE_ROOT=str(C),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0');os.environ.pop('DP',None)
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for n in ('pipeline','core'):
 pkg=importlib.import_module('lawrag.'+n);pkg.__path__.append(str(ROOT/'02_BACKEND/lawrag'/n))
import conftest,pytest
sys.path[:0]=[str(C/'02_BACKEND'),str(C)]
rows=[]
class Recorder:
 def pytest_runtest_logreport(self,report):
  if report.when=='call' or report.failed:rows.append({'test':report.nodeid,'when':report.when,'outcome':report.outcome,'error':report.longreprtext if report.failed else None})
paths=args.tests or ['06_TOOLS/EXPERIMENTS/adr_1285/test_contracts.py']
start=time.monotonic();status=pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','--show-capture=no','-p','no:cacheprovider','--basetemp='+str(out/'runtime'),*[str(ROOT/n) for n in paths]],plugins=[conftest,Recorder()])
result={'exit_code':int(status),'passed':sum(r['outcome']=='passed' for r in rows),'failed':sum(r['outcome']=='failed' for r in rows),'seconds':time.monotonic()-start,'rows':rows,'model_calls':0,'oracle_calls':0,'code_root':str(C),'code_unchanged':all(sha(C/n)==h for n,h in freeze['files'].items()),'tests':{str(p):sha(ROOT/p) for p in paths},'active_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==freeze['pointer_sha256']}
put(out/'result.json',result);print({k:v for k,v in result.items() if k!='rows'});raise SystemExit(int(status))
