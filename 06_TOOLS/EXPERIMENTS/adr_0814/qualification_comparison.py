"""Frozen finite comparison/recovery contracts; synthetic proposals, no retrieval.

This runner does not grade legal meaning. The same descriptors and oracle are
used for each code root. Only the arm's declared dimension inventory is adapted;
an unsupported status is never rewritten into a passing status.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib
import json
import os
from pathlib import Path
import resource
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[3]
DESIGN = ROOT / '04_EXPERIMENTS/ADR/ADR-0814-evidence-completeness-qualification/artifacts/design'
COMMON_DIMENSIONS = ('definition', 'numerator', 'denominator', 'scope', 'unit',
                     'period', 'date', 'exceptions', 'direction')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def hashed(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def describe_error(exc):
    return {'type': type(exc).__name__, 'code': getattr(exc, 'code', type(exc).__name__),
            'message': getattr(exc, 'message', str(exc))}


def load_runtime(code_root):
    """Bind product modules to the requested arm before importing any of them."""
    sys.dont_write_bytecode = True
    os.environ.update(SOURCE_PROVIDER_PROJECT_ROOT=str(ROOT), LAWRAG_WORKSPACE_ROOT=str(ROOT),
                      LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT), LAWRAG_TOKEN_TEST_REPOSITORY=str(ROOT))
    sys.path[:0] = [str(code_root / '02_BACKEND'), str(code_root), str(ROOT / '02_BACKEND')]
    # Shared ancillary modules are not part of the changed serving bundle.
    # Selected arm paths always precede their workspace fallback.
    for name in ('lawrag', 'lawrag.pipeline', 'lawrag.core', 'lawrag.core.structure'):
        module = importlib.import_module(name)
        module.__path__.insert(0, str(code_root / '02_BACKEND' / name.replace('.', '/')))
        module.__path__.append(str(ROOT / '02_BACKEND' / name.replace('.', '/')))
    from jsonschema import validate as schema_validate, ValidationError
    from workflow.risk_team_compare_workflow import compare, contracts
    from workflow.adapters.model import ModelAdapter
    from workflow.repository import Repository
    from workflow.contracts import WorkflowError
    from semantic_runtime.legal_agent.bounded_source_session import _Protocol
    from semantic_runtime.legal_agent.context import RequestContext
    from semantic_runtime.legal_agent.errors import ContractError, ProposalError
    from semantic_runtime.legal_agent.output_contract import strict_json, validate_shape
    from semantic_runtime.legal_agent.repository import WorkRepository
    return locals()


def verify_imports(code_root):
    files = {name: str(Path(module.__file__).resolve()) for name, module in list(sys.modules.items())
             if (name == 'workflow' or name.startswith('workflow.') or
                 name == 'semantic_runtime' or name.startswith('semantic_runtime.'))
             and getattr(module, '__file__', None)}
    foreign = {name: path for name, path in files.items() if not Path(path).is_relative_to(code_root)}
    if foreign:
        raise RuntimeError('qualification imported an unselected runtime: ' + encoded(foreign))
    return files


def record(case, started):
    return {'case_id': case['case_id'], 'passed': False, 'checks': {}, 'available': [], 'presented': [],
            'executed_retrieval': False, 'skip_reason': 'Fixed proposals no retrieval',
            'elapsed_seconds': time.perf_counter() - started, 'tool_calls': 0, 'stub_model_calls': 0,
            'fixture_hash': hashed(case)}


def comparison_case(runtime, case, fixture):
    started = time.perf_counter()
    result = record(case, started)
    declarations = tuple(runtime['contracts'].DIMENSIONS)
    supplied = case['dimension_statuses']
    # The prospective descriptor names both common dimensions and the new value
    # capability. The code root only chooses which declared names it can read.
    unmapped = sorted(set(declarations) - set(supplied))
    if unmapped:
        raise RuntimeError('descriptor has no independent observation for dimensions: ' + repr(unmapped))
    evidence = deepcopy(fixture['evidence'])
    citations = [{'evidence': source['evidence_id'], 'quote': source['spans'][0]['text']}
                 for source in evidence]
    pair = deepcopy(fixture['pair'])
    pair['applicability']['citations'] = deepcopy(citations)
    pair['content_citations'] = deepcopy(citations)
    row = {'pair_id': pair['pair_id'], 'item': fixture['issue']['label'], 'verdict': case['verdict'],
           'difference': '고정된 모의 차원 관측의 필드 일관성만 확인합니다.',
           'reason': '이 제안은 법률 의미나 수치 방향의 정답을 주장하지 않습니다.',
           'citations': deepcopy(citations), 'numeric': True,
           'dimensions': [{'name': name, 'status': supplied[name], 'citations': deepcopy(citations),
                           'reason': '이 차원의 상태는 사전 고정한 모의 관측입니다.'} for name in declarations],
           'unresolved': ['모의 미확인 범위 보존'] if case['verdict'] in ('POSSIBLE_GAP', 'DEFERRED') else []}
    proposal = {'rows': [row], 'answer': '모의 계약 검사', 'unresolved': deepcopy(row['unresolved'])}
    before = hashed([evidence, pair, proposal])
    accepted = False
    rejection = None
    try:
        runtime['schema_validate'](proposal, runtime['contracts'].COMPARE)
        runtime['compare'].validate(proposal, evidence, {'pairs': [pair]}, [fixture['issue']])
        accepted = True
    except (ValueError, runtime['ValidationError']) as exc:
        rejection = describe_error(exc)
    result['checks'] = {
        'acceptance_matches_frozen_field_oracle': accepted is case['expected_accept'],
        'common_dimensions_preserved': all(name in declarations for name in COMMON_DIMENSIONS),
        'statuses_not_inferred_or_rewritten': all(d['status'] == supplied[d['name']] for d in row['dimensions']),
        'pure_validation_preserves_inputs': before == hashed([evidence, pair, proposal]),
        'no_retrieval_or_model_calls': True,
    }
    result['observed'] = {'accepted': accepted, 'expected_accept': case['expected_accept'],
                          'declared_dimensions': list(declarations),
                          'additional_dimension_capabilities': sorted(set(declarations) - set(COMMON_DIMENSIONS)),
                          'unsupported_descriptor_dimensions': sorted(set(supplied) - set(declarations)),
                          'dimension_pattern': case['dimension_pattern'], 'verdict': case['verdict'],
                          'validation_error': rejection, 'legal_correctness_scored': False}
    result['proposal_hash'] = hashed(proposal)
    result['passed'] = all(result['checks'].values())
    if not result['passed']:
        result['error'] = rejection or {'type': 'ContractOracleMismatch', 'message': 'Accepted a field-inconsistent proposal.'}
    result['elapsed_seconds'] = time.perf_counter() - started
    return result


class InterruptedAfterRaw(BaseException):
    """A controlled process-death boundary, before proposal acceptance."""


def recovery_case(runtime, case, fixture, output_dir):
    started = time.perf_counter()
    result = record(case, started)
    schema = deepcopy(fixture['schema'])
    data = deepcopy(fixture['data'])
    data['qualification_case'] = case['case_id']
    proposals = [{'value': value} for value in case['proposal_values']]
    original_proposals = deepcopy(proposals)

    class Services:
        ProposalError = runtime['ProposalError']

        def __init__(self):
            self.calls = []
            self.interrupt = case['interruption'] == 'after_raw'

        def recover_response(self, raw, response_schema):
            if raw['model'] != fixture['model_id']:
                raise runtime['ContractError']('synthetic response binding changed')
            value = runtime['strict_json'](raw['content'])
            runtime['validate_shape'](value, response_schema)
            return value

        def structured(self, work, context, stage, call_id, request_data, response_schema, system, validator):
            self.calls.append(deepcopy(request_data))
            if not proposals:
                raise AssertionError('physical stub call exceeded the frozen proposal sequence')
            value = proposals.pop(0)
            view = work.save_view('compose', {'workflow_call_id': call_id, **request_data}, [])
            ident = work.reserve_attempt(view, {'model': fixture['model_id']}, call_id, 1, 'compose')
            work.attempt_sent(ident)
            raw = {'model': fixture['model_id'], 'content': json.dumps(value, ensure_ascii=False)}
            work.finish_attempt(ident, 'SUCCEEDED', raw, {'model': fixture['model_id'], 'usage': {}})
            if self.interrupt:
                self.interrupt = False
                raise InterruptedAfterRaw()
            runtime['_Protocol'](response_schema, validator).validate('FiniteIntegerObservation', value)
            return deepcopy(value)

    services = Services()
    request = {'workflow_id': 'risk_team_compare_workflow', 'question': data['question']}
    binding = deepcopy(fixture['binding'])
    run_id = uuid.uuid5(uuid.NAMESPACE_URL, 'adr0814:' + case['case_id']).hex
    context = runtime['RequestContext'].create({'id': case['case_id'], 'question': data['question']},
                                               request, binding, fixture['wall_seconds'], run_id)
    deadline_at = context.deadline_at
    path = output_dir / 'journals' / case['case_id'] / 'journal.sqlite'
    if path.exists():
        raise RuntimeError('refusing to reuse a qualification journal: ' + str(path))
    work = repo = model = None
    errors = []
    outcomes = []
    snapshots = []
    crash_observed = False
    crash_state_valid = case['interruption'] == 'none'

    def open_journal():
        nonlocal work, repo, model
        work = runtime['WorkRepository'](path, context, fixture['profile'])
        repo = runtime['Repository'](work, request, binding)
        model = runtime['ModelAdapter'](repo, services, context)

    def reopen_if_requested():
        if case['reuse'] == 'reopen':
            work.close()
            open_journal()

    def positive_integer(value):
        if value['value'] <= 0:
            raise ValueError('supplied integer observation must be positive')

    def decide():
        try:
            value = model.decide('FINITE_INTEGER_OBSERVATION', data, schema,
                                 fixture['instructions'], positive_integer)
            outcomes.append({'kind': 'COMPLETE', 'value': value})
        except Exception as exc:
            error = describe_error(exc)
            errors.append(error)
            outcomes.append({'kind': error['code'], 'error': error})

    def snapshot():
        calls = [dict(row) for row in work.db.execute('SELECT * FROM workflow_call ORDER BY call_id')]
        attempts = [dict(row) for row in work.db.execute('SELECT * FROM model_attempt ORDER BY created_seq')]
        view_bindings = [json.loads(row[0]) for row in work.db.execute('SELECT body_json FROM model_view ORDER BY created_seq')]
        return {'call_statuses': [row['status'] for row in calls],
                'repairable_failures': [json.loads(row['error_json']) for row in calls if row['status'] == 'FAILED'],
                'attempts': attempts, 'views': view_bindings, 'budget': work.budget(), 'run': work.run()}

    try:
        open_journal()
        try:
            decide()
        except InterruptedAfterRaw:
            crash_observed = True
            interrupted = snapshot()
            crash_state_valid = (interrupted['call_statuses'] == ['PREPARED'] and
                                 len(interrupted['attempts']) == 1 and
                                 interrupted['attempts'][0]['status'] == 'SUCCEEDED' and
                                 interrupted['budget']['model_reserved'] == 1)
            reopen_if_requested()
            decide()
        snapshots.append(snapshot())
        calls_before_reuse = len(services.calls)
        reopen_if_requested()
        decide()
        snapshots.append(snapshot())
        current = snapshots[-1]
        expected_kind = 'WORKFLOW_REPAIR_EXHAUSTED' if case['outcome'] == 'exhausted' else 'COMPLETE'
        expected_value = None if case['outcome'] == 'exhausted' else {'value': case['proposal_values'][-1]}
        expected_statuses = case['expected_workflow_statuses']
        raw_values = [json.loads(json.loads(row['response_json'])['content']) for row in current['attempts']]
        # Journal view coordinates legitimately differ by physical attempt.
        # Compare every supplied decision field after removing only these
        # repository-owned coordinates and the explicit correction envelope.
        coordinates = {'repair', 'workflow_call_id', 'view_id', 'phase',
                       'base_state_revision', 'evidence_revision'}
        base_views = [{key: value for key, value in view.items() if key not in coordinates}
                      for view in current['views']]
        call_inputs = [{key: value for key, value in call.items() if key != 'repair'} for call in services.calls]
        result['checks'] = {
            'controlled_crash_boundary': crash_observed == (case['interruption'] == 'after_raw') and crash_state_valid,
            'first_terminal_outcome': len(outcomes) == 2 and outcomes[0]['kind'] == expected_kind,
            'reused_terminal_outcome': len(outcomes) == 2 and outcomes[-1]['kind'] == expected_kind,
            'returned_value_preserved': expected_value is None or all(item.get('value') == expected_value for item in outcomes),
            'workflow_terminal_states': current['call_statuses'] == expected_statuses,
            'failed_proposals_keep_one_repair_owner': all(item.get('repairable') is True for item in current['repairable_failures']),
            'physical_call_count': len(services.calls) == case['expected_stub_calls'],
            'zero_new_sends_on_terminal_reuse': len(services.calls) == calls_before_reuse,
            'raw_attempts_retained': raw_values == original_proposals and all(row['status'] == 'SUCCEEDED' for row in current['attempts']),
            'persistent_budget': all(snap['budget']['model_reserved'] == case['expected_stub_calls'] and
                                     snap['budget']['model_limit'] == fixture['profile']['max_model_attempts'] and
                                     snap['budget']['tool_limit'] == fixture['profile']['max_tool_actions'] and
                                     snap['budget']['tool_used'] == 0 for snap in snapshots),
            'deadline_binding_preserved': all(snap['run']['deadline_at'] == deadline_at and
                                              snap['run']['binding_hash'] == context.binding_hash for snap in snapshots),
            'same_evidence_and_scope_on_correction': bool(base_views) and
                all(view == call_inputs[0] for view in base_views) and
                all(call == call_inputs[0] for call in call_inputs),
            'no_external_model_or_retrieval': True,
        }
        result['observed'] = {'outcomes': outcomes, 'call_statuses': current['call_statuses'],
                              'budget': current['budget'], 'crash_observed': crash_observed,
                              'journal': str(path), 'journal_reopened': case['reuse'] == 'reopen',
                              'raw_attempt_count': len(current['attempts']), 'errors': errors,
                              'legal_correctness_scored': False}
        result['stub_model_calls'] = len(services.calls)
        result['tool_calls'] = current['budget']['tool_used']
        result['passed'] = all(result['checks'].values())
        if not result['passed']:
            result['error'] = errors[-1] if errors else {'type': 'RecoveryContractMismatch', 'message': 'Frozen recovery invariant failed.'}
    finally:
        if work is not None:
            work.close()
    result['elapsed_seconds'] = time.perf_counter() - started
    return result


def run_family(runtime, arm, family, output_dir, code_root):
    started = time.perf_counter()
    descriptor_path = DESIGN / (family + '-cases.json')
    descriptor = json.loads(descriptor_path.read_text())
    results = []
    for case in descriptor['cases']:
        if family == 'comparison':
            result = comparison_case(runtime, case, descriptor['fixture'])
        else:
            result = recovery_case(runtime, case, descriptor['fixture'], output_dir)
        results.append(result)
    elapsed = time.perf_counter() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    value = {'arm': arm, 'family': family, 'results': results, 'elapsed_seconds': elapsed,
             'max_rss_kib': rss, 'real_model_calls': 0, 'descriptor_hash': hashed(descriptor),
             'code_root': str(code_root), 'imports': verify_imports(code_root),
             'scope': 'finite software contract census; no legal accuracy or retrieval coverage claim',
             'limits_passed': elapsed <= 180 and rss <= 12582912}
    with (output_dir / (family + '.json')).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--code-root', type=Path, required=True)
    parser.add_argument('--arm', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    code_root = args.code_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if any((output_dir / (family + '.json')).exists() for family in ('comparison', 'recovery')):
        raise RuntimeError('refusing to replace previous qualification results')
    runtime = load_runtime(code_root)
    verify_imports(code_root)
    families = [run_family(runtime, args.arm, family, output_dir, code_root)
                for family in ('comparison', 'recovery')]
    print(encoded({'arm': args.arm, 'families': {value['family']: {
        'passed': sum(row['passed'] for row in value['results']), 'count': len(value['results']),
        'elapsed_seconds': value['elapsed_seconds'], 'limits_passed': value['limits_passed']}
        for value in families}, 'real_model_calls': 0}))
    return 0 if all(value['limits_passed'] and all(row['passed'] for row in value['results']) for value in families) else 1


if __name__ == '__main__':
    raise SystemExit(main())
