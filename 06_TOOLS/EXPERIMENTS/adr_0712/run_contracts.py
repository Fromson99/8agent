from pathlib import Path
import json,subprocess,hashlib,sys,os
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0712-compact-direct-read-context';C=R/'02_BACKEND/lawrag/research/candidates/adr_0712/compact';cm=json.loads((C/'candidate.json').read_text());s=C/'revisions'/cm['revisions'][-1]['revision_id']/'snapshot'
for f in cm['revisions'][-1]['files']:
 assert hashlib.sha256((R/f['frozen_path']).read_bytes()).hexdigest()==f['snapshot_sha256'], f['frozen_path']
D=A/'artifacts/contracts';D.mkdir(exist_ok=True)
names=['test_exception_wire.py','test_genos_full_error_log.py','test_main_workflow_display.py','test_standalone_current_judgment.py','test_genos_answer_stream.py','test_rag_flow_svg.py','test_judgment_loop_recovery.py','test_investigation_completion_adr0678.py','test_completion_boundary_adr0679.py','test_followup_structure_lookup.py','test_law_grouped_navigation.py','test_law_navigation_state_contract_adr0661.py','test_completion_v4.py','test_structure_reading.py','test_wire_repair.py','test_public_display_boundary.py','test_document_focus.py','test_named_menu.py','test_compact_metrics.py']
testroot=R/'02_BACKEND/lawrag/research/candidates/adr_0704/compact-display/revisions/rev-006/snapshot'
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py',str(s),*[str(testroot/'05_TESTS/CONTRACTS'/p) for p in names],str(R/'06_TOOLS/EXPERIMENTS/adr_0707/test_entry.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0707/test_title_search.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0712/test_compact_input.py'),'-k','not test_completion_preserves_correction_table_history_and_experience','--junitxml='+str(D/'required.xml')]
with (D/'required.log').open('w') as out:r=subprocess.run(cmd,cwd=R,stdout=out,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONPATH':str(R/'05_TESTS/CONTRACTS')+':'+str(R/'05_TESTS/REGRESSION/core')})
print('Required contracts exit',r.returncode);raise SystemExit(r.returncode)
