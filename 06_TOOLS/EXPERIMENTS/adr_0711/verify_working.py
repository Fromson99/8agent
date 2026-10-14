from pathlib import Path
import json,subprocess,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0711-compact-selection-source-input';D=A/'artifacts/design'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
f=read(D/'freeze.json')
for p,h in f['serving_files'].items():assert sha(R/p)==h,p
names=['test_exception_wire.py','test_genos_full_error_log.py','test_main_workflow_display.py','test_standalone_current_judgment.py','test_genos_answer_stream.py','test_rag_flow_svg.py','test_judgment_loop_recovery.py','test_investigation_completion_adr0678.py','test_completion_boundary_adr0679.py','test_followup_structure_lookup.py','test_law_grouped_navigation.py','test_law_navigation_state_contract_adr0661.py','test_completion_v4.py','test_structure_reading.py','test_wire_repair.py','test_public_display_boundary.py','test_document_focus.py','test_named_menu.py','test_compact_metrics.py']
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py',str(R),*[str(R/'05_TESTS/CONTRACTS'/n) for n in names],str(R/'06_TOOLS/EXPERIMENTS/adr_0707/test_entry.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0707/test_title_search.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0711/test_compact_input.py'),'-k','not test_completion_preserves_correction_table_history_and_experience','--junitxml='+str(A/'artifacts/working-required.xml')]
with (A/'artifacts/working-required.log').open('w') as out:run=subprocess.run(cmd,cwd=R,stdout=out,stderr=subprocess.STDOUT)
print('Identical working serving files verified; focused contracts exit',run.returncode);raise SystemExit(run.returncode)
