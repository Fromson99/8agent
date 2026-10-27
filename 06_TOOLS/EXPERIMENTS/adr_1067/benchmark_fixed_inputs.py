"""Offline saved-wire schema microbenchmark, NOT a service/canonical replay.

Run baseline and optimized as separate sequential processes, then compare their
artifacts. No model, corpus, journal, source store, or index is opened. Saved
requests are read only to extract response_format.json_schema.schema; question,
source and response contents are never copied into the output artifact.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace

import jsonschema
from jsonschema.validators import validator_for


ROOT = Path(__file__).resolve().parents[3]
VERSION = 'adr1067-saved-wire-schema-micro-v1'
ITERATIONS = 6  # validator-cache cold 1 + repeated exact-schema warm 5
EXPECTED_CALLS = 19
MAX_INPUT_BYTES = 4 * 1024 * 1024
ALIAS = '_adr1067_micro_runtime'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value, *, ordered=False):
    return json.dumps(value, ensure_ascii=False, sort_keys=not ordered,
        separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value, *, ordered=False):
    return hashlib.sha256(encoded(value, ordered=ordered)).hexdigest()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    require(Path(path).stat().st_size <= MAX_INPUT_BYTES, 'input file exceeds small-file scope')
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_once(path, report):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def frozen_binding(code, arm):
    code = Path(code).resolve()
    require(code.name == 'snapshot' and code.parent.parent.name == 'revisions',
        'code must be an explicit frozen revisions/<revision>/snapshot path')
    manifest_path = code.parents[2] / 'candidate.json'
    manifest = read(manifest_path)
    require(manifest.get('adr_id') == 'ADR-1067' and manifest.get('arm_id') == arm
        and manifest.get('production_loadable') is False, 'unexpected candidate/arm binding')
    matches = [r for r in manifest['revisions'] if r['revision_id'] == code.parent.name]
    require(len(matches) == 1, 'frozen revision is missing or ambiguous')
    revision = matches[0]
    require(digest({k: v for k, v in revision.items() if k != 'revision_sha256'})
        == revision['revision_sha256'], 'revision metadata hash mismatch')
    files = {}
    for row in revision['files']:
        path = (ROOT / row['frozen_path']).resolve()
        require(path.is_relative_to(code), 'frozen file escaped code root')
        relative = str(path.relative_to(code))
        require(relative not in files, 'duplicate frozen file')
        files[relative] = row['snapshot_sha256']
    require(files, 'empty frozen file map')
    binding = {'code_root': str(code), 'manifest_path': str(manifest_path),
        'manifest_sha256': sha(manifest_path), 'revision_id': revision['revision_id'],
        'revision_sha256': revision['revision_sha256'], 'arm_id': arm,
        'registered_file_count': len(files)}
    return code, files, binding


def check_files(code, files, relatives):
    result = {}
    for relative in sorted(relatives):
        require(relative in files, 'imported/relevant code is not registered: ' + relative)
        actual = sha(code / relative)
        require(actual == files[relative], 'frozen code file changed: ' + relative)
        result[relative] = actual
    return result


def local_references_only(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ('$ref', '$dynamicRef', '$recursiveRef') and isinstance(child, str):
                require(not child or child.startswith('#'), 'external schema references are outside offline scope')
            local_references_only(child)
    elif isinstance(value, list):
        for child in value:
            local_references_only(child)


def discover(matrix_root):
    """Select exact saved physical START records, without reading user views."""
    root = Path(matrix_root).resolve()
    rows = []
    inputs = {}
    for events_path in sorted(root.glob('*/physical-calls.jsonl')):
        require(events_path.stat().st_size <= MAX_INPUT_BYTES, 'physical event log too large')
        inputs[str(events_path)] = sha(events_path)
        seen = set()
        with events_path.open(encoding='utf-8') as stream:
            for line in stream:
                event = json.loads(line)
                if event.get('event') != 'START' or not event.get('phase', '').startswith('source-law-navigation-'):
                    continue
                call = event['call']
                require(type(call) is int and call > 0 and call not in seen, 'duplicate/invalid physical call')
                seen.add(call)
                folder = events_path.parent / 'model' / f'call-{call:03d}-service'
                request_path, response_path = folder / 'request.json', folder / 'response.json'
                request = read(request_path)
                schema = request['response_format']['json_schema']['schema']
                local_references_only(schema)
                del request  # the prompt/originals are not retained by the benchmark
                response = read(response_path)
                choices = response['choices']
                require(len(choices) == 1, 'response must contain one saved choice')
                content = choices[0]['message']['content']
                require(isinstance(content, str), 'response content is not a JSON string')
                value = json.loads(content)
                require(isinstance(value, dict) and 'choice' in value, 'navigation response has no explicit choice')
                for path in (request_path, response_path):
                    inputs[str(path)] = sha(path)
                rows.append({'case': events_path.parent.name, 'call': call, 'phase': event['phase'],
                    'request_path': str(request_path), 'request_sha256': inputs[str(request_path)],
                    'response_path': str(response_path), 'response_sha256': inputs[str(response_path)],
                    'schema_ordered_sha256': digest(schema, ordered=True),
                    'schema_canonical_sha256': digest(schema),
                    'schema_chars': len(encoded(schema, ordered=True).decode('utf-8')),
                    'schema_bytes': len(encoded(schema, ordered=True)),
                    'actual_value_sha256': digest(value), 'schema': schema, 'value': value})
    rows.sort(key=lambda row: (row['case'], row['call']))
    require(len(rows) == EXPECTED_CALLS, f'expected {EXPECTED_CALLS} navigation inputs, found {len(rows)}')
    return rows, inputs


def error_descriptor(error):
    # Values/messages can contain response text; only the digest leaves memory.
    return {'class': type(error).__name__, 'message': error.message,
        'validator': error.validator, 'validator_value': error.validator_value,
        'path': list(error.path), 'schema_path': list(error.schema_path),
        'context': [error_descriptor(child) for child in error.context]}


def outcome(error):
    return {'status': 'VALID' if error is None else type(error).__name__,
        'selected_error_sha256': None if error is None else digest(error_descriptor(error))}


def load_helper(code):
    runtime = code / '02_BACKEND/semantic_runtime'
    require(ALIAS not in sys.modules, 'benchmark runtime was already loaded')
    spec = importlib.util.spec_from_file_location(ALIAS, runtime / '__init__.py',
        submodule_search_locations=[str(runtime)])
    package = importlib.util.module_from_spec(spec)
    sys.modules[ALIAS] = package
    spec.loader.exec_module(package)
    return importlib.import_module(ALIAS + '.legal_agent.schema_preparation')


def imported_files(code):
    result = set()
    for name, module in list(sys.modules.items()):
        if name == ALIAS or name.startswith(ALIAS + '.'):
            path = Path(module.__file__).resolve()
            require(path.is_relative_to(code), 'candidate runtime import escaped frozen code')
            result.add(str(path.relative_to(code)))
    return result


def measure_case(row, variant, value, arm, helper):
    schema = row['schema']
    owner = SimpleNamespace()  # fresh validator cache for each fixed schema/value pair
    key = (validator_for(schema), encoded(schema, ordered=True).decode('utf-8'))
    samples = []
    for iteration in range(ITERATIONS):
        cache = getattr(owner, '_navigation_schema_validators', None)
        cache_hit = bool(cache is not None and key in cache._entries)
        error = None
        wall_start = time.perf_counter_ns()
        cpu_start = time.thread_time_ns()
        try:
            if arm == 'baseline':
                jsonschema.validate(value, schema)
            else:
                helper.validate(value, schema, owner=owner)
        except (jsonschema.ValidationError, jsonschema.SchemaError) as exc:
            error = exc
        cpu_ns = time.thread_time_ns() - cpu_start
        wall_ns = time.perf_counter_ns() - wall_start
        samples.append({'iteration': iteration, 'temperature': 'cold' if iteration == 0 else 'warm',
            'wall_ns': wall_ns, 'thread_cpu_ns': cpu_ns,
            'cache_entry_present_before_validation': cache_hit, **outcome(error)})
    # Untimed full enumeration additionally checks order beyond best_match's
    # chosen error/context. The optimized path uses its actual prepared object.
    cache = getattr(owner, '_navigation_schema_validators', None)
    validator = cache._entries[key][0] if cache is not None and key in cache._entries else validator_for(schema)(schema)
    ordered_errors = [error_descriptor(error) for error in validator.iter_errors(value)]
    observed = {(sample['status'], sample['selected_error_sha256']) for sample in samples}
    require(len(observed) == 1, 'validation result changed across identical iterations')
    require(samples[0]['status'] != 'SchemaError', 'saved wire schema itself is invalid')
    require(variant != 'missing_choice' or samples[0]['status'] == 'ValidationError',
        'deterministic missing-choice variant unexpectedly passed')
    warm = samples[1:]
    return {'case': row['case'], 'call': row['call'], 'variant': variant,
        'value_sha256': digest(value), 'schema_ordered_sha256': row['schema_ordered_sha256'],
        'schema_chars': row['schema_chars'], 'schema_bytes': row['schema_bytes'],
        'samples': samples, 'ordered_errors_sha256': digest(ordered_errors),
        'ordered_error_count': len(ordered_errors),
        'cache_hits': sum(sample['cache_entry_present_before_validation'] for sample in samples),
        'warm_median_wall_ns': statistics.median(sample['wall_ns'] for sample in warm),
        'warm_max_wall_ns': max(sample['wall_ns'] for sample in warm),
        'warm_median_thread_cpu_ns': statistics.median(sample['thread_cpu_ns'] for sample in warm)}


def runtime_binding():
    import jsonschema.exceptions
    import jsonschema.validators
    return {'python': sys.version, 'executable': sys.executable,
        'jsonschema_version': importlib.metadata.version('jsonschema'),
        'referencing_version': importlib.metadata.version('referencing'),
        'jsonschema_validators_sha256': sha(jsonschema.validators.__file__),
        'jsonschema_exceptions_sha256': sha(jsonschema.exceptions.__file__)}


def run(args):
    require(not Path(args.output).exists(), 'output already exists; use a new artifact path')
    baseline, baseline_files, baseline_binding = frozen_binding(args.baseline_code, 'B0')
    optimized, optimized_files, optimized_binding = frozen_binding(args.optimized_code, 'B1')
    relevant = {'02_BACKEND/semantic_runtime/legal_agent/' + name for name in
        ('decision_projection.py', 'law_navigation.py', 'navigation_tasks.py', 'repository.py')}
    before = {'baseline': check_files(baseline, baseline_files, relevant),
        'optimized': check_files(optimized, optimized_files,
            relevant | {'02_BACKEND/semantic_runtime/legal_agent/schema_preparation.py'})}
    helper = load_helper(optimized) if args.arm == 'optimized' else None
    loaded = imported_files(optimized) if helper is not None else set()
    before['optimized'].update(check_files(optimized, optimized_files, loaded))
    rows, inputs = discover(args.matrix_root)
    case_bindings = [{key: value for key, value in row.items() if key not in ('schema', 'value')} for row in rows]
    script_hash = sha(__file__)
    results = []
    for row in rows:
        results.append(measure_case(row, 'actual_response', row['value'], args.arm, helper))
        invalid = deepcopy(row['value'])
        del invalid['choice']
        results.append(measure_case(row, 'missing_choice', invalid, args.arm, helper))
    for path, expected in inputs.items():
        require(sha(path) == expected, 'saved input changed during benchmark')
    require(sha(__file__) == script_hash, 'benchmark script changed during execution')
    require(sha(baseline_binding['manifest_path']) == baseline_binding['manifest_sha256']
        and sha(optimized_binding['manifest_path']) == optimized_binding['manifest_sha256'],
        'candidate binding changed during execution')
    after = {'baseline': check_files(baseline, baseline_files, before['baseline']),
        'optimized': check_files(optimized, optimized_files, before['optimized'])}
    require(before == after, 'code file map changed during benchmark')
    require(not helper or imported_files(optimized) == loaded, 'late runtime import requires an additional binding')
    report = {'schema_version': VERSION, 'status': 'COMPLETE', 'arm': args.arm,
        'created_at': datetime.now(timezone.utc).isoformat(), 'script_sha256': script_hash,
        'scope': 'saved_wire_schema_microbenchmark', 'service_performance_claim': False,
        'canonical_action_reconstruction': 'NOT_PERFORMED_REQUIRES_ORIGINAL_TASK_AND_STATE',
        'measured_function': ('jsonschema.validate(instance, saved_wire_schema)' if args.arm == 'baseline'
            else 'frozen schema_preparation.validate(instance, saved_wire_schema, owner=request)'),
        'cold_definition': 'First validation on a fresh owner; library/import/OS caches are not reset.',
        'profiling': 'R2 observer is not installed; candidate latency.span follows its inactive path.',
        'limitations': [
            'Saved response_format schema is tested, not the server canonical action contract.',
            'Schema key order is the saved JSON order; original pre-serialization dict order is not asserted.',
            'Cold means a fresh validator cache, not a fresh OS/DB/import cache.',
            'Each schema/value pair has its own owner: warm hits measure repeated-schema potential, not production hit rate.',
            'Only validation calls are timed; loading, error fingerprints and full error-order audit are untimed.',
            'No service, tool, legal meaning, source/ACL/state commit, model or corpus path is exercised.'],
        'runtime': runtime_binding(), 'code_bindings': {'baseline': baseline_binding, 'optimized': optimized_binding},
        'verified_code_files_before': before, 'verified_code_files_after': after,
        'source_files': inputs, 'dataset_sha256': digest(case_bindings), 'cases': case_bindings,
        'workload': {'saved_navigation_calls': len(rows), 'variants_per_call': 2,
            'cold_iterations': 1, 'warm_iterations': 5, 'timed_validations': len(results) * ITERATIONS,
            'model_calls': 0, 'source_db_reads': 0}, 'results': results}
    write_once(args.output, report)
    print(json.dumps({'status': report['status'], 'arm': args.arm,
        'saved_navigation_calls': len(rows), 'timed_validations': len(results) * ITERATIONS,
        'artifact': str(Path(args.output).resolve())}))


def compare(args):
    baseline, optimized = read(args.baseline_result), read(args.optimized_result)
    require(baseline['schema_version'] == optimized['schema_version'] == VERSION, 'result schema differs')
    require(baseline['arm'] == 'baseline' and optimized['arm'] == 'optimized', 'result arms are reversed')
    for key in ('status', 'script_sha256', 'dataset_sha256', 'cases', 'source_files', 'runtime', 'workload', 'code_bindings'):
        require(baseline[key] == optimized[key], 'benchmark binding/workload differs: ' + key)
    require(baseline['status'] == 'COMPLETE', 'cannot compare incomplete benchmark')
    require(len(baseline['results']) == len(optimized['results']) == EXPECTED_CALLS * 2, 'result count differs')
    rows = []
    mismatches = []
    for old, new in zip(baseline['results'], optimized['results']):
        identity = {key: old[key] for key in ('case', 'call', 'variant')}
        for key in ('case', 'call', 'variant', 'value_sha256', 'schema_ordered_sha256', 'schema_chars', 'schema_bytes',
                    'ordered_errors_sha256', 'ordered_error_count'):
            if old[key] != new[key]: mismatches.append({**identity, 'field': key})
        require(len(old['samples']) == len(new['samples']) == ITERATIONS, 'iteration count differs')
        for a, b in zip(old['samples'], new['samples']):
            for key in ('iteration', 'temperature', 'status', 'selected_error_sha256'):
                if a[key] != b[key]: mismatches.append({**identity, 'iteration': a['iteration'], 'field': key})
        base_median, opt_median = old['warm_median_wall_ns'], new['warm_median_wall_ns']
        rows.append({**identity, 'baseline_cold_wall_ns': old['samples'][0]['wall_ns'],
            'optimized_cold_wall_ns': new['samples'][0]['wall_ns'],
            'baseline_warm_median_wall_ns': base_median, 'optimized_warm_median_wall_ns': opt_median,
            'baseline_warm_median_thread_cpu_ns': old['warm_median_thread_cpu_ns'],
            'optimized_warm_median_thread_cpu_ns': new['warm_median_thread_cpu_ns'],
            'warm_wall_reduction_fraction': 1 - opt_median / base_median if base_median else None,
            'optimized_cache_hits': new['cache_hits']})
    report = {'schema_version': VERSION, 'status': 'EQUIVALENT' if not mismatches else 'MISMATCH',
        'scope': 'saved_wire_schema_microbenchmark', 'service_performance_claim': False,
        'baseline_result': {'path': str(Path(args.baseline_result).resolve()), 'sha256': sha(args.baseline_result)},
        'optimized_result': {'path': str(Path(args.optimized_result).resolve()), 'sha256': sha(args.optimized_result)},
        'dataset_sha256': baseline['dataset_sha256'], 'workload_per_arm': baseline['workload'],
        'error_result_and_order_equal': not mismatches, 'mismatches': mismatches, 'rows': rows,
        'limitations': baseline['limitations'] + ['Independent process order and machine scheduling are not randomized by this helper.']}
    write_once(args.output, report)
    print(json.dumps({'status': report['status'], 'pairs': len(rows), 'mismatches': len(mismatches),
        'artifact': str(Path(args.output).resolve())}))
    return 0 if not mismatches else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    run_parser = subparsers.add_parser('run')
    run_parser.add_argument('--arm', required=True, choices=('baseline', 'optimized'))
    run_parser.add_argument('--baseline-code', required=True, type=Path)
    run_parser.add_argument('--optimized-code', required=True, type=Path)
    run_parser.add_argument('--matrix-root', required=True, type=Path)
    run_parser.add_argument('--output', required=True, type=Path)
    compare_parser = subparsers.add_parser('compare')
    compare_parser.add_argument('--baseline-result', required=True, type=Path)
    compare_parser.add_argument('--optimized-result', required=True, type=Path)
    compare_parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'run':
        run(args)
        return 0
    return compare(args)


if __name__ == '__main__':
    raise SystemExit(main())
