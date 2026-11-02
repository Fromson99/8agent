from pathlib import Path
import json,sys,importlib.util,hashlib,ast
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1245-main128-oracle-records-live';D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
F=R/read(D/'candidate.json')['snapshot'];spec=importlib.util.spec_from_file_location('gold_preflight',F/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py');gold=importlib.util.module_from_spec(spec);spec.loader.exec_module(gold);gold.ROOT=R;gold.ACTIVE_POINTER=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
ast.parse((R/read(D/'candidate.json')['entry']).read_text())
with gold.open_store(documents=read(D/'cases.json')[0]['request']['json']['document_ids']) as (store,req,transport):
 policy=store.gold_profile['candidate_navigation'];assert policy['ontology_enabled'] is True and policy['ontology_context']=={'mode':'DB'};store.selection.require_latest()
 import semantic_runtime
 assert Path(semantic_runtime.__file__).is_relative_to(R/gold.engine_binding()['engine_root'])
 out={'passed':True,'physical_mapping':store.gold_ports.preflight,'ontology_enabled':True,'mode':'DB','sql_calls':len(transport.statements),'model_calls':0,'engine_files':len(gold.engine_binding()['engine_files']),'engine_release':gold.engine_binding()['engine_release_id'],'runtime_source':str(Path(semantic_runtime.__file__).relative_to(R))}
 write_summary(D/'preflight.json',out);print(json.dumps({k:v for k,v in out.items() if k!='physical_mapping'}))
