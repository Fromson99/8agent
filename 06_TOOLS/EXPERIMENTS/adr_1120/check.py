from pathlib import Path
import hashlib,json,sys,os,time
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1120-full-alternative-native-check'
f=json.loads((ADR/'artifacts/design/freeze.json').read_text());C=ROOT/f['code_root']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert all(sha(C/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/n)==h for n,h in f['scripts'].items())
sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(ROOT/'05_TESTS/CONTRACTS')]
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT),AD_WORKER_ENABLED='0')
import pytest
class Results:
    rows=[]
    def pytest_runtest_logreport(self,report):
        r=report
        if r.when=='call' or r.failed:self.rows.append({'test':r.nodeid,'status':r.outcome,'error':r.longreprtext if r.failed else None})
p=Results();start=time.perf_counter()
rc=pytest.main(['-k','not test_actual_resume_keeps_newer_judgments_before_executing_accepted_action and not test_composition_carries_and_checks_review_receipt','--noconftest','-c','/dev/null','--confcutdir='+str(Path(__file__).parent),'-q','--tb=short','-p','no:cacheprovider',str(Path(__file__).with_name('test_runtime_binding.py')),str(Path(__file__).with_name('test_preparation.py')),str(Path(__file__).with_name('test_stable_recovery_isolated.py')),str(Path(__file__).with_name('test_output_contract_local.py')),str(ROOT/'05_TESTS/CONTRACTS/test_read_judgment.py'),str(ROOT/'05_TESTS/CONTRACTS/test_compact_wire_binding.py')],plugins=[p])
leaks={n:v.__file__ for n,v in sys.modules.items() if n.split('.')[0] in ('semantic_runtime','lawrag') and getattr(v,'__file__',None) and not Path(v.__file__).resolve().is_relative_to(C)}
out=ADR/'artifacts/check-001.json';assert not out.exists()
result={'status':int(rc),'rows':p.rows,'passed':sum(r['status']=='passed' for r in p.rows),'failed':sum(r['status']=='failed' for r in p.rows),
        'seconds':time.perf_counter()-start,'import_leaks':leaks,'new_model_calls':0,'active_changed':False}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('CHECK',result['passed'],result['failed'],leaks)
raise SystemExit(int(bool(rc or leaks)))
