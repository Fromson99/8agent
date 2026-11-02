from pathlib import Path
import json,sys,importlib.util
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1235-gold-ontology-transport-live';D=A/'artifacts/design';P=R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
def read(p):return json.loads(p.read_text())
F=R/read(D/'candidate.json')['snapshot'];spec=importlib.util.spec_from_file_location('gold_preflight',F/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py');gold=importlib.util.module_from_spec(spec);spec.loader.exec_module(gold);gold.HERE=P;gold.ROOT=R
with gold.open_store(mapping=P/'mapping_local_dtls_current.json',mapping_sha256=read(D/'before.json')['active_mapping']['sha256'],ontology_settings=F/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/ontology_settings.json',documents=['7bbe815ff43b6635']) as (store,req,transport):
 policy=store.gold_profile['candidate_navigation'];assert policy['ontology_enabled'] is True and policy['ontology_context']=={'mode':'DB'};store.selection.require_latest()
 out={'passed':True,'physical_mapping':store.gold_ports.preflight,'ontology_enabled':True,'mode':'DB','sql_calls':len(transport.statements),'model_calls':0};(D/'preflight.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out))
