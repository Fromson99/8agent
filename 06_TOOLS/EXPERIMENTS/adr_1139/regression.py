from pathlib import Path
import json,sys,os,resource,hashlib,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1139-ontology-framework-local-http';D=A/'artifacts/design';T=Path(__file__).parent
arm=sys.argv[1];read=lambda p:json.loads(p.read_text());base=read(D/'baseline.json');stage=read(D/'staging.json');S=R/(base['manifest']['code_root'] if arm=='baseline' else stage['code_root']);files=base['manifest']['files'] if arm=='baseline' else stage['files']
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(R),GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0',WORKFLOW_TEST_CODE_ROOT=str(S));os.environ.pop('GENOS_RAG_ONTOLOGY_ENABLED',None)
resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3));sys.dont_write_bytecode=True
sys.path[:0]=[str(S),str(S/'02_BACKEND'),str(R/'02_BACKEND'),str(R/'05_TESTS/CONTRACTS')]
import lawrag
lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
import lawrag.pipeline
lawrag.pipeline.__path__.append(str(R/'02_BACKEND/lawrag/pipeline'))
import main,pytest
class Roots:
 def pytest_collection_modifyitems(self,session,config,items):
  for name,m in list(sys.modules.items()):
   if name.startswith('test_') and getattr(m,'ROOT',None)==R:m.ROOT=S
 def pytest_sessionfinish(self,session,exitstatus):
  assert all(hashlib.sha256((S/n).read_bytes()).hexdigest()==h for n,h in files.items())
tests=['test_genos_applied_mode.py','test_genos_chat_flow.py','test_genos_main_chat.py','test_genos_native_chat_sse.py','test_risk_team_compare_workflow.py','test_source_prefix_routing.py','test_unified_legal_agent.py','test_unified_scope_semantic_authority.py','test_main50_request_repair.py']
out=A/'artifacts'/('regression-'+arm+'.xml');assert not out.exists()
raise SystemExit(pytest.main(['-q','--tb=short','--show-capture=no','--junitxml='+str(out),'-p','no:cacheprovider',*[str(R/'05_TESTS/CONTRACTS'/n) for n in tests]],plugins=[Roots()]))
