from pathlib import Path
import hashlib,json,os,sys,time,importlib,argparse
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1308-gold-query-optimization'
p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--prepared',action='store_true');p.add_argument('--baseline',action='store_true');p.add_argument('--exclude-known-ontology-fixtures',action='store_true');p.add_argument('tests',nargs='*');args=p.parse_args()
f=json.loads((ADR/'artifacts/design-final/freeze.json').read_text())
if args.prepared:f=json.loads((ROOT/'08_DEPLOYMENT/RELEASES/gold-query-optimized-20261103-r2/release.json').read_text())
C=ROOT/f['code_root']
if args.baseline:
 f={'code_root':'.','files':json.loads((ADR/'artifacts/design/baseline.json').read_text())['working_files']};C=ROOT
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(C/n)==h for n,h in f['files'].items())
out=ADR/'artifacts'/args.name;out.mkdir(exist_ok=False)
os.environ.update(LOOP_TEST_CODE_ROOT=str(C),WORKFLOW_TEST_CODE_ROOT=str(C),GENOS_ONTOLOGY_CODE_ROOT=str(C),LOOP_TEST_REPOSITORY_ROOT=str(ROOT),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0')
os.environ.pop('DP',None);sys.dont_write_bytecode=True
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for n in ('pipeline','core'):
 pkg=importlib.import_module('lawrag.'+n);pkg.__path__.append(str(ROOT/'02_BACKEND/lawrag'/n))
import conftest,pytest
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(Path(__file__).parent)]
rows=[]
class Recorder:
 @pytest.fixture(autouse=True)
 def historical_artifact_root(self,request,monkeypatch):
  if request.node.name=='test_archived_real_1277_acquired_need_is_not_a_new_source_request':
   monkeypatch.setattr(request.module,'ROOT',ROOT)
 def pytest_runtest_logreport(self,report):
  r=report
  if r.when=='call' or r.failed:rows.append({'test':r.nodeid,'when':r.when,'outcome':r.outcome,'error':r.longreprtext if r.failed else None})
sys.path.insert(0,str(Path(__file__).parent))
from resource_guard import Guard
guard=Guard(out);guard.start();started=time.monotonic()
paths=args.tests or ['06_TOOLS/EXPERIMENTS/adr_1308/test_queries.py']
status=pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','-p','no:cacheprovider','--basetemp='+str(out/'runtime'),*(['-k','not test_native_typed_scenario_and_explicit_ontology_use'] if args.exclude_known_ontology_fixtures else []),*[str(ROOT/p) for p in paths]],plugins=[conftest,Recorder()])
guard.done.set();guard.thread.join(timeout=3)
result={'known_ontology_fixture_exclusion':args.exclude_known_ontology_fixtures,'exit_code':int(status),'passed':sum(r['outcome']=='passed' for r in rows),'failed':sum(r['outcome']=='failed' for r in rows),'seconds':time.monotonic()-started,'rows':rows,'model_calls':0,'oracle_calls':0,'code_root':str(C.relative_to(ROOT)),'code_unchanged':all(sha(C/n)==h for n,h in f['files'].items()),'resources':guard.check()}
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print({k:v for k,v in result.items() if k not in ('rows','resources')});raise SystemExit(int(status))
