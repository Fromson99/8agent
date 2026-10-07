from pathlib import Path
import sys, importlib
sys.dont_write_bytecode=True
root=Path(__file__).resolve().parents[3]
code=root/'02_BACKEND/lawrag/research/candidates/adr_0676/integrated/revisions/rev-001/snapshot'
sys.path.insert(0,str(code/'02_BACKEND'));sys.path.insert(0,str(root/'05_TESTS/CONTRACTS'));sys.path.insert(0,str(code/'05_TESTS/CONTRACTS'));sys.path.insert(0,str(root/'05_TESTS'))
import semantic_runtime
assert str(code) in semantic_runtime.__file__
for name in ('lawrag','lawrag.pipeline'):
 package=importlib.import_module(name);package.__path__.append(str(root/'02_BACKEND'/name.replace('.','/')))
import pytest
files=['test_chain_parent_collision_adr0672.py','test_investigation_chain_adr0671.py','test_selection_tool_contracts_adr0665.py','test_search_question_boundary_adr0662.py','test_law_navigation_state_contract_adr0661.py','test_law_grouped_navigation.py']
files += ['test_investigation_control_adr0674.py','test_investigation_reinspection_adr0676.py','test_law_navigation_patch_repair_adr0664.py','test_law_navigation_one_repair_adr0663.py']
files += ['test_ad_language.py','test_ad_table_context.py','test_genos_latest_service_layout.py','test_shortcut_schema_draft.py']
paths=[str(code/'05_TESTS/CONTRACTS'/f) if (code/'05_TESTS/CONTRACTS'/f).exists() else str(root/'05_TESTS/CONTRACTS'/f) for f in files]
excluded=[
 ('test_law_navigation_patch_repair_adr0664.py','test_partial_patch_recovers_actual_select_path_once'),
 ('test_law_navigation_patch_repair_adr0664.py','test_bad_partial_patch_is_never_executed'),
 ('test_law_navigation_one_repair_adr0663.py','test_actual_previous_conflict_schema_requires_changed_decision'),
 ('test_law_navigation_one_repair_adr0663.py','test_repair_then_execute_reads_only_corrected_decision'),
 ('test_law_navigation_one_repair_adr0663.py','test_second_invalid_is_saved_and_resume_cannot_retry_again')]
args=['-q','--tb=short']+paths
for f,name in excluded:args+=['--deselect',str((code/'05_TESTS/CONTRACTS'/f).relative_to(root))+'::'+name]
raise SystemExit(pytest.main(args,plugins=[importlib.import_module('conftest')]))
