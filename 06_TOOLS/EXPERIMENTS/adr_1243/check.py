from pathlib import Path
import importlib,json,logging,os,sys,time
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1243-oracle-default-runtime-main';ART=ADR/'artifacts'
mode=sys.argv[1] if len(sys.argv)>1 else 'candidate';tag=sys.argv[2] if len(sys.argv)>2 else mode
read=lambda p:json.loads(Path(p).read_text())
b=read(ART/'design/baseline.json')
C=ROOT/b['manifest']['code_root'] if mode=='baseline' else ROOT/read(ART/'design/freeze.json')['code_root']
if os.environ.get('ADR1243_ROOT_ENTRY')=='1':C=ROOT
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT),WORKFLOW_TEST_CODE_ROOT=str(C),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0')
os.environ.pop('DP',None)
sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS'),str(Path(__file__).parent)]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for n in ('pipeline','core'):
 p=importlib.import_module('lawrag.'+n);p.__path__.append(str(ROOT/'02_BACKEND/lawrag'/n))
import conftest,pytest
sys.path[:0]=[str(C),str(C/'02_BACKEND')]
class Results:
 def __init__(self):self.rows=[]
 def pytest_collection_modifyitems(self,items):
  for name,module in list(sys.modules.items()):
   file=getattr(module,'__file__',None)
   if name.startswith('test_') and file and Path(file).is_relative_to(ROOT/'05_TESTS') and getattr(module,'ROOT',None)==ROOT:module.ROOT=C
 def pytest_runtest_logreport(self,report):
  r=report
  if r.when=='call' or r.failed:self.rows.append({'test':r.nodeid,'status':r.outcome,'error':r.longreprtext if r.failed else None,
      **({'captured_log':r.caplog,'captured_stdout':r.capstdout,'captured_stderr':r.capstderr} if r.failed else {})})
r=Results();paths=[]
selection=sys.argv[3] if len(sys.argv)>3 else 'existing'
if selection=='records':paths=[str(Path(__file__).parent/'test_records.py')]
elif selection=='api':paths=[str(Path(__file__).parent/'test_oracle_service.py')]
elif selection=='support':paths=[str(ROOT/'05_TESTS/CONTRACTS'/n) for n in (
    'test_genos_journal_storage.py','test_legal_llm_wiki.py','test_ad_request_reports.py','test_workflow_source_cards.py')]
else:
 paths=[str(ROOT/'05_TESTS/CONTRACTS'/n) for n in ('test_oracle_query.py','test_oracle_query_catalog.py','test_legal_agent_double_harness.py',
    'test_unified_legal_agent.py','test_journal_storage.py') if (ROOT/'05_TESTS/CONTRACTS'/n).exists()]
start=time.monotonic();(ART/'test-runtime').mkdir(exist_ok=True)
code=pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','--show-capture=no','-p','no:cacheprovider',
    '--basetemp='+str(ART/'test-runtime'/tag),*paths],plugins=[r,conftest])
result={'code_root':str(C.relative_to(ROOT)),'exit_code':int(code),'rows':r.rows,'seconds':time.monotonic()-start,
        'passed':sum(v['status']=='passed' for v in r.rows),'failed':sum(v['status']=='failed' for v in r.rows),'real_model_calls':0}
out=ART/('checks-'+tag+'.json')
with out.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
raise SystemExit(int(code))
