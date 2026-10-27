from pathlib import Path
import os,sys,json,hashlib,time
import pytest
ROOT=Path('/home/jin/8-AGENT')
code=Path(sys.argv[1]).resolve();art=ROOT/'04_EXPERIMENTS/ADR/ADR-1043-ontology-mvp-input-budget/artifacts'
name=sys.argv[2]
os.environ['LAWRAG_WORKSPACE_ROOT']=str(ROOT)
os.environ['LAWRAG_TOOL_WORKSPACE_ROOT']=str(ROOT)
os.chdir(code);sys.path[:0]=[str(code/'02_BACKEND'),str(code)]
tests=['test_ontology_compiler.py','test_ontology_context.py','test_ontology_api.py','test_definition_context.py','test_experiment_session_export.py','test_final_input_budget.py','test_wire_schema_identity.py','test_navigation_input_audit_budget.py','test_input_budget_completion_adr1043.py','test_output_contract_recovery.py']
class Results:
 def __init__(self):self.rows=[];self.api=[]
 def pytest_runtest_logreport(self,report):
  if report.when=='call' or report.failed:self.rows.append({'nodeid':report.nodeid,'when':report.when,'outcome':report.outcome})
  if report.when=='call' and report.passed and ('api' in report.nodeid or 'test_experiment_session_export.py' in report.nodeid):
   names=['semantic_runtime.app','semantic_runtime.legal_agent.gateway','semantic_runtime.legal_agent.law_navigation','semantic_runtime.legal_agent.completion_execution','semantic_runtime.legal_agent.unified_publication']
   self.api.append({'nodeid':report.nodeid,'outcome':'passed','imports':{n:str(Path(sys.modules[n].__file__).resolve()) for n in names if n in sys.modules}})
p=Results();start=time.monotonic()
status=pytest.main(['-c','/dev/null','--confcutdir='+str(code),'-q','--tb=short','--show-capture=no','-p','no:cacheprovider']+[str(code/'05_TESTS/CONTRACTS'/x) for x in tests],plugins=[p])
imports={n:str(Path(m.__file__).resolve()) for n,m in list(sys.modules.items()) if n.split('.')[0] in ('semantic_runtime','lawrag') and getattr(m,'__file__',None)}
leaks={n:v for n,v in imports.items() if not Path(v).is_relative_to(code)}
def write(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
write(art/(name+'-imports.json'),{'candidate_root':str(code.relative_to(ROOT)),'all_runtime_imports':imports,'actual_API_tests':p.api})
write(art/(name+'-summary.json'),{'status':status,'elapsed_seconds':round(time.monotonic()-start,3),'passed':sum(r['outcome']=='passed' for r in p.rows),'failed':sum(r['outcome']=='failed' for r in p.rows),'test_files':tests,'candidate_root':str(code.relative_to(ROOT)),'production_import_leaks':leaks,'rows':p.rows,'live_model_calls':0,'real_source_database_opened':False})
print('IMPORT_CHECK',len(imports),'modules; leaks',len(leaks))
sys.exit(status or bool(leaks))
