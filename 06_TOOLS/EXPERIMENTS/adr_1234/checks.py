from pathlib import Path
import json,sys,importlib.util,os
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1234-gold-ontology-reference-repair';D=A/'artifacts/design';O=A/'artifacts/run-001';P=R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
def read(p):return json.loads(p.read_text())
F=R/read(D/'candidate.json')['snapshot'];C=R/read(P/'binding.json')['engine_root'];sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(R/'05_TESTS/CONTRACTS')]
spec=importlib.util.spec_from_file_location('gold',F/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py');gold=importlib.util.module_from_spec(spec);spec.loader.exec_module(gold);gold.HERE=P;gold.ROOT=R;gold.install_runtime_patches(C)
import pytest
class Capture:
 def __init__(self):self.rows=[]
 def pytest_runtest_logreport(self,report):
  if report.when=='call' or report.failed:self.rows.append({'test':report.nodeid,'status':report.outcome,'failure':report.longreprtext if report.failed else None})
r=Capture();code=pytest.main(['-q','--noconftest','-c','/dev/null','-p','no:cacheprovider','--tb=short',str(Path(__file__).with_name('test_repairs.py')),str(R/'05_TESTS/CONTRACTS/test_navigation_input_compaction.py')],plugins=[r]);(O/'checks.json').write_text(json.dumps({'passed':sum(x['status']=='passed' for x in r.rows),'failed':sum(x['status']=='failed' for x in r.rows),'rows':r.rows,'model_calls':0},ensure_ascii=False,indent=2)+'\n');raise SystemExit(code)
