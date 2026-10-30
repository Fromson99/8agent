from pathlib import Path
import sys,os,json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1165-vector-navigation-connected';f=json.loads((A/'artifacts/design/freeze.json').read_text());C=R/f['code_root']
assert all(hashlib.sha256((C/n).read_bytes()).hexdigest()==h for n,h in f['files'].items())
os.environ.update(VECTOR_CODE_ROOT=str(C),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0');sys.path[:0]=[str(C/'02_BACKEND'),str(Path(__file__).parent)]
import pytest
class Results:
 rows=[]
 def pytest_runtest_logreport(self,report):
  r=report
  if r.when=='call' or r.failed:self.rows.append({'test':r.nodeid,'status':r.outcome,'error':r.longreprtext if r.failed else None})
r=Results();rc=pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','-p','no:cacheprovider',str(Path(__file__).parent/'test_vector.py')],plugins=[r]);out={'status':rc,'rows':r.rows,'passed':sum(x['status']=='passed' for x in r.rows),'failed':sum(x['status']=='failed' for x in r.rows),'new_model_calls':0};p=A/'artifacts'/('technical-'+f['binding']['revision_id']+'.json');assert not p.exists();p.write_text(json.dumps(out,ensure_ascii=False,indent=2));raise SystemExit(rc)
