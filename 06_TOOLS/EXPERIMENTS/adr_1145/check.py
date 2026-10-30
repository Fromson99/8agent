from pathlib import Path
import json,hashlib,os,sys,time,resource
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1145-scenario-complement-selection';D=A/'artifacts';T=Path(__file__).parent
read=lambda p:json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
f=read(D/'freeze.json');binding=f['arms']['concise'];code=R/binding['code_root'];sys.dont_write_bytecode=True
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(R),LAWRAG_TOOL_WORKSPACE_ROOT=str(R),QUALIFICATION_CODE_ROOT=str(code),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0')
os.environ.pop('GENOS_RAG_ONTOLOGY_ENABLED',None);resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3));os.chdir(code)
sys.path[:0]=[str(code/'02_BACKEND'),str(code),str(code/'05_TESTS'),str(code/'05_TESTS/CONTRACTS')]
import pytest
class Results:
 def __init__(self):self.rows=[]
 def pytest_runtest_logreport(self,report):
  r=report
  if r.when=='call' or r.failed:self.rows.append({'test':r.nodeid,'when':r.when,'status':r.outcome,'error':r.longreprtext if r.failed else None})
p=Results();start=time.monotonic()
old=R/'06_TOOLS/EXPERIMENTS/adr_1139'
sys.path.insert(0,str(old))
tests=[str(old/n) for n in ('test_scenarios.py','test_sufficiency.py','test_scenario_native.py')]
rc=pytest.main(['-c','/dev/null','--confcutdir='+str(code),'-q','--tb=short','--show-capture=no','-p','no:cacheprovider',*tests],plugins=[p])
imports={n:str(Path(v.__file__).resolve()) for n,v in sys.modules.items() if n.split('.')[0] in ('semantic_runtime','lawrag') and getattr(v,'__file__',None)}
leaks={n:v for n,v in imports.items() if not Path(v).is_relative_to(code)}
changed=[n for n,h in binding['files'].items() if sha(code/n)!=h]
result={'status':int(rc),'passed':sum(x['status']=='passed' for x in p.rows),'failed':sum(x['status']=='failed' for x in p.rows),'rows':p.rows,'imports':imports,'import_leaks':leaks,'changed_files':changed,'seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'new_model_calls':0}
out=A/'artifacts/check-001.json';assert not out.exists();out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('CHECK',result['passed'],result['failed'],'leaks',len(leaks),'changed',changed)
raise SystemExit(bool(rc or leaks or changed))
