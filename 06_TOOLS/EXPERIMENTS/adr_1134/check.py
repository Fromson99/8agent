from common import *
import os,sys,time
f=read(ART/'freeze.json');code=ROOT/f['code_root']
sys.dont_write_bytecode=True;os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT))
os.chdir(code);sys.path[:0]=[str(code/'02_BACKEND'),str(code),str(code/'05_TESTS'),str(code/'05_TESTS/CONTRACTS')]
import pytest
class Results:
 def __init__(self):self.rows=[]
 def pytest_runtest_logreport(self,report):
  r=report
  if r.when=='call' or r.failed:self.rows.append({'test':r.nodeid,'when':r.when,'status':r.outcome,'error':r.longreprtext if r.failed else None})
plugin=Results();start=time.monotonic()
tests=[str(code/'05_TESTS/CONTRACTS'/n) for n in ('test_ontology_compiler.py','test_compact_model_input.py','test_compact_wire_binding.py','test_journal_evidence_batch.py')]
tests.extend(str(Path(__file__).with_name(n)) for n in ('test_projection.py','test_direct.py','test_semantics.py','test_scenarios.py','test_scenario_native.py','test_sufficiency.py'))
rc=pytest.main(['-c','/dev/null','--confcutdir='+str(code),'-q','--tb=short','--show-capture=no','-p','no:cacheprovider',*tests],plugins=[plugin])
imports={n:str(Path(v.__file__).resolve()) for n,v in sys.modules.items() if n.split('.')[0] in ('semantic_runtime','lawrag') and getattr(v,'__file__',None)}
leaks={n:p for n,p in imports.items() if not Path(p).is_relative_to(code)}
changed=[n for n,h in f['files'].items() if sha(code/n)!=h]
result={'status':int(rc),'passed':sum(r['status']=='passed' for r in plugin.rows),'failed':sum(r['status']=='failed' for r in plugin.rows),'seconds':time.monotonic()-start,'rows':plugin.rows,'imports':imports,'import_leaks':leaks,'changed_files':changed,'new_model_calls':0}
p=ART/'check-001.json';assert not p.exists();put(p,result)
print('CHECK',result['passed'],result['failed'],result['seconds'],'leaks',len(leaks));raise SystemExit(bool(rc or leaks or changed))
