"""Focused tests against one explicit frozen code map, never selected MAIN."""
from pathlib import Path
import hashlib,json,os,sys,time
import pytest
ROOT=Path(__file__).resolve().parents[3]
ART=ROOT/'04_EXPERIMENTS/ADR/ADR-1068-startup-latency-attribution/artifacts'
code=Path(sys.argv[1]).resolve();name=sys.argv[2]
sys.dont_write_bytecode=True
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT),ADR1068_OPTIMIZED_SNAPSHOT=str(code))
os.chdir(code);sys.path[:0]=[str(code/'02_BACKEND'),str(code),str(code/'05_TESTS'),str(code/'05_TESTS/CONTRACTS')]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def files():return {str(p.relative_to(code)):sha(p) for p in code.rglob('*') if p.is_file()}
before=files()
tests=[]
for item in sys.argv[3:]:
    path,node=(item.split('::',1)+[None])[:2] if '::' in item else (item,None)
    p=Path(path)
    if not p.is_absolute():p=code/'05_TESTS/CONTRACTS'/p
    tests.append(str(p)+('::'+node if node else ''))
class Results:
    def __init__(self):self.rows=[]
    def pytest_runtest_logreport(self,report):
        r=report
        if r.when=='call' or r.failed:self.rows.append({'nodeid':r.nodeid,'when':r.when,'outcome':r.outcome,'error':r.longreprtext if r.failed else None})
plugin=Results();start=time.perf_counter()
status=pytest.main(['-c','/dev/null','--confcutdir='+str(code),'-q','--tb=short','--show-capture=no','-p','no:cacheprovider','-o','faulthandler_timeout=45',*tests],plugins=[plugin])
imports={n:str(Path(m.__file__).resolve()) for n,m in sys.modules.items() if n.split('.')[0] in ('semantic_runtime','lawrag') and getattr(m,'__file__',None)}
leaks={n:p for n,p in imports.items() if not Path(p).is_relative_to(code)}
after=files()
value={'status':int(status),'elapsed_seconds':time.perf_counter()-start,'passed':sum(r['outcome']=='passed' for r in plugin.rows),'failed':sum(r['outcome']=='failed' for r in plugin.rows),'rows':plugin.rows,'code_root':str(code.relative_to(ROOT)),'files':before,'candidate_changed':before!=after,'imports':imports,'import_leaks':leaks,'live_model_calls':0,'real_corpus_loads':0}
(ART/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print('BINDING',json.dumps({'imports':len(imports),'leaks':len(leaks),'changed':before!=after}))
raise SystemExit(int(bool(status or leaks or before!=after)))
