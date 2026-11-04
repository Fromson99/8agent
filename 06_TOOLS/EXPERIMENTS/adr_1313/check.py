from common import *
import os,time,importlib,argparse
p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--arm',default='sqlite');p.add_argument('tests',nargs='*');args=p.parse_args()
f=read(DES/('candidate-'+args.arm+'.json'));C=ROOT/f['code_root'];assert all(sha(C/n)==h for n,h in f['selected_files'].items())
out=ART/args.name;out.mkdir(exist_ok=False)
os.environ.update(LOOP_TEST_CODE_ROOT=str(C),WORKFLOW_TEST_CODE_ROOT=str(C),GENOS_ONTOLOGY_CODE_ROOT=str(C),LOOP_TEST_REPOSITORY_ROOT=str(ROOT),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0',PYTHONDONTWRITEBYTECODE='1',MALLOC_ARENA_MAX='1')
os.environ.pop('DP',None);sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import lawrag;lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for n in ('pipeline','core'):
 pkg=importlib.import_module('lawrag.'+n);pkg.__path__.append(str(ROOT/'02_BACKEND/lawrag'/n))
import conftest,pytest
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(Path(__file__).parent)]
rows=[]
class Recorder:
 def pytest_runtest_logreport(self,report):
  r=report
  if r.when=='call' or r.failed:rows.append({'test':r.nodeid,'when':r.when,'outcome':r.outcome,'error':r.longreprtext if r.failed else None})
from resource_guard import Guard
guard=Guard(out);guard.start();begin=time.monotonic()
paths=args.tests or ['06_TOOLS/EXPERIMENTS/adr_1311/test_repair.py','05_TESTS/CONTRACTS/test_model_structure_selection.py','05_TESTS/CONTRACTS/test_required_structure_selection.py','05_TESTS/CONTRACTS/test_query_latency_cache.py','05_TESTS/CONTRACTS/test_source_store_verification_cache.py']
status=pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','-p','no:cacheprovider','--basetemp='+str(out/'runtime'),*[str(ROOT/p) for p in paths]],plugins=[conftest,Recorder()])
guard.done.set();guard.thread.join(timeout=2)
put(out/'result.json',{'exit_code':int(status),'passed':sum(r['outcome']=='passed' for r in rows),'failed':sum(r['outcome']=='failed' for r in rows),'seconds':time.monotonic()-begin,'rows':rows,'code_root':str(C),'code_unchanged':all(sha(C/n)==h for n,h in f['selected_files'].items()),'resources':guard.check()});raise SystemExit(int(status))
