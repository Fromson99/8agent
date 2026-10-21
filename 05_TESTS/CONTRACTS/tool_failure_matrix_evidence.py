"""Pytest evidence projection; the design catalogue is never runtime config.

Optional pytest plugin: set TOOL_FAILURE_EVIDENCE_PATH and load with -p.
Existing JUnit runs can be projected with from_junit/build_report without reruns.
Missing, skipped and deferred scenarios are explicitly NOT_RUN, never PASS.
"""
import gzip
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
DESIGN=ROOT/'07_DOCS/REFERENCE/REPORTS/TOOL_FAILURE_RECOVERY_DESIGN_20261014'
PREFIX='05_TESTS/CONTRACTS/'
EXTRA={
 'F01':['test_tool_failure_matrix.py::test_all_choices_availability_and_binding','test_container_article_read.py::test_api_container_original_reaches_answer_and_duplicate_reuses_result'],
 'F03':['test_tool_failure_matrix.py::test_all_choices_availability_and_binding','test_tool_failure_matrix.py::test_f46_policy_checkpoint_preserves_legacy_and_rejects_drift'],
 'F04':['test_investigation_completion_adr0678.py::test_same_request_retries_keep_budget_and_original_deadline','test_tool_failure_matrix.py::test_f12_failed_read_reservation_stays_spent'],
 'F05':['test_tool_failure_matrix.py::test_f05_legacy_result_does_not_invent_execution','test_tool_failure_matrix.py::test_f05_native_failure_receipt_replay_and_budget','test_tool_failure_matrix.py::test_f05_handler_result_cause_survives_wrappers','test_tool_failure_matrix.py::test_f05_rejected_before_execution_does_not_spend_or_run','test_tool_failure_matrix.py::test_f05_v1_source_result_keeps_sql_cause','test_tool_failure_matrix.py::test_f05_v2_relations_result_keeps_sql_cause','test_tool_failure_matrix.py::test_f05_unsuccessful_handler_never_commits_returned_evidence'],
 'F06':['test_tool_failure_matrix.py::test_f06_hard_nested_cause_overrides_transient','test_tool_failure_matrix.py::test_f06_sql_codes_are_structured'],
 'F07':['test_tool_failure_matrix.py::test_f07_only_distinct_alternative_and_existing_budget'],
 'F12':['test_tool_failure_matrix.py::test_f12_partial_read_retains_pages_and_exact_continuation','test_tool_failure_matrix.py::test_f12_partial_result_needs_actual_receipt'],
 'F13':['test_tool_failure_matrix.py::test_f13_missing_terminal_is_unknown_and_never_replayed','test_tool_failure_matrix.py::test_f13_receipt_failure_preserves_unknown_and_original_cause','test_tool_failure_matrix.py::test_f13_intent_storage_failure_never_dispatches'],
 'F18':['test_investigation_completion_adr0678.py::test_read_is_separate_from_adopt_or_defer'],
 'F22':['test_bounded_wiki_recall.py::test_access_and_currentness_before_exposure','test_bounded_wiki_recall.py::test_existing_decision_can_abstain_or_choose_and_revalidate'],
 'F26':['test_investigation_completion_adr0678.py::test_known_429_retries_once_with_original_status','test_genos_answer_stream.py::test_genos_stream_model_metadata_does_not_block_display'],
 'F27':['test_ad_request_reports.py::test_legal_and_ad_share_wire_contract_and_omit_unsupported_keyword'],
 'F33':['test_exception_wire.py::test_wire_binds_nonempty_exceptions_to_source_status','test_exception_wire.py::test_empty_exceptions_stay_uncertain_and_cannot_claim_source_exceptions','test_main50_request_repair.py::test_unknown_nested_evidence_and_fabricated_user_fact_rejected'],
 'F37':['test_memory_runtime_v2.py::test_duplicate_id_and_revision_conflict','test_genos_failure_boundaries.py::test_duplicate_active_request_is_409_without_dispatch'],
 'F38':['test_successful_shortcut.py::test_publication_matrix','test_legal_agent_failures.py::test_wrong_generation_request_binding_is_immutable'],
 'F39':['test_legal_agent_failures.py::test_publication_no_clobber_and_idempotent_export','test_legal_agent_failures.py::test_publication_conflict_preserves_both_journal_and_existing_result','test_legal_agent_failures.py::test_recover_commit_ready_before_or_after_file_install','test_successful_shortcut.py::test_receipt_rolls_back_with_core_failure'],
 'F46':['test_tool_failure_matrix.py::test_f46_policy_checkpoint_preserves_legacy_and_rejects_drift'],
 'F47':['test_genos_compact_service_boot.py::test_real_compact_service_boot_search_and_tamper_rejection','test_investigation_diagnostics.py::test_http_failure_keeps_source_cause_through_native_runtime'],
 'F48':['test_tool_failure_matrix.py::test_all_choices_hard_failure_never_retries'],
 'F49':['test_investigation_scope_recovery.py::test_terminal_keeps_cause_but_cannot_repair_again','test_investigation_scope_recovery.py::test_actual_api_normal_repair_and_failure'],
}
EXTRA['F04'].append('test_tool_failure_matrix.py::test_f04_reference_budget_changed_after_menu_stays_budget_failure')
EXTRA['F07'].append('test_tool_failure_matrix.py::test_f07_same_tool_different_target_is_distinct_operation')
EXTRA['F06'].extend(['test_tool_failure_matrix.py::test_f06_schema_proposal_keeps_existing_repair_owner',
                     'test_tool_failure_matrix.py::test_f06_implicit_hard_cause_cannot_be_hidden_by_cleanup_timeout'])
