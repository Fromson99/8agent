from pathlib import Path
import ast
R=Path(__file__).resolve().parents[3]
old=(R/'05_TESTS/CONTRACTS/test_genos_full_error_log.py').read_text();tree=ast.parse(old)
kept=['test_rejected_decision_is_rendered_as_full_error_before_generic_decision','test_rejected_decisions_survive_pending_and_recovered_selection','test_async_logger_never_drops_oversized_errors','test_capture_and_readable_report_keep_complete_exception']
functions=['\n'.join(old.splitlines()[n.lineno-1:n.end_lineno]) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in kept]
for arm in ['safe-display','consistent-judgment']:
 s=R/'02_BACKEND/lawrag/research/candidates/adr_0693'/arm/'snapshot'
 p=s/'05_TESTS/CONTRACTS/test_genos_full_error_log.py'
 p.write_text((R/'06_TOOLS/EXPERIMENTS/adr_0693/test_public_boundary.py').read_text()+'''\nimport sys
from semantic_runtime.request_report import format_readable_report
from semantic_runtime.legal_agent.investigation_diagnostics import selection_report
from semantic_runtime.legal_agent.readable_log import render_detail
'''+ '\n\n'+ '\n\n'.join(functions).replace("payload()['diagnostics']","{'cause':LONG}")+'\n')
 p=s/'05_TESTS/CONTRACTS/test_main_workflow_display.py';t=p.read_text().replace("assert raw == {'status': 500, 'body': {'error': 'synthetic failure', 'detail': detail}}", "assert raw['status']==500 and raw['body']['answer_status']=='failed'\n    assert 'ERROR_END' not in json.dumps(raw)")
 t=t.replace("assert 'ERROR_END' in provided['text'] and 'x' * 45000 in provided['text']", "assert 'ERROR_END' not in provided['text'] and '조회 번호' in provided['text']")
 p.write_text(t)
 p=s/'05_TESTS/CONTRACTS/test_standalone_current_judgment.py';t=p.read_text().replace("'basis':{'stage':'ASSESS','state':'COMPLETED','detail_mode':'judgment'}", "'basis':{'kind':'CASE_JUDGMENT_ACCEPTED','stage':'ASSESS','state':'COMPLETED','detail_mode':'judgment'}");p.write_text(t)
