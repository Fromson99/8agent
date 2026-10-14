from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0700-named-document-menu-preservation';C=R/'02_BACKEND/lawrag/research/candidates/adr_0700/preserved';D=A/'artifacts/contracts';D.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=C/'candidate.json';cm=json.loads(p.read_text());rev=cm['revisions'][-1];s=C/'revisions'/rev['revision_id']/'snapshot';runner=R/'06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py'
b={'candidate_id':'preserved','experiment_id':'ADR-0700-experiment-v1','arm_id':'preserved','run_ids':['run-001'],'manifest_path':str(p.relative_to(R)),'manifest_sha256':sha(p),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)}
p=A/'실험/manifest.json';m=json.loads(p.read_text());m['design']['code_isolation']['candidates']=[b];p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
(D/'bindings.json').write_text(json.dumps(b,indent=2)+'\n')
files=['test_genos_full_error_log.py','test_main_workflow_display.py','test_standalone_current_judgment.py','test_genos_answer_stream.py','test_rag_flow_svg.py','test_judgment_loop_recovery.py','test_investigation_completion_adr0678.py','test_completion_boundary_adr0679.py','test_structure_first_search.py','test_followup_structure_lookup.py','test_unit_fulltext_adaptive_read.py','test_law_grouped_navigation.py','test_law_navigation_state_contract_adr0661.py']
cmd=[str(R/'.venv/bin/python'),str(runner),str(s),*[str(s/'05_TESTS/CONTRACTS'/p) for p in files],str(R/'06_TOOLS/EXPERIMENTS/adr_0693/test_completion_v4.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0689/test_review_repairs.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0694/test_structure_reading.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0696/test_wire_repair.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0698/test_document_focus.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0700/test_named_menu.py'),'-k','not test_completion_preserves_correction_table_history_and_experience','--junitxml='+str(D/'structured-reading.xml')]
with (D/'structured-reading.log').open('w') as f:r=subprocess.run(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT)
print('Final contracts exit:',r.returncode);raise SystemExit(r.returncode)
