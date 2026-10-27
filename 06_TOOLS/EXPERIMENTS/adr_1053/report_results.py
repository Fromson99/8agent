"""Report frozen MVP observations without a model, source DB, or inferred scores.

Default inspection is read-only. --write updates only the three report artifacts
and the existing 37 question documents; native results and frozen inputs remain
immutable. Partial/stopped executions never become a completed experiment.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.util
import json
import math
from pathlib import Path
import statistics

from common import ROOT, ADR, ART, read, save, sha

ARMS = ('A0', 'A1', 'A2')
PAIRS = (('A2', 'A1'), ('A1', 'A0'), ('A2', 'A0'))
STAGES = ('acquired', 'delivered', 'cited')
USAGE_FIELDS = ('input_tokens', 'output_tokens', 'total_tokens', 'cost_usd')
HEADINGS = [
    '## 1. 실행 메타', '## 2. 사용자 질문 원문',
    '## 3. 기준답변 — 채점 전용, 제품 입력 비공개', '## 4. 제품 입력을 구성한 원값',
    '### 회수·탈락 단계 원장 — run·arm별', '## 5. 제품 모델 호출 — run·arm별 실제 원문',
    '## 6. 중간 LLM 호출 — router/compiler/verifier/repair',
    '## 7. 채점 호출과 반복 판정', '## 8. 사례 최종 판정',
]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def receipt(path):
    path = Path(path)
    before = path.stat()
    value = {'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'bytes': before.st_size}
    after = path.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
            'artifact changed while reporting: ' + str(path))
    return value


def verify_ref(value):
    path = (ROOT / value['path']).resolve()
    require(path.is_relative_to(ROOT.resolve()) and path.is_file(), 'missing/outside input artifact')
    require(sha(path) == value['sha256'], 'input hash mismatch: ' + value['path'])


def numeric(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def distribution(values, expected):
    numbers = sorted(float(x) for x in values if numeric(x))
    def quantile(q):
        if not numbers:
            return None
        index = (len(numbers) - 1) * q
        low = math.floor(index)
        return numbers[low] + (numbers[math.ceil(index)] - numbers[low]) * (index - low)
    return {'observed': len(numbers), 'missing': expected - len(numbers),
            'mean': statistics.mean(numbers) if numbers else None,
            'p50': quantile(.5), 'p95': quantile(.95),
            'quantile_method': 'linear interpolation at (n-1)*q'}


def usage_from_result(result):
    calls = result.get('model_calls')
    if type(calls) is not int or calls < 0:
        return None
    rows = result.get('usage') or []
    out = {'physical_calls': calls}
    for field in USAGE_FIELDS:
        known = [row[field] for row in rows if numeric(row.get(field))]
        unknown = max(0, calls - len(known))
        out[field] = {'known_sum': sum(known), 'unknown_calls': unknown,
                      'total': sum(known) if not unknown else None}
    return out


def aggregate_usage(values, expected):
    """Known sums describe observed records; missing observations are not zero."""
    values = [x for x in values if isinstance(x, dict)]
    missing = expected - len(values)
    counts = [x['physical_calls'] for x in values if type(x.get('physical_calls')) is int]
    out = {'observations': len(values), 'missing_observations': missing,
           'physical_calls_known': sum(counts),
           'physical_calls_total': sum(counts) if missing == 0 and len(counts) == len(values)
               and all(x.get('physical_calls_exact', True) for x in values) else None}
    for field in USAGE_FIELDS:
        sums = [x.get(field, {}).get('known_sum') for x in values]
        unknown = sum(x.get(field, {}).get('unknown_calls', x.get('physical_calls', 0)) for x in values)
        all_totals = all(numeric(x.get(field, {}).get('total')) for x in values)
        out[field] = {'known_sum': sum(x for x in sums if numeric(x)),
            'unknown_calls_in_observed_runs': unknown, 'missing_observations': missing,
            'total': sum(x[field]['total'] for x in values) if missing == 0 and all_totals
                and all(x.get('physical_calls_exact', True) for x in values) else None}
    return out


def answer_judgment(case, arm, cells, judges):
    if case['evaluation_class'] == 'EVIDENCE_ONLY':
        return {'verdict': 'excluded', 'reason': 'EVIDENCE_ONLY', 'failure_types': [],
                'missing_source_handling': 'not_applicable', 'grounded_correctness': 'unknown'}
    cell = cells[(case['case_id'], arm)]
    metric = cell.get('metrics')
    if not cell.get('completed'):
        reason = 'PRODUCT_OBSERVATION_NOT_COMPLETED'
    elif not metric:
        reason = 'METRICS_NOT_AVAILABLE'
    elif (metric.get('source_integrity', {}).get('mismatch_count') or
          metric.get('source_integrity', {}).get('failures')):
        reason = 'SOURCE_OR_RECORD_INTEGRITY_FAILURE'
    elif metric.get('service_error') or metric.get('service_status') != 200 or not metric.get('answer'):
        reason = 'SERVICE_OR_OUTPUT_UNAVAILABLE'
    else:
        judge = judges.get(case['case_id'], {})
        value = judge.get('answer_judgments', {}).get(arm)
        if value and not judge.get('completion_receipt_verified', False):
            return {'verdict': 'unknown', 'reason': 'JUDGE_COMPLETION_RECEIPT_UNAVAILABLE',
                    'failure_types': [], 'missing_source_handling': 'unknown', 'grounded_correctness': 'unknown'}
        if value:
            require(value.get('verdict') in ('pass', 'fail', 'unknown'), 'unexpected answer verdict')
            return value
        reason = 'JUDGE_NOT_AVAILABLE'
    return {'verdict': 'unknown', 'reason': reason, 'failure_types': [],
            'missing_source_handling': 'unknown', 'grounded_correctness': 'unknown'}


def paired_required_extent(cases, cells):
    """Equal-weight target means per case, then equal-weight paired case deltas.

    Only frozen BOUND targets enter a denominator. Unavailable source targets
    remain explicitly excluded, never zero-covered. Both arms must use the same
    frozen coordinates and expected span lengths for the pair to be determinate.
    """
    def case_coverage(case, arm, stage):
        targets = case.get('evidence_targets', []) + case.get('source_provenance', {}).get('required_external_evidence', [])
        bound = [t for t in targets if t.get('current_binding', {}).get('status') == 'BOUND']
        unavailable = Counter(t.get('current_binding', {}).get('status', 'UNKNOWN') for t in targets
                              if t.get('current_binding', {}).get('status') != 'BOUND')
        value = {'mean_bound_target_coverage': None, 'bound_target_count': len(bound),
                 'unavailable_target_count': len(targets) - len(bound),
                 'unavailable_binding_statuses': dict(unavailable)}
        cell = cells[(case['case_id'], arm)]; metric = cell.get('metrics')
        if not cell.get('completed'):
            return {**value, 'reason': 'PRODUCT_OBSERVATION_NOT_COMPLETED'}
        if metric is None:
            return {**value, 'reason': 'METRICS_NOT_AVAILABLE'}
        integrity = metric.get('source_integrity', {})
        if integrity.get('mismatch_count') or integrity.get('failures'):
            return {**value, 'reason': 'SOURCE_OR_RECORD_INTEGRITY_FAILURE'}
        observed = metric.get('required_targets', [])
        if len(observed) != len(targets):
            return {**value, 'reason': 'FROZEN_TARGET_SET_MISMATCH'}
        ratios = []
        for target, item in zip(targets, observed):
            binding = target.get('current_binding', {})
            if (item.get('role') != target.get('role') or
                    any(item.get(k) != binding.get(k) for k in
                        ('document_id', 'unit_id', 'coordinate_key')) or
                    item.get('binding_status') != binding.get('status')):
                return {**value, 'reason': 'FROZEN_TARGET_SET_MISMATCH'}
            coverage = item.get(stage, {})
            if binding.get('status') != 'BOUND':
                if coverage.get('status') != 'UNAVAILABLE_IN_FROZEN_CORPUS':
                    return {**value, 'reason': 'UNAVAILABLE_TARGET_STATE_MISMATCH'}
                continue
            expected = sum(b['end_cp'] - b['start_cp'] for b in binding.get('blocks', []))
            covered = coverage.get('covered_codepoints')
            if (expected <= 0 or coverage.get('expected_codepoints') != expected or
                    coverage.get('status') not in ('COMPLETE', 'PARTIAL', 'TITLE_ONLY', 'NONE') or
                    not numeric(covered) or not 0 <= covered <= expected):
                return {**value, 'reason': 'BOUND_TARGET_EXTENT_UNAVAILABLE_OR_MISMATCH'}
            ratios.append(covered / expected)
        if not ratios:
            return {**value, 'reason': 'NO_BOUND_TARGETS'}
        return {**value, 'mean_bound_target_coverage': statistics.mean(ratios), 'reason': None}

    output = {}
    groups = {'reference_34': [c for c in cases if c['evaluation_class'] != 'EVIDENCE_ONLY'],
              'evidence_only_diagnostic_3': [c for c in cases if c['evaluation_class'] == 'EVIDENCE_ONLY']}
    for candidate, baseline in PAIRS:
        pair = {}
        for group, selected in groups.items():
            stages = {}
            for stage in STAGES:
                rows = []
                for case in selected:
                    a = case_coverage(case, candidate, stage); b = case_coverage(case, baseline, stage)
                    av = a['mean_bound_target_coverage']; bv = b['mean_bound_target_coverage']
                    delta = av - bv if av is not None and bv is not None else None
                    rows.append({'case_id': case['case_id'], 'candidate': a, 'baseline': b,
                                 'delta': delta, 'direction': 'unknown' if delta is None else
                                 'positive' if delta > 0 else 'negative' if delta < 0 else 'tie'})
                known = [r for r in rows if r['delta'] is not None]
                counts = Counter(r['direction'] for r in rows)
                stages[stage] = {'eligible_pairs': len(rows), 'determinate_pairs': len(known),
                    **{k + '_pairs': counts[k] for k in ('positive', 'tie', 'negative', 'unknown')},
                    'mean_paired_delta': statistics.mean(r['delta'] for r in known) if known else None,
                    'candidate_mean_on_determinate_pairs': statistics.mean(r['candidate']['mean_bound_target_coverage'] for r in known) if known else None,
                    'baseline_mean_on_determinate_pairs': statistics.mean(r['baseline']['mean_bound_target_coverage'] for r in known) if known else None,
                    'unknown_case_ids': [r['case_id'] for r in rows if r['delta'] is None], 'cases': rows}
            pair[group] = stages
        output[candidate + '-' + baseline] = pair
    return output


def summarize(cases, cells, judges, *, stop=None, completion_receipts=None):
    """Pure arithmetic, also used by small synthetic checks before freezing."""
    eligible = [c for c in cases if c['evaluation_class'] != 'EVIDENCE_ONLY']
    require(len(cases) == 37 and len(eligible) == 34, 'unexpected fixed sample')
    verdicts = {c['case_id']: {a: answer_judgment(c, a, cells, judges) for a in ARMS} for c in cases}
    completed = sum(c.get('completed') is True for c in cells.values())
    metric_count = sum(c.get('metrics') is not None for c in cells.values())
    ledger_count = sum(c.get('ledger') is not None for c in cells.values())
    judge_complete = sum(j.get('status') in ('COMPLETE', 'COMPLETE_WITH_UNKNOWNS') and
                         j.get('completion_receipt_verified', False) for j in judges.values())
    fatal = [c['cell'] for c in cells.values() if c.get('result', {}).get('outcome') == 'FATAL_STOP']
    integrity = sum(bool(c.get('metrics', {}).get('source_integrity', {}).get('mismatch_count') or
                         c.get('metrics', {}).get('source_integrity', {}).get('failures'))
                    for c in cells.values())
    stopped = bool(stop or fatal or integrity or any(j.get('status') == 'PROVIDER_STOP' for j in judges.values()))
    receipt_counts = completion_receipts or {'metrics': 0, 'judge': 0}
    complete = (completed == metric_count == ledger_count == receipt_counts['metrics'] == 111
                and judge_complete == receipt_counts['judge'] == 37 and not stopped)
    status = ('COMPLETE_OBSERVATIONS' if complete else 'STOPPED_PARTIAL' if stopped else
              'NOT_STARTED' if not any(c.get('reserved') for c in cells.values()) else 'PARTIAL')
    arms = {}
    for arm in ARMS:
        judgments = [verdicts[c['case_id']][arm] for c in eligible]
        counts = Counter(j['verdict'] for j in judgments)
        determined = counts['pass'] + counts['fail']
        observed = [cells[(c['case_id'], arm)] for c in cases]
        metrics = [x['metrics'] for x in observed if x.get('metrics') is not None]
        coverage = {}
        for stage in STAGES:
            entries = [t[stage] for m in metrics for t in m['required_targets']]
            states = Counter(x['status'] for x in entries)
            bound = [x for x in entries if x['status'] != 'UNAVAILABLE_IN_FROZEN_CORPUS']
            known_extent = [x for x in bound if numeric(x.get('covered_codepoints')) and numeric(x.get('expected_codepoints'))]
            covered = sum(x['covered_codepoints'] for x in known_extent)
            expected = sum(x['expected_codepoints'] for x in known_extent)
            coverage[stage] = {'observed_targets': len(entries), 'status_counts': dict(states),
                'bound_targets': len(bound), 'unavailable_targets': states['UNAVAILABLE_IN_FROZEN_CORPUS'],
                'missing_cell_metrics': 37 - len(metrics), 'unknown_extent_targets': len(bound) - len(known_extent),
                'covered_codepoints_known': covered, 'expected_codepoints_known': expected,
                'micro_coverage_on_known_bound_targets': covered / expected if expected else None,
                'body_codepoints_known': sum(x.get('body_codepoints', 0) for x in known_extent),
                'full_extent_share_of_bound_targets': states['COMPLETE'] / len(bound) if bound else None}
        relevance = [j.get('reading_relevance', {}).get(arm) for j in judges.values()]
        relevance = [r for r in relevance if r is not None]
        chars = Counter(); fragments = Counter()
        for row in relevance:
            chars.update(row.get('codepoints', {})); fragments.update(row.get('fragment_counts', {}))
        total = sum(chars.values()); classified = chars['relevant'] + chars['unrelated']
        arms[arm] = {'semantic': {'eligible': 34, 'pass': counts['pass'], 'fail': counts['fail'],
            'unknown': counts['unknown'], 'confirmed_correct_share': counts['pass'] / 34,
            'determinate_count': determined, 'determinate_accuracy': counts['pass'] / determined if determined else None,
            'unknown_reasons': dict(Counter(j['reason'] for j in judgments if j['verdict'] == 'unknown')),
            'failure_types': dict(Counter(t for j in judgments for t in j.get('failure_types', []))),
            'evidence_only_excluded': 3},
            'product_observations': {'completed': sum(x.get('completed') is True for x in observed),
                'outcomes': dict(Counter(x.get('result', {}).get('outcome', 'NO_RESULT') for x in observed)),
                'service_errors': sum(bool(m.get('service_error')) or m.get('service_status') != 200 for m in metrics),
                'output_errors': sum(len(m.get('output_errors', [])) for m in metrics),
                'missing_metrics': 37 - len(metrics)},
            'required_extent': coverage,
            'latency_seconds': distribution([x.get('result', {}).get('seconds') for x in observed], 37),
            'usage': aggregate_usage([x.get('usage') for x in observed], 37),
            'delivered_canonical_articles': distribution([len(m['coordinates']['delivered']) for m in metrics], 37),
            'presented_selectivity': distribution([m.get('presented_selectivity') for m in metrics], 37),
            'missing_source_handling': dict(Counter(j.get('missing_source_handling', 'unknown') for j in judgments)),
            'grounded_correctness': dict(Counter(j.get('grounded_correctness', 'unknown') for j in judgments)),
            'reading_relevance': {'observed_cases': len(relevance), 'missing_cases': 37 - len(relevance),
                'fragment_counts': dict(fragments), 'codepoints': dict(chars),
                'unrelated_share_of_classified': chars['unrelated'] / classified if classified else None,
                'unrelated_share_lower_bound': chars['unrelated'] / total if total else None,
                'unrelated_share_upper_bound': (chars['unrelated'] + chars['uncertain']) / total if total else None,
                'uncertain_share': chars['uncertain'] / total if total else None}}
    pairs = {}
    for candidate, baseline in PAIRS:
        bins = Counter(); unknown = []
        for case in eligible:
            cid = case['case_id']; a = verdicts[cid][candidate]['verdict']; b = verdicts[cid][baseline]['verdict']
            if 'unknown' in (a, b):
                unknown.append(cid); continue
            bins['both_pass' if a == b == 'pass' else 'both_fail' if a == b == 'fail' else
                 'candidate_only_pass' if a == 'pass' else 'baseline_only_pass'] += 1
        count = sum(bins.values())
        pairs[candidate + '-' + baseline] = {**{k: bins[k] for k in
            ('both_pass', 'candidate_only_pass', 'baseline_only_pass', 'both_fail')},
            'eligible_pairs': 34, 'determinate_pairs': count, 'unknown_pairs': len(unknown),
            'unknown_case_ids': unknown, 'determinate_delta':
            (bins['candidate_only_pass'] - bins['baseline_only_pass']) / count if count else None}
    return {'schema_version': 'ontology-mvp-matrix-summary-v1', 'status': status,
        'complete_observations': complete, 'adr_final_validation_completed': False,
        'planned_product_cells': 111, 'completed_product_cells': completed,
        'product_matrix_complete': completed == 111, 'metrics_cells': metric_count, 'ledger_cells': ledger_count,
        'planned_evaluation_cases': 37, 'finished_evaluation_cases': judge_complete,
        'evaluation_cases_with_result': len(judges), 'completion_receipts_verified': receipt_counts,
        'source_integrity_failure_cells': integrity,
        'stop': stop, 'fatal_cells': fatal, 'arms': arms, 'paired_semantic': pairs,
        'paired_required_extent': paired_required_extent(cases, cells),
        'paired_required_extent_method': 'Arithmetic mean of exact coverage ratios across frozen BOUND targets within each case, then mean candidate-minus-baseline delta across determinate pairs. Same frozen targets/extent denominators for both arms. Unavailable targets excluded and counted; no BOUND targets or incomplete observations remain unknown. Reference34 and evidence-only3 are separate groups. No significance test.',
        'judge': {'usage': aggregate_usage([j.get('usage') for j in judges.values()], 37),
                  'latency_seconds': distribution([j.get('seconds') for j in judges.values()], 37),
                  'statuses': dict(Counter(j['status'] for j in judges.values())),
                  'errors': {k: v.get('errors', []) for k, v in judges.items() if v.get('errors')},
                  'calibration': 'Not performed; provisional same-model offline evaluator; no repeat/regrade.'},
        'case_verdicts': verdicts, 'decision_eligible': False, 'known_in_sample': True,
        'gold_visible_to_product': False, 'main_or_genos_quality_certified': False}


def load_inputs():
    freeze = read(ART / 'design-freeze.json'); freeze_hash = sha(ART / 'design-freeze.json')
    for key in ('product_cases', 'evaluator_cases', 'evaluation_contract', 'corpus', 'authorization'):
        verify_ref({'path': freeze[key + '_path'], 'sha256': freeze[key + '_sha256']})
    scripts = {**freeze.get('runner_hashes', {}), **freeze.get('evaluation_scripts', {})}
    for name in ('common.py', 'report_results.py'):
        path = Path(__file__).with_name(name)
        require(scripts.get(str(path.relative_to(ROOT))) == sha(path), 'report script is not frozen: ' + name)
    ledger_path = ROOT / '02_BACKEND/lawrag/runtime/retrieval_stage_ledger.py'
    require(scripts.get(str(ledger_path.relative_to(ROOT))) == sha(ledger_path), 'ledger code is not frozen')
    spec = importlib.util.spec_from_file_location('adr1049_report_ledger', ledger_path)
    ledger_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(ledger_module)
    cases = read(ROOT / freeze['evaluator_cases_path'])['cases']
    product = read(ROOT / freeze['product_cases_path'])['cases']
    require([(c['case_id'], c['question']) for c in cases] == [(c['case_id'], c['question']) for c in product],
            'product/evaluator question mismatch')
    by_id = {c['case_id']: c for c in cases}; cells = {}; refs = []; ledgers = []
    completion_path = ART / 'evaluation-case-receipts.json'
    completion = read(completion_path) if completion_path.is_file() else {'metrics': {}, 'judge': {}}
    if completion_path.is_file():
        require(completion['design_freeze_sha256'] == freeze_hash, 'evaluation receipt freeze mismatch')
        refs.append(receipt(completion_path))
    require(set(completion['metrics']) <= {str(i) for i in range(1, 112)} and
            set(completion['judge']) <= set(by_id), 'completion receipt contains unknown cases')
    completion_counts = {'metrics': 0, 'judge': 0}
    require(len(freeze['execution_order']) == 111, 'matrix length changed')
    for cell in freeze['execution_order']:
        cid, arm = cell['case_id'], cell['arm']; require(cid in by_id and arm in ARMS, 'unknown cell')
        key = (cid, arm); require(key not in cells, 'duplicate cell')
        out = ART / 'matrix' / f"{cell['ordinal']:03d}-{cid}-{arm}"
        row = {'cell': cell, 'out': out, 'reserved': out.exists(), 'completed': False, 'refs': []}
        def capture(name):
            p = out / name
            if not p.is_file():
                return None
            r = receipt(p); refs.append(r); row['refs'].append(r); return read(p)
        reservation = capture('reservation.json'); result = capture('result.json')
        row['reservation'] = reservation
        if result is not None:
            require(reservation and reservation['cell'] == cell and result['cell'] == cell and
                    reservation['design_freeze_sha256'] == freeze_hash, 'cell freeze binding mismatch')
            row['result'] = result
            row['completed'] = result.get('completed') is True and result.get('outcome') in (
                'SERVICE_COMPLETED', 'NATIVE_BOUNDED_FAILURE')
            row['usage'] = usage_from_result(result)
        elif (out / 'call-state.json').is_file():
            state = capture('call-state.json')
            usage_path = out / 'model/usage.json'
            usage = read(usage_path) if usage_path.is_file() else []
            # Last committed count is a lower bound if a later call was reserved.
            physical = state.get('physical_calls', max(0, state.get('reserved_calls', 0) - 1))
            row['usage'] = usage_from_result({'model_calls': physical, 'usage': usage})
            row['usage']['physical_calls_exact'] = False
        metric = capture('metrics.json')
        if metric is not None:
            require(metric['case_id'] == cid and metric['arm'] == arm and
                    metric['source_generation_id'] == freeze['source_generation_id'], 'metric binding mismatch')
            row['metrics'] = metric; row['usage'] = metric['usage']
        ledger = capture('retrieval-ledger-case.json')
        if ledger is not None:
            require(ledger['case_id'] == cid and ledger['arm_id'] == ('baseline' if arm == 'A0' else arm),
                    'ledger binding mismatch')
            ledger_module.validate_graded_ledger(ledger)
            row['ledger'] = ledger; ledgers.append(ledger)
        expected = completion['metrics'].get(str(cell['ordinal']))
        if expected is not None:
            required_paths = {str((out / n).relative_to(ROOT)) for n in ('metrics.json', 'evidence-audit.json',
                'judge-source-packets.json', 'ontology-audit.json', 'retrieval-ledger-case.json')}
            require(set(expected) == required_paths, 'metric completion receipt paths mismatch')
            for path, expected_hash in expected.items():
                verify_ref({'path': path, 'sha256': expected_hash})
            completion_counts['metrics'] += 1
        cells[key] = row
    require(len(cells) == 111, 'missing matrix cell')
    judges = {}
    for case in cases:
        folder = ART / 'evaluation' / case['case_id']; result_path = folder / 'result.json'
        if not result_path.is_file():
            continue
        require((folder / 'plan.json').is_file(), 'judge result lacks plan')
        plan = read(folder / 'plan.json')
        for item in plan['input_files']:
            verify_ref(item)
        require(plan['case_id'] == case['case_id'] and plan['question'] == case['question'], 'judge plan mismatch')
        result = read(result_path)
        require(result['case_id'] == case['case_id'], 'judge case mismatch')
        require(result['status'] in ('COMPLETE', 'COMPLETE_WITH_UNKNOWNS', 'PROVIDER_STOP'), 'judge status mismatch')
        require(set(result['answer_judgments']) == set(ARMS), 'judge arm mismatch')
        expected = completion['judge'].get(case['case_id'])
        result['completion_receipt_verified'] = expected is not None
        if expected is not None:
            require(set(expected) == {str((folder / n).relative_to(ROOT)) for n in
                ('result.json', 'plan.json', 'relevance-judgments.json')}, 'judge completion receipt paths mismatch')
            for path, expected_hash in expected.items():
                verify_ref({'path': path, 'sha256': expected_hash})
            completion_counts['judge'] += 1
        judges[case['case_id']] = result; refs.extend([receipt(folder / 'plan.json'), receipt(result_path)])
    if ledgers:
        declarations = {arm: ['original_read', 'delivered', 'final_cited'] for arm in {x['arm_id'] for x in ledgers}}
        run = ledger_module.build_run_artifact('run-001', ledgers, declarations)
        ledger = ledger_module.build_experiment_artifact('ADR-1049', freeze['experiment_id'], [run])
    else:
        ledger = {'schema_version': 'ontology-mvp-empty-ledger-status-v1', 'status': 'NO_OBSERVED_LEDGERS',
            'planned_cells': 111, 'observed_cells': 0, 'reason': 'No stage observations; empty sets are not invented.',
            'computed_post_selection': True, 'gold_visible_to_product': False}
    stops = {name: read(ART / name) for name in ('matrix-stop.json', 'evaluation-stop.json') if (ART / name).is_file()}
    summary = summarize(cases, cells, judges, stop=stops or None, completion_receipts=completion_counts)
    summary.update(experiment_id=freeze['experiment_id'], run_id='run-001',
        design_freeze=receipt(ART / 'design-freeze.json'), reporting_rules=freeze['reporting_rules'],
        corpus_total_article_roots=freeze.get('corpus_total_article_roots'),
        input_artifacts=refs, unobserved_ledger_cells=[r['cell'] for r in cells.values() if 'ledger' not in r],
        missing_required_sources=read(ROOT / freeze['corpus_path']).get('missing_required', []),
        per_cell=[{'cell': r['cell'], 'completed': r['completed'], 'metrics': r.get('metrics', {}).get('required_targets'),
                   'artifact_refs': r['refs']} for r in cells.values()])
    require(sha(ART / 'design-freeze.json') == freeze_hash, 'design freeze changed while reporting')
    return freeze, cases, cells, judges, summary, ledger


def fmt(value, digits=3):
    return '미확인' if value is None else str(round(value, digits)) if isinstance(value, float) else str(value)


def report_markdown(summary):
    s = summary
    lines = ['# ADR-1049 MVP 비교 관찰 결과', '',
        f"상태: **{s['status']}**. 제품 관찰 {s['completed_product_cells']}/111, 평가 완료 {s['finished_evaluation_cases']}/37.", '',
        '111개 제품 관찰과 37개 평가가 모두 갖춰져야 전체 관찰 완료로 표시한다. ADR 최종 검증·MAIN 승격·GENOS 품질 인증은 별도다.', '',
        '| 조건 | pass | fail | unknown | pass/34 | pass/(pass+fail) | 확정 분모 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for arm in ARMS:
        a = s['arms'][arm]['semantic']
        lines.append(f"| {arm} | {a['pass']} | {a['fail']} | {a['unknown']} | {fmt(a['confirmed_correct_share'])} | {fmt(a['determinate_accuracy'])} | {a['determinate_count']} |")
    lines += ['', '근거 확보만 평가하는 3문항은 의미 정확도 분모에서 제외한다. 미확보 자체로 의미 오답을 만들지 않는다.', '',
        '| 비교 | 양쪽 pass | 후보만 pass | 기준만 pass | 양쪽 fail | 확정 쌍 | 미확인 쌍 | 확정 쌍 차이 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for key, p in s['paired_semantic'].items():
        lines.append('| ' + ' | '.join(str(x) for x in [key, p['both_pass'], p['candidate_only_pass'],
            p['baseline_only_pass'], p['both_fail'], p['determinate_pairs'], p['unknown_pairs'], fmt(p['determinate_delta'])]) + ' |')
    lines += ['', '| 원문 범위 비교 | 문항군 | 단계 | 양수 | 동일 | 음수 | 미확인 | 평균 paired 차이 |',
        '|---|---|---|---:|---:|---:|---:|---:|']
    for comparison, groups in s['paired_required_extent'].items():
        for group, stages in groups.items():
            for stage, p in stages.items():
                lines.append('| ' + ' | '.join(str(x) for x in [comparison, group, stage,
                    p['positive_pairs'], p['tie_pairs'], p['negative_pairs'], p['unknown_pairs'], fmt(p['mean_paired_delta'])]) + ' |')
    lines += ['', '문항마다 동결된 BOUND 대상의 정확 구간 확보율을 동일 가중 평균하고, 두 조건 모두 관찰된 문항의 차이를 평균한다. 확보·전달·인용을 각각 계산한다. 코퍼스 미확보 대상은 0점으로 넣지 않고 분모에서 제외해 별도로 기록한다. 3개 근거전용 문항은 별도 진단군이며 유의성 검정은 하지 않는다.']
    lines += ['', '| 조건 | 확보 전체/부분/제목 | 전달 전체/부분/제목 | 인용 전체/부분/제목 | 미확보 대상 | 미집계 문항 |',
        '|---|---|---|---|---:|---:|']
    for arm in ARMS:
        ext = s['arms'][arm]['required_extent']; display = []
        for stage in STAGES:
            c = ext[stage]['status_counts']; display.append('/'.join(str(c.get(k, 0)) for k in ('COMPLETE', 'PARTIAL', 'TITLE_ONLY')))
        lines.append(f"| {arm} | {' | '.join(display)} | {ext['acquired']['unavailable_targets']} | {ext['acquired']['missing_cell_metrics']} |")
    lines += ['', '정확한 원문 구간 확보율과 조문 존재 원장은 별도다. 별표를 조문 수로 변환하지 않으며, 전달·인용되지 않은 자료를 무관하다고 간주하지 않는다.', '',
        '| 구분 | 관찰 호출 | 비용 확인 합계(USD) | 비용 전체 | 누락 관찰 | 평균 초 | p50 초 | p95 초 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name, item in [*( (a, s['arms'][a]) for a in ARMS), ('평가자', s['judge'])]:
        u = item['usage']; t = item['latency_seconds']
        lines.append(f"| {name} | {u['physical_calls_known']} | {fmt(u['cost_usd']['known_sum'])} | {fmt(u['cost_usd']['total'])} | {u['missing_observations']} | {fmt(t['mean'])} | {fmt(t['p50'])} | {fmt(t['p95'])} |")
    lines += ['', f"공통 코퍼스의 조문 root: {fmt(s['corpus_total_article_roots'])}개. 필터 전·후의 완전 집합은 기록되지 않아 미확인이다.",
        '사용량 누락은 0으로 보정하지 않는다. 제품 비용과 평가 비용은 합치지 않는다.', '',
        '알려진 37문항을 이용한 탐색 비교이며 평가자 calibration을 수행하지 않았다. 같은 모델의 잠정 판정은 검증된 법률 정답이나 운영 성능 인증이 아니다.', '',
        '[기계 판독 요약](matrix-summary.json) · [회수 단계 원장](retrieval-ledger.json)', '']
    return '\n'.join(lines)


def file_table(paths):
    lines = ['| 원본 파일 | bytes | SHA-256 |', '|---|---:|---|']
    found = False
    for path in sorted(set(paths)):
        if path.is_file():
            r = receipt(path); found = True
            lines.append(f"| [{r['path']}]({path.resolve()}) | {r['bytes']} | `{r['sha256']}` |")
    return '\n'.join(lines) if found else '저장된 원본 파일 없음. 미실행·미수신·미확보 상태를 유지한다.'


def question_markdown(number, case, freeze, cells, judges, summary):
    cid = case['case_id']; rows = [cells[(cid, a)] for a in ARMS]
    source = ROOT / freeze['evaluator_cases_path']; product = ROOT / freeze['product_cases_path']
    lines = [f'# 질문 {number:03d} — {cid}', '', HEADINGS[0], '',
        f"ADR-1053 / run-001 / A0(baseline)·A1·A2. 전체 상태 {summary['status']}. 모델 qwen/qwen3.8-27b.",
        '저장된 원본은 아래 경로와 해시로 연결한다. 미수신 응답은 unavailable이며 재구성하지 않는다.', '',
        file_table([ART / 'design-freeze.json']), '', HEADINGS[1], '', case['question'], '',
        HEADINGS[2], '', case.get('reference_answer') or 'EVIDENCE_ONLY: 승인 기준답변 없음. 의미 정확도 채점 제외.', '',
        '최소 기준·보충 설명·허용 미확인·과거 출처는 평가 전용 자료의 해당 case_id에서 확인한다.',
        file_table([source]), '', HEADINGS[3], '', file_table([product, ROOT / freeze['corpus_path'], ROOT / freeze['snapshot_path']]), '',
        '제품 입력 질문 원문과 공통 코퍼스는 고정했다. 회수 원문·관계·정의는 실제 호출 및 원문 감사 파일을 연결하며 본문을 중복 복사하지 않는다.', '',
        HEADINGS[4], '', '| arm | stage | before | added | discarded | after | gold before | gold added | gold lost | gold after/total | recall |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|']
    for row in rows:
        arm = row['cell']['arm']; ledger = row.get('ledger')
        if ledger is None:
            lines.append(f'| {arm} | 미관찰 | 미확인 | 미확인 | 미확인 | 미확인 | 미확인 | 미확인 | 미확인 | 미확인 | 미확인 |')
            continue
        for stage in ledger['stages']:
            lines.append('| ' + ' | '.join(str(x) for x in [arm, stage['stage_id'], stage['before_count'],
                stage['added_count'], stage['discarded_count'], stage['after_count'], stage['gold_before'],
                stage['gold_added'], stage['gold_discarded'], f"{stage['gold_after']}/{stage['gold_total']}", fmt(stage['golden_recall'])]) + ' |')
    lines += ['', '정확한 탈락 좌표·사유와 원문 구간 확보 상태는 다음 원본에 보존한다. 비전달을 무관 판정으로 해석하지 않는다.',
        file_table([r['out'] / n for r in rows for n in ('retrieval-ledger-case.json', 'evidence-audit.json',
            'judge-source-packets.json', 'ontology-audit.json', 'metrics.json')] +
            [r['out'] / j['path'] for r in rows for j in r.get('metrics', {}).get('journals', [])]),
        '', HEADINGS[5], '', 'system·user·schema/tool은 각 request.json의 원문이다. provider 원응답·출력·사용량도 아래 저장 파일 그대로 연결한다.']
    for row in rows:
        out = row['out']; arm = row['cell']['arm']; result = row.get('result', {})
        reserved = (row.get('reservation') or {}).get('reserved_at')
        started = datetime.fromtimestamp(reserved, timezone.utc).isoformat() if numeric(reserved) else '미실행/시각 미확인'
        lines += ['', f"### run-001 / {arm} / {result.get('outcome', 'NOT_RECORDED')}", '',
            f'실행 예약 시각(UTC): {started}.',
            f"완료 관찰: {row['completed']}. 지연 초: {fmt(result.get('seconds'))}. 호출: {fmt(result.get('model_calls'))}.",
            file_table([out / n for n in ('reservation.json', 'request.json', 'response.json', 'result.json', 'physical-calls.jsonl', 'call-state.json')] +
                       list((out / 'model').glob('call-*/*')) + [out / 'model/usage.json'])]
    lines += ['', HEADINGS[6], '', '모든 중간·복구 호출도 위 제품 call 번호 순서의 원본에 포함한다. 컴파일러는 결정적 코드이며 모델 호출로 세지 않는다.',
        file_table([r['out'] / 'native-failures.jsonl' for r in rows]), '', HEADINGS[7], '',
        '반복 채점·다수결·자동 재시도 없음. plan의 익명 위치와 result의 arm 대응을 보존한다.',
        file_table([ART / 'evaluation' / cid / n for n in ('plan.json', 'result.json', 'relevance-judgments.json')] +
                   list((ART / 'evaluation' / cid / 'raw').glob('call-*/*')) + [ART / 'evaluation' / cid / 'raw/usage.json']),
        '', HEADINGS[8], '', '| arm | 의미 판정 | 미확보 처리 | 근거 완전성 | 사유 |', '|---|---|---|---|---|']
    for arm in ARMS:
        v = summary['case_verdicts'][cid][arm]
        lines.append(f"| {arm} | {v['verdict']} | {v.get('missing_source_handling', 'unknown')} | {v.get('grounded_correctness', 'unknown')} | {v['reason'].replace('|', '/').replace(chr(10), ' ')} |")
    lines += ['', '실패 유형과 미확인 원인은 평가 result 및 metrics를 따른다. 사람이 확인한 직접 원인·후속 가설은 이 자동 보고서가 생성하지 않는다.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--inspect-only', action='store_true')
    args = parser.parse_args()
    require(not (args.write and args.inspect_only), 'choose write or inspection')
    freeze, cases, cells, judges, summary, ledger = load_inputs()
    if args.write:
        # Pre-render everything before replacing any report; no partial markdown update on validation failure.
        documents = [(ADR / '실험' / f"질문-{i:03d}-{c['case_id']}.md",
                      question_markdown(i, c, freeze, cells, judges, summary)) for i, c in enumerate(cases, 1)]
        require(all(p.is_file() for p, _ in documents), 'expected question document absent')
        summary['report_generated_at'] = datetime.now(timezone.utc).isoformat()
        save(ART / 'retrieval-ledger.json', ledger)
        summary['retrieval_ledger'] = receipt(ART / 'retrieval-ledger.json')
        save(ART / 'matrix-summary.json', summary)
        (ART / 'RESULT.md').write_text(report_markdown(summary), encoding='utf-8')
        for path, text in documents:
            path.write_text(text, encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('status', 'complete_observations', 'completed_product_cells',
        'finished_evaluation_cases', 'metrics_cells', 'ledger_cells')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
