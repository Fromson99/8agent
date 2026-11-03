from common import *
import os,time,importlib,argparse
p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--baseline',action='store_true');p.add_argument('tests',nargs='*');args=p.parse_args()
freeze=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1284-shared-scenario-contract-live/artifacts/design/freeze.json' if args.baseline else DES/'freeze.json');C=ROOT/freeze['code_root'];out=ART/args.name;out.mkdir(exist_ok=False)
assert all(sha(C/n)==h for n,h in freeze['files'].items())
os.environ.update(LOOP_TEST_CODE_ROOT=str(C),WORKFLOW_TEST_CODE_ROOT=str(C),GENOS_ONTOLOGY_CODE_ROOT=str(C),LOOP_TEST_REPOSITORY_ROOT=str(ROOT),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0');os.environ.pop('DP',None)
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for n in ('pipeline','core'):
 pkg=importlib.import_module('lawrag.'+n);pkg.__path__.append(str(ROOT/'02_BACKEND/lawrag'/n))
import conftest,pytest
import wire_fixture
sys.path[:0]=[str(C/'02_BACKEND'),str(C/'03_FRONTEND/APPS/legal-knowledge-streamlit'),str(C/'05_TESTS/CONTRACTS'),str(ROOT/'90_RUNTIME/streamlit-knowledge-design/python'),str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1301'),str(C)]
rows=[]
class Recorder:
 def pytest_runtest_logreport(self,report):
  if report.when=='call' or report.failed:rows.append({'test':report.nodeid,'when':report.when,'outcome':report.outcome,'error':report.longreprtext if report.failed else None,'sections':report.sections if report.failed else []})
paths=args.tests or ['06_TOOLS/EXPERIMENTS/adr_1301/test_contracts.py']
from resource_guard import Guard
guard=Guard(out);guard.start()
start=time.monotonic();status=pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','--show-capture=no','-p','no:cacheprovider','--basetemp='+str(out/'runtime'),*[str(C/n if n.startswith(('05_TESTS/CONTRACTS/test_wiki_workspace.py','05_TESTS/CONTRACTS/test_genos_answer_reference_display.py','03_FRONTEND/')) else ROOT/n) for n in paths]],plugins=[conftest,wire_fixture,Recorder()])
guard.done.set();guard.thread.join(timeout=3)
put(out/'resource-final.json',guard.check())
result={'exit_code':int(status),'passed':sum(r['outcome']=='passed' for r in rows),'failed':sum(r['outcome']=='failed' for r in rows),'seconds':time.monotonic()-start,'rows':rows,'model_calls':0,'oracle_calls':0,'code_root':str(C),'code_unchanged':all(sha(C/n)==h for n,h in freeze['files'].items()),'tests':{str(p):(sha(C/p.split('::')[0] if (C/p.split('::')[0]).is_file() else ROOT/p.split('::')[0])) for p in paths if (C/p.split('::')[0]).is_file() or (ROOT/p.split('::')[0]).is_file()},'active_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==freeze['pointer_sha256']}
put(out/'result.json',result);print({k:v for k,v in result.items() if k!='rows'});raise SystemExit(int(status))
