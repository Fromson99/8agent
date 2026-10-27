"""Sequential bounded synthetic contract suite; no external calls/corpus loading."""
from pathlib import Path
import os,subprocess,sys
ROOT=Path(__file__).resolve().parents[3]
CODE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1065/task-local-r1/snapshot'
ART=ROOT/'04_EXPERIMENTS/ADR/ADR-1065-ontology-task-local-navigation/artifacts'
TESTS=[
 'test_guidance_binding_adr1059.py','test_navigation_values_adr1058.py',
 'test_model_input_projection_adr1047.py','test_navigation_input_audit_budget.py',
 'test_compact_input_adr1044.py','test_model_binding_adr1054.py','test_final_input_budget.py',
 'test_shared_input_values.py','test_state_format_schema_adr1047.py','test_stage_guidance_adr1047.py',
 'test_read_judgment_api.py','test_grouped_query_adr1056.py','test_query_literal_adr1057.py',
 'test_step_state_adr1053.py','test_output_key_aliases.py','test_output_contract_recovery.py',
 'test_ontology_compiler.py','test_ontology_context.py','test_ontology_api.py',
 'test_law_overview_adr1052.py','test_progressive_clauses_adr1051.py','test_read_judgment.py',
 'test_buffered_json_stream.py','test_buffered_external_transport.py','test_response_reception_state.py',
 'test_provider_failover_adr1049.py','test_definition_context.py','test_legal_agent_v5.py',
 'test_investigation_scope_recovery.py',
]
TESTS+=sorted(p.name for p in (CODE/'05_TESTS/CONTRACTS').glob('*_adr1061.py'))
TESTS+=sorted(p.name for p in (CODE/'05_TESTS/CONTRACTS').glob('*_adr1062.py'))
TESTS+=sorted(p.name for p in (CODE/'05_TESTS/CONTRACTS').glob('*_adr1063.py'))
TESTS+=sorted(p.name for p in (CODE/'05_TESTS/CONTRACTS').glob('*_adr1065.py'))
if __name__=='__main__':
 name=sys.argv[1] if len(sys.argv)>1 else 'release-check'
 with (ART/(name+'.log')).open('x') as log:
  result=subprocess.run([str(ROOT/'.venv/bin/python'),'-B',str(Path(__file__).with_name('validate_candidate.py')),str(CODE),name,*TESTS],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','MALLOC_ARENA_MAX':'1'})
 print(name,'exit',result.returncode,flush=True)
 raise SystemExit(result.returncode)
