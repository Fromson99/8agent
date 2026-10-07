"""Offline diagnose -> bounded proposal -> split plan -> paired gate.

Records are inert. This module does not load candidates, run models, authorize
exports, select runtime profiles, publish knowledge, or promote MAIN.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile

from semantic_runtime.contracts import digest
from lawrag.platform.workspace import load_layout
from .native_trace import read_trace, verify_trace


def seal(value):
    return {**value, 'content_sha256': digest(value)}


def verify(value, version):
    if value.get('schema_version') != version or value.get('content_sha256') != digest({k: v for k, v in value.items() if k != 'content_sha256'}):
        raise ValueError('offline artifact hash/version mismatch')
    return value


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def publish(path, value):
    """Atomic no-replace publication; identical retries preserve the first bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('immutable offline artifact already exists with different bytes')
        return False
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.publishing-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise ValueError('concurrent offline publication conflict')
            return False
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
        return True
    finally:
        Path(temporary).unlink(missing_ok=True)


def diagnose(journals, output, *, feedback=None):
    """Read explicit terminal journals, persist content-addressed diagnoses."""
    output = Path(output)
    paths = sorted({Path(p).resolve() for p in journals})
    if not paths:
        raise ValueError('explicit nonempty journal selection required')
    if output.resolve() in paths or any(output.resolve().is_relative_to(p.parent) for p in paths):
        raise ValueError('diagnostic output must be outside source request directories')
    output.mkdir(parents=True, exist_ok=True); output.chmod(0o700)
    records = []; errors = []; deferred = []; new = 0
    with (output / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for path in paths:
            try:
                trace = read_trace(path)
                traces_path = output / 'traces' / (trace['content_sha256'] + '.json')
                publish(traces_path, trace)
                signals = sorted([{'event_id': e['event_id'], 'signal': e['signal']} for e in (feedback or {}).get(trace['run_id'], [])], key=lambda e: e['event_id'])
                issues = list(trace['issues'])
                if signals:
                    issues.append({'type': 'negative_feedback', 'stage': 'UNKNOWN', 'confirmed': False,
                                   'cause': 'UNKNOWN', 'refs': signals})
                value = {'schema_version': 'failure-diagnosis-v1', 'run_id': trace['run_id'],
                         'trace_sha256': trace['content_sha256'], 'snapshot_sha256': trace['snapshot_sha256'],
                         'trace_path': str(traces_path.resolve()), 'journal_path': str(path),
                         'binding_hash': digest(trace['binding']), 'run_status': trace['run_status'],
                         'issues': issues, 'legal_quality': 'UNKNOWN', 'runtime_loadable': False}
                ident = 'diagnosis:' + digest(value)
                value = seal({**value, 'id': ident})
                target = output / 'diagnoses' / (ident.split(':')[1] + '.json')
                new += int(publish(target, value))
                records.append({'id': ident, 'path': str(target.resolve()), 'sha256': value['content_sha256'],
                                'issues': len(issues), 'run_status': trace['run_status']})
            except (ValueError, OSError, sqlite3.Error) as exc:
                # Do not persist provider errors or source prose from exception messages.
                if isinstance(exc, ValueError) and str(exc) == 'native journal is not terminal':
                    deferred.append(str(path))
                else:
                    errors.append({'journal': str(path), 'error_type': type(exc).__name__})
        report = seal({'schema_version': 'failure-diagnostic-report-v1', 'records': records,
                       'errors': errors, 'deferred': deferred, 'source_read_only': True,
                       'model_calls': 0, 'quality_certified': False})
        report_path = output / 'reports' / (report['content_sha256'] + '.json')
        publish(report_path, report)
    return {'state': 'PARTIAL' if errors else 'COMPLETED', 'report': str(report_path.resolve()),
            'records': len(records), 'new_records': new, 'existing_records': len(records)-new,
            'errors': len(errors), 'deferred': len(deferred), 'model_calls': 0}


TARGETS = {
    'tool_partial': ('Tool', 'source_read_completion', 'Mark acquisition incomplete and expose the remaining read extent before selecting evidence.'),
    'tool_truncated': ('Tool', 'source_read_completion', 'Expose truncation and the existing next-cursor contract; distinguish excerpts from full originals.'),
    'partial_original': ('Tool', 'source_read_completion', 'Explain the unresolved source extent using existing read receipts and cursor semantics.'),
    'empty_selection': ('Tool', 'source_selection_exposure', 'Clarify offered source IDs and coverage in the selector while preserving scope and budget.'),
}


def propose(diagnosis_path, output):
    diagnosis = verify(read(diagnosis_path), 'failure-diagnosis-v1')
    trace = verify_trace(read(diagnosis['trace_path']))
    if diagnosis['trace_sha256'] != trace['content_sha256']:
        raise ValueError('diagnosis/trace binding mismatch')
    if (diagnosis['snapshot_sha256'] != trace['snapshot_sha256'] or
            diagnosis['run_id'] != trace['run_id'] or diagnosis['run_status'] != trace['run_status'] or
            diagnosis['binding_hash'] != digest(trace['binding'])):
        raise ValueError('diagnosis metadata does not match native trace')
    observed = {digest(issue) for issue in trace['issues']}
    if any(issue.get('confirmed') and digest(issue) not in observed for issue in diagnosis['issues']):
        raise ValueError('diagnosis confirmed issue not corroborated by native trace')
    current = read_trace(diagnosis['journal_path'])
    if current['snapshot_sha256'] != diagnosis['snapshot_sha256']:
        raise ValueError('native source changed since diagnosis')
    if current['content_sha256'] != trace['content_sha256']:
        raise ValueError('native diagnostic projection changed; regenerate diagnosis')
    candidates = []
    for issue in diagnosis['issues']:
        if not issue.get('confirmed') or issue.get('resolved') or issue['type'] not in TARGETS:
            continue
        layer, target, hypothesis = TARGETS[issue['type']]
        value = {'schema_version': 'failure-improvement-proposal-v1', 'diagnosis_id': diagnosis['id'],
                 'diagnosis_sha256': diagnosis['content_sha256'], 'trace_sha256': trace['content_sha256'],
                 'binding_hash': diagnosis['binding_hash'], 'layer': layer, 'target': target,
                 'hypothesis': hypothesis, 'observed_issue': issue, 'status': 'PROPOSED',
                 'runtime_loadable': False, 'requires_fresh_adr_before_candidate_implementation': True,
                 'controls': ['originals', 'generation', 'scope', 'model', 'decoding', 'budget', 'assessment_policy'],
                 'validation': ['independent-case paired answer quality', 'critical regressions', 'calls/tokens/p95/cost'],
                 'rollback': 'Retain the frozen Parent; do not activate Candidate if binding or acceptance criteria fail.'}
        ident = 'proposal:' + digest(value)
        value = seal({**value, 'id': ident})
        path = Path(output) / (ident.split(':')[1] + '.json')
        publish(path, value)
        candidates.append({'id': ident, 'path': str(path.resolve()), 'sha256': value['content_sha256']})
    report = seal({'schema_version': 'failure-proposal-report-v1', 'diagnosis_id': diagnosis['id'],
                   'candidates': candidates, 'unresolved_issue_types': sorted({i['type'] for i in diagnosis['issues'] if i['type'] not in TARGETS}),
                   'model_calls': 0, 'runtime_loadable': False})
    path = Path(output) / ('report-' + report['content_sha256'] + '.json')
    publish(path, report)
    return {'state': 'COMPLETED', 'proposals': len(candidates), 'report': str(path.resolve()), 'model_calls': 0}


def freeze_comparison(design):
    """Seal a human-authored split and protocol before any candidate rollout."""
    if design.get('schema_version') != 'failure-comparison-design-v1':
        raise ValueError('comparison design version required')
    for name in ('experiment_id', 'parent_arm', 'candidate_arm', 'generation_id', 'store_sha256',
                 'model', 'decoding_hash', 'budget_hash', 'evaluator_hash', 'parent_code_hash', 'candidate_code_hash'):
        if not isinstance(design.get(name), str) or not design[name]:
            raise ValueError('missing comparison binding: ' + name)
    if design['parent_arm'] == design['candidate_arm']:
        raise ValueError('distinct comparison arms required')
    for name in ('store_sha256', 'decoding_hash', 'budget_hash', 'evaluator_hash', 'parent_code_hash', 'candidate_code_hash'):
        value = design[name]
        if len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('exact comparison SHA-256 required: ' + name)
    splits = design.get('splits', {})
    if set(splits) != {'construction', 'validation', 'holdout'} or any(not isinstance(splits[k], list) or not splits[k] for k in splits):
        raise ValueError('three nonempty comparison splits required')
    cases = set(); families = set()
    for name in ('construction', 'validation', 'holdout'):
        local_families = set()
        for row in splits[name]:
            if set(row) != {'case_id', 'family_id'} or not row['case_id'] or not row['family_id']:
                raise ValueError('case_id and family_id required')
            if row['case_id'] in cases or row['family_id'] in families:
                raise ValueError('comparison case/family leaks across splits')
            cases.add(row['case_id']); local_families.add(row['family_id'])
        families.update(local_families)
    criteria = design.get('criteria', {})
    if set(criteria) != {'min_net_wins', 'max_regressions', 'max_p95_ratio', 'max_cost_ratio'}:
        raise ValueError('complete preregistered criteria required')
    if type(criteria['min_net_wins']) is not int or criteria['min_net_wins'] < 1 or type(criteria['max_regressions']) is not int or criteria['max_regressions'] < 0:
        raise ValueError('invalid quality gate criteria')
    for key in ('max_p95_ratio', 'max_cost_ratio'):
        if type(criteria[key]) not in (int, float) or not math.isfinite(criteria[key]) or criteria[key] <= 0:
            raise ValueError('invalid resource gate criteria')
    return seal({**design, 'schema_version': 'failure-comparison-plan-v1',
                 'gold_visible_to_product': False, 'main_promotion_automatic': False})


def paired_gate(plan, parent, candidate):
    """Compare complete reviewed held-out rows; a pass is never MAIN approval."""
    verify(plan, 'failure-comparison-plan-v1')
    expected = {r['case_id'] for r in plan['splits']['holdout']}
    def arm(value, arm_id, code_hash):
        verify(value, 'failure-comparison-results-v1')
        for key in ('generation_id', 'store_sha256', 'model', 'decoding_hash', 'budget_hash', 'evaluator_hash'):
            if value.get(key) != plan[key]:
                raise ValueError('comparison result binding mismatch: ' + key)
        if value.get('plan_sha256') != plan['content_sha256'] or value.get('arm_id') != arm_id or value.get('code_hash') != code_hash:
            raise ValueError('comparison result arm/code/plan mismatch')
        rows = value.get('cases', [])
        if len(rows) != len(expected) or {r['case_id'] for r in rows} != expected:
            raise ValueError('comparison requires each held-out case exactly once')
        for row in rows:
            if row.get('answer_quality') not in ('PASS', 'FAIL') or type(row.get('critical_error')) is not bool:
                raise ValueError('unreviewed comparison result')
            answer_hash = row.get('answer_sha256')
            if (not isinstance(row.get('reviewer'), str) or not row['reviewer'].strip() or
                    not isinstance(answer_hash, str) or len(answer_hash) != 64 or
                    any(c not in '0123456789abcdef' for c in answer_hash)):
                raise ValueError('answer-bound review receipt required')
            for key in ('duration_seconds', 'cost_usd'):
                v = row.get(key)
                if type(v) not in (float, int) or not math.isfinite(v) or v < 0:
                    raise ValueError('missing/invalid comparison resource measurement')
        return {r['case_id']: r for r in rows}
    before = arm(parent, plan['parent_arm'], plan['parent_code_hash'])
    after = arm(candidate, plan['candidate_arm'], plan['candidate_code_hash'])
    wins = []; losses = []; both_pass = []; both_fail = []; critical = []
    for cid in sorted(expected):
        a = before[cid]['answer_quality'] == 'PASS'; b = after[cid]['answer_quality'] == 'PASS'
        (both_pass if a and b else wins if b else losses if a else both_fail).append(cid)
        if after[cid]['critical_error']:
            critical.append(cid)
    def p95(rows):
        times = sorted(r['duration_seconds'] for r in rows.values())
        return times[math.ceil(len(times)*.95)-1]
    def ratio(new, old):
        return new/old if old else (1.0 if new == 0 else None)
    time_ratio = ratio(p95(after), p95(before))
    cost_ratio = ratio(sum(r['cost_usd'] for r in after.values()), sum(r['cost_usd'] for r in before.values()))
    c = plan['criteria']; reasons = []
    if len(wins)-len(losses) < c['min_net_wins']: reasons.append('QUALITY_GAIN_NOT_MET')
    if len(losses) > c['max_regressions']: reasons.append('REGRESSION_LIMIT_EXCEEDED')
    if critical: reasons.append('CRITICAL_ERRORS')
    if time_ratio is None or time_ratio > c['max_p95_ratio']: reasons.append('LATENCY_LIMIT_EXCEEDED')
    if cost_ratio is None or cost_ratio > c['max_cost_ratio']: reasons.append('COST_LIMIT_EXCEEDED')
    return seal({'schema_version': 'failure-comparison-gate-v1', 'plan_sha256': plan['content_sha256'],
                 'parent_results_sha256': parent['content_sha256'], 'candidate_results_sha256': candidate['content_sha256'],
                 'acceptance_criteria_met': not reasons, 'reasons': reasons,
                 'wins': wins, 'regressions': losses, 'both_pass': both_pass, 'both_fail': both_fail,
                 'critical_errors': critical, 'p95_ratio': time_ratio, 'cost_ratio': cost_ratio,
                 'case_count': len(expected), 'statistical_significance': 'NOT_ESTABLISHED',
                 'main_promotion_automatic': False, 'requires_adr_finalization': True})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('diagnose'); p.add_argument('--journal', action='append', type=Path)
    p.add_argument('--root', type=Path); p.add_argument('--runtime', type=Path)
    p.add_argument('--limit', type=int, default=100); p.add_argument('--output', required=True, type=Path)
    p = sub.add_parser('propose'); p.add_argument('--diagnosis', required=True, type=Path); p.add_argument('--output', required=True, type=Path)
    p = sub.add_parser('comparison-plan'); p.add_argument('--design', required=True, type=Path); p.add_argument('--output', required=True, type=Path)
    p = sub.add_parser('compare')
    for key in ('plan', 'parent', 'candidate', 'output'): p.add_argument('--'+key, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'diagnose':
            if not 1 <= args.limit <= 1000: raise ValueError('diagnostic limit must be 1..1000')
            runtime = args.runtime or load_layout(args.root).path('runtime')/'semantic'
            if args.journal:
                journals = sorted(set(args.journal))
                if len(journals) > args.limit: raise ValueError('explicit journal selection exceeds diagnostic limit')
            else:
                journals = sorted((runtime/'legal-agent/runs').glob('*/*/journal.sqlite'))[:args.limit]
            from .action_memory import negative_feedback
            value = diagnose(journals, args.output, feedback=negative_feedback(runtime))
        elif args.command == 'propose': value = propose(args.diagnosis, args.output)
        elif args.command == 'comparison-plan':
            value = freeze_comparison(read(args.design)); publish(args.output, value)
            value = {'state': 'COMPLETED', 'plan': str(args.output.resolve()), 'sha256': value['content_sha256']}
        else:
            value = paired_gate(read(args.plan), read(args.parent), read(args.candidate)); publish(args.output, value)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        if value.get('acceptance_criteria_met') is False: return 2
        return 1 if value.get('state') == 'PARTIAL' else 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({'state': 'FAILED', 'error_type': type(exc).__name__}, ensure_ascii=False))
        return 1
