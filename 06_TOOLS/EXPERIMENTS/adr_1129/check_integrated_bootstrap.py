from pathlib import Path
import json,sys,os,hashlib,resource,time,importlib
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1129-catalog-recovery-serving';ART=ADR/'artifacts';f=json.loads((ART/'design/freeze.json').read_text());C=ROOT/f['code_root'];mode=sys.argv[1]
def sha(p):
 with Path(p).open('rb') as h:return hashlib.file_digest(h,'sha256').hexdigest()
assert mode in ('primary','support','modes')
assert all(sha(C/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/n)==h for n,h in f['scripts'].items())
support=json.loads((ART/'design/test-support.json').read_text());assert all(sha(ROOT/n)==h for n,h in support['files'].items())
resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,)*2);sys.dont_write_bytecode=True
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT),WORKFLOW_TEST_CODE_ROOT=str(C),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0')
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS'),str(Path(__file__).parent)]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for name in ('pipeline','core'):
 pkg=importlib.import_module('lawrag.'+name);pkg.__path__.append(str(ROOT/'02_BACKEND/lawrag'/name))
saved_paths=list(sys.path)
import inspect,pytest
import conftest
sys.path[:]=saved_paths
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(Path(__file__).parent),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS')]
import pytest
files={'primary':['test_fresh_matrix.py','test_native_qualification.py','test_catalogue_receipt.py'],
'support':['test_preparation.py','test_stable_recovery_isolated.py','test_output_contract_local.py','test_runtime_binding.py','test_regression_matrix.py','test_native_integrated.py','test_conflict_diagnostics.py','test_review_ownership.py','test_complete_alternatives.py','test_final_diagnostics.py','test_final_shape.py','test_observed_matrix.py','test_observed_native.py','test_document_catalog.py'],
'modes':[str(ROOT/'05_TESTS/CONTRACTS/test_genos_applied_mode.py')]}[mode]
paths=[str(Path(__file__).parent/n) if not Path(n).is_absolute() else n for n in files]
if mode=='support':paths += [str(ROOT/'05_TESTS/CONTRACTS/test_read_judgment.py'),str(ROOT/'05_TESTS/CONTRACTS/test_compact_wire_binding.py')]
class Results:
 rows=[]
 def pytest_collection_modifyitems(self,session,config,items):
  for name,m in list(sys.modules.items()):
   if name.startswith('test_') and getattr(m,'ROOT',None)==ROOT:m.ROOT=C
 def pytest_runtest_logreport(self,report):
  if report.when=='call' or report.failed:self.rows.append({'test':report.nodeid,'status':report.outcome,'error':report.longreprtext if report.failed else None})
r=Results();start=time.monotonic();rc=pytest.main(['--noconftest','-c','/dev/null','--confcutdir='+str(Path(__file__).parent),'-q','--tb=short','-p','no:cacheprovider',*paths],plugins=[r,conftest])
imports={n:str(Path(m.__file__).resolve()) for n,m in sys.modules.items() if n.split('.')[0] in ('semantic_runtime','lawrag') and getattr(m,'__file__',None)}
leaks={n:p for n,p in imports.items() if n.startswith('semantic_runtime') and not Path(p).is_relative_to(C)}
external={n:str(Path(p).relative_to(ROOT)) for n,p in imports.items() if Path(p).is_relative_to(ROOT) and not Path(p).is_relative_to(C)}
assert all(p in support['files'] and sha(ROOT/p)==support['files'][p] for p in external.values()),external
assert all(sha(C/n)==h for n,h in f['files'].items())
result={'status':int(rc),'passed':sum(x['status']=='passed' for x in r.rows),'failed':sum(x['status']=='failed' for x in r.rows),'rows':r.rows,'import_leaks':leaks,'fixture_support_imports':external,'seconds':time.monotonic()-start,'new_model_calls':0,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
out=ART/('check-'+mode+'.json');assert not out.exists();out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('RESULT',mode,result['passed'],result['failed'],leaks)
raise SystemExit(int(bool(rc or leaks)))