POLICY_TEST='05_TESTS/CONTRACTS/test_tool_failure_matrix.py::test_all_choices_availability_and_binding'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def binding(root=ROOT):
    paths=sorted((root/'02_BACKEND/semantic_runtime').rglob('*.py'))+sorted((root/'02_BACKEND/ENGINES').rglob('*.json'))+[root/'00_SYSTEM/PIPELINE.json']
    return {str(p.relative_to(root)):sha(p) for p in paths}


def from_junit(path):
    results={}
    for case in ET.parse(path).iter('testcase'):
        name=case.attrib['classname'].replace('.','/')+'.py::'+case.attrib['name']
        status='FAIL' if case.find('failure') is not None or case.find('error') is not None else 'NOT_RUN' if case.find('skipped') is not None else 'PASS'
        results[name]={'status':status,'observations_ref':str(path),'fixture_binding':case.attrib['name']}
    return results


def status_for(nodeids,results):
    found=[];missing=[]
    for node in nodeids:
        matched=[n for n in results if n==node or n.startswith(node+'[')]
        found.extend(matched)
        if not matched:missing.append(node)
    if any(results[n]['status']=='FAIL' for n in found):status='FAIL'
    elif missing or not found or any(results[n]['status']!='PASS' for n in found):status='NOT_RUN'
    else:status='PASS'
    return status,sorted(set(found)),missing


def build_report(results,code_binding,*,root=ROOT):
    design=root/'07_DOCS/REFERENCE/REPORTS/TOOL_FAILURE_RECOVERY_DESIGN_20261014'
    matrix=json.loads((design/'FAILURE_MATRIX.json').read_text())
    catalogue=json.loads((design/'POLICY_DESIGN.json').read_text())
    signature=hashlib.sha256(json.dumps(code_binding,sort_keys=True).encode()).hexdigest()
    drift=[name for name,expected in code_binding.items() if not (root/name).is_file() or sha(root/name)!=expected]
    scenarios=[]
    for case in matrix['cases']:
        nodes=list(dict.fromkeys(case['existing_test_references']+[PREFIX+n for n in EXTRA.get(case['id'],[])]))
        status,found,missing=status_for(nodes,results)
        deferred=case['implementation_package'] not in ('P1','P2','P3')
        scenarios.append({'case_id':case['id'],'choice_key':None,'implementation_package':case['implementation_package'],
            'status':'NOT_RUN' if deferred or drift else status,'test_nodeid':found,
            'code_binding_sha256':signature,'fixture_binding':'synthetic sources / scripted transport',
            'environment':'WSL local; GENOS not accessed','observations_ref':'test_results',
            'reason':'후속 패키지 미구현; 연결된 기존 회귀 검사는 별도 보존' if deferred else
                     '검사 후 코드 지문 변경' if drift else '누락 또는 건너뛴 검사' if status=='NOT_RUN' else None,
            'missing_tests':missing,'scope':'linked assertions only; not every possible failure combination'})
    cells=[]
    for choice in catalogue['choices']:
        for case_id in choice['planned_matrix']:
            # Per-choice policy proofs do not certify a domain mutation or the
            # full tool-by-scenario cartesian product. Keep untested cells open.
            nodes=([POLICY_TEST+'['+choice['key']+']'] if case_id in ('F01','F02','F03','F04') else
                   [PREFIX+'test_tool_failure_matrix.py::test_all_choices_hard_failure_never_retries['+kind+'-'+choice['key']+']'
                    for kind in ('AUTH','INTEGRITY','STATE','UNKNOWN','INTERNAL','DEADLINE')] if case_id in ('F06','F48') else [])
            status,found,missing=status_for(nodes,results)
            cells.append({'case_id':case_id,'choice_key':choice['key'],'status':'NOT_RUN' if drift else status,
                'test_nodeid':found,'code_binding_sha256':signature,'fixture_binding':'policy state fixture',
                'environment':'WSL local','observations_ref':'test_results','coverage_level':'POLICY_ONLY',
                'reason':None if status=='PASS' and not drift else '개별 도구×시나리오 실행 증거 없음; family 검사로 대체 통과시키지 않음'})
    return {'schema_version':'tool-failure-test-evidence-v1','code_binding_sha256':signature,'code_binding':code_binding,
        'code_drift':drift,'scenario_count':len(scenarios),'choice_count':len(catalogue['choices']),
        'scenario_status_counts':{s:sum(x['status']==s for x in scenarios) for s in ('PASS','FAIL','NOT_RUN')},
        'scenarios':scenarios,'choice_policy_cells':cells,'test_results':results,
        'limits':['합성 계약 검사이며 모델 판단 품질·GENOS 현장 성능 인증 아님','POLICY_ONLY는 개별 handler의 모든 실패를 실행했다는 뜻이 아님']}


def write_report(path,report):
    raw=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode()
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(gzip.compress(raw,mtime=0) if path.suffix=='.gz' else raw)


_results={};_binding=None

def pytest_configure(config):
    global _binding
    if os.environ.get('TOOL_FAILURE_EVIDENCE_PATH'):_binding=binding()


def pytest_runtest_logreport(report):
    if _binding is None:return
    if report.when=='call' or report.failed or report.skipped:
        previous=_results.get(report.nodeid,{})
        status='FAIL' if report.failed or previous.get('status')=='FAIL' else 'NOT_RUN' if report.skipped else 'PASS'
        _results[report.nodeid]={'status':status,'observations_ref':'pytest:'+report.nodeid,
                                 'fixture_binding':report.nodeid}


def pytest_sessionfinish(session,exitstatus):
    if _binding is not None:write_report(os.environ['TOOL_FAILURE_EVIDENCE_PATH'],build_report(_results,_binding))
