#!/usr/bin/env python3
"""Run offline recovery contracts against an explicit code root, serially.

Output distinguishes API answer recovery, controlled stops and component guards.
Never calls a model service or changes the selected release.
"""
from pathlib import Path
import argparse
import hashlib
import importlib
import json
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--code-root', type=Path, default=ROOT)
parser.add_argument('--output', type=Path, required=True, help='new directory for this invocation')
parser.add_argument('--api-only', action='store_true')
args = parser.parse_args()
code = args.code_root.resolve()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
runtime = out/'runtime'
os.environ.update(WORKFLOW_TEST_CODE_ROOT=str(code), LOOP_TEST_CODE_ROOT=str(code),
    GENOS_AUTO_WARMUP='0', AD_WORKER_ENABLED='0')
os.environ.pop('DP',None)
sys.dont_write_bytecode = True
sys.path[:0] = [str(code/'02_BACKEND'), str(code), str(ROOT/'05_TESTS'), str(ROOT/'05_TESTS/CONTRACTS')]
# Release snapshots intentionally omit fixture builders. Their fallback is
# limited to authoring helpers; semantic_runtime always comes from code root.
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for name in ('pipeline','core'):
    package=importlib.import_module('lawrag.'+name)
    package.__path__.append(str(ROOT/'02_BACKEND/lawrag'/name))
import conftest
import pytest
# conftest offers legacy test-only tool imports; selected product imports retain priority.
sys.path[:0] = [str(code/'02_BACKEND'), str(code)]
import semantic_runtime.legal_agent.gateway as gateway
assert Path(gateway.__file__).resolve().is_relative_to(code/'02_BACKEND')

files = ['05_TESTS/CONTRACTS/test_agent_loop_fault_recovery.py']
if not args.api_only:
    files += ['05_TESTS/CONTRACTS/'+name for name in (
        'test_scope_review.py','test_scope_review_api.py','test_need_continuity_api.py',
        'test_read_judgment_keep_recovery.py','test_output_contract_recovery.py',
        'test_gateway_response_binding_failure.py','test_genos_model_stream_completion.py',
        'test_request_resume_stop.py','test_shortcut_owner_transition.py',
        'test_research_state_owner.py','test_tool_failure_matrix.py',
        'test_judgment_loop_recovery.py','test_investigation_scope_recovery.py',
        'test_read_judgment_api.py','test_legal_agent_double_harness.py',
        'test_selection_contract_versions.py','test_source_target_coordinate.py',
        'test_need_continuity.py')]
    files += ['05_TESTS/CONTRACTS/test_main50_request_repair.py::'+name for name in (
        'test_native_transient_read_failure_offers_different_route_without_false_adoption',
        'test_accepted_batch_resume_keeps_completed_target_receipts',
        'test_transient_partial_batch_retains_completed_original_without_adoption',
        'test_interrupted_corrective_transport_resumes_original_view_without_third_call',
        'test_recoverable_failure_invalidates_pre_failure_state_version',
        'test_exact_failed_search_is_blocked_but_new_expression_can_execute',
        'test_failed_tool_receipt_never_satisfies_missing_target',
        'test_wrapped_integrity_and_unknown_model_outcomes_are_not_source_recovery')]

def hashes():
    paths = [p
        for folder in ('02_BACKEND/semantic_runtime','02_BACKEND/ENGINES','00_SYSTEM/LEGAL_AGENT')
        for p in sorted((code/folder).rglob('*')) if p.is_file() and p.suffix in ('.py','.json')]
    paths.append(code/'00_SYSTEM/PIPELINE.json')
    return {str(p.relative_to(code)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

before = hashes()
active = ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
active_hash = hashlib.sha256(active.read_bytes()).hexdigest()
rows = []
class Results:
    def pytest_runtest_logreport(self, report):
        if report.when == 'call' or report.failed:
            rows.append({'test':report.nodeid,'when':report.when,'outcome':report.outcome,
                'error':report.longreprtext if report.failed else None})

started = time.monotonic()
status = pytest.main(['--noconftest','-c','/dev/null','-q','--tb=short','--show-capture=no',
    '--rootdir='+str(ROOT),'-p','no:cacheprovider','--basetemp='+str(runtime),
    *[str(ROOT/f) for f in files]], plugins=[conftest, Results()])
outcomes = [json.loads(p.read_text()) for p in sorted(runtime.glob('*/loop-outcome.json'))
    if not p.parent.name.endswith('current')]
result = {'code_root':str(code),'gateway_origin':str(Path(gateway.__file__).resolve()),
    'code_hashes_before':before,'code_unchanged':before==hashes(),
    'active_pointer_unchanged':active_hash==hashlib.sha256(active.read_bytes()).hexdigest(),
    'elapsed_seconds':round(time.monotonic()-started,3),'exit_code':int(status),
    'passed':sum(r['outcome']=='passed' for r in rows),'failed':sum(r['outcome']=='failed' for r in rows),
    'real_model_calls':0,'rows':rows,'api_outcomes':outcomes,
    'semantic_module_origins':{name:str(Path(module.__file__).resolve())
        for name,module in sys.modules.items()
        if name.startswith('semantic_runtime') and getattr(module,'__file__',None)},
    'interpretation':'Controlled-stop cases are not successful answer recovery; no live-model quality claim.'}
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
if (not result['code_unchanged'] or not result['active_pointer_unchanged']
        or any(not Path(path).is_relative_to(code/'02_BACKEND')
            for path in result['semantic_module_origins'].values())):
    raise SystemExit('Code or selection changed while testing; result is not a fixed-code verification')
raise SystemExit(int(status))
