"""Read saved R2/v3 timing profiles; never run an application or benchmark.

Only numeric/code-label fields enter the output. The R2 extractor is reused
without modifying it. Direct profiles describe their request scope; an explicit
service receipt may additionally establish service wall time.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
R2_PATH = ROOT/'08_DEPLOYMENT/GENOS/handoffs/function_timing_20261024_r2/extract.py'
R2_SHA = 'e911b12cab9f0b557aa87bf5ff48fe3d63b3a4d733bf91ded836083a57e0e395'
VERSION = 'adr1070-timing-extraction-v1'
MAX_INPUT = 32*1024*1024
PROFILE_SCHEMAS = {'genos-function-timing-v1','genos-function-timing-v2','genos-function-timing-v3'}
COUNTERS = {'candidate_count','source_count','page_count','row_count','block_count','span_count',
    'action_count','query_count','schema_count','item_count','byte_count','request_bytes',
    'response_bytes','source_bytes','encoded_bytes','characters','cache_hits','cache_misses',
    'cache_hit','cache_bypass','schema_bytes','validation_count'}
CATEGORIES = {'copy','encode_hash','schema_validation','state_validation','ontology','source_integrity',
    'read_review','input_preparation','state_storage','source_query','navigation_view','model_adapter',
    'other_instrumented','startup_preparation'}
_R2 = None


class ExtractionError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ExtractionError(code)


def numeric(value):
    return type(value) in (int,float) and 0 <= value <= 1e18 and math.isfinite(value)


def legacy():
    global _R2
    if _R2 is None:
        require(hashlib.sha256(R2_PATH.read_bytes()).hexdigest() == R2_SHA, 'R2_READER_CHANGED')
        spec = importlib.util.spec_from_file_location('_adr1070_r2_timing_reader', R2_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _R2 = module
    return _R2


def merged(intervals, end):
    result = []
    for lo,hi in sorted((max(0,lo),min(end,hi)) for lo,hi in intervals):
        if hi <= lo:
            continue
        if result and lo <= result[-1][1]:
            result[-1][1] = max(result[-1][1],hi)
        else:
            result.append([lo,hi])
    return result


def length(intervals):
    return sum(hi-lo for lo,hi in intervals)


def without(intervals, excluded):
    """Both arguments are disjoint interval lists in the same clock domain."""
    return sum(max(0,hi-lo)-sum(max(0,min(hi,b)-max(lo,a)) for a,b in excluded)
               for lo,hi in intervals)


def safe_profile(raw):
    require(type(raw) is dict and raw.get('schema_version') in PROFILE_SCHEMAS, 'INVALID_PROFILE')
    version = raw['schema_version']
    compat = {**raw,'schema_version':'genos-function-timing-v2'} if version.endswith('v3') else raw
    try:
        profile = legacy().safe_profile(compat)
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError,legacy().ExtractionError) as error:
        raise ExtractionError('INVALID_R2_PROFILE_FIELDS') from error
    profile['schema_version'] = version
    for key in ('collection_complete','sampling_enabled','gc_observation_enabled'):
        if type(raw.get(key)) is bool:
            profile[key] = raw[key]
    # R2 discards unknown function fields; extend exactly these numeric fields.
    for row,original in zip(profile['functions'],raw.get('functions',[])):
        for key in ('non_model_attempt_ms','non_model_attempt_self_ms'):
            if numeric(original.get(key)):
                row[key] = original[key]
    counters = raw.get('numeric_counters')
    if counters is not None:
        require(type(counters) is dict and len(counters) <= 256, 'COUNTER_LIMIT')
        profile['numeric_counters'] = {}
        for name,values in counters.items():
            if not legacy().token(name):
                continue
            require(type(values) is dict, 'INVALID_COUNTER_ROW')
            profile['numeric_counters'][name] = {k:v for k,v in values.items() if k in COUNTERS and numeric(v)}
    attribution = raw.get('attribution')
    if attribution is not None:
        require(type(attribution) is dict, 'INVALID_ATTRIBUTION')
        rows = attribution.get('categories',[])
        require(type(rows) is list and len(rows) <= 32, 'CATEGORY_LIMIT')
        profile['attribution'] = {'categories':[
            {'category':r['category'],'thread_wall_ms':r['thread_wall_ms']} for r in rows
            if type(r) is dict and r.get('category') in CATEGORIES and numeric(r.get('thread_wall_ms'))]}
    timing = raw.get('model_attempt_timing')
    if timing is not None:
        require(type(timing) is dict and timing.get('basis') == 'MODEL_ATTEMPT', 'INVALID_MODEL_BASIS')
        require(numeric(timing.get('window_ms')) and type(timing.get('complete')) is bool, 'INVALID_MODEL_WINDOW')
        rows = timing.get('intervals')
        require(type(rows) is list and len(rows) <= 2048, 'MODEL_INTERVAL_LIMIT')
        cleaned = []
        for row in rows:
            require(type(row) is dict and type(row.get('number')) is int and row['number'] > 0,
                    'INVALID_MODEL_INTERVAL')
            lo,hi = row.get('start_ms'),row.get('end_ms')
            require(numeric(lo) and (hi is None or numeric(hi) and hi >= lo), 'INVALID_MODEL_INTERVAL')
            item = {'number':row['number'],'start_ms':lo,'end_ms':hi}
            if legacy().token(row.get('stage')):
                item['stage'] = row['stage']
            cleaned.append(item)
        require(len({r['number'] for r in cleaned}) == len(cleaned), 'DUPLICATE_MODEL_INTERVAL')
        complete = timing['complete']
        require(not complete or all(r['end_ms'] is not None for r in cleaned), 'UNFINISHED_MODEL_INTERVAL')
        if numeric(profile.get('model_calls')) and complete:
            require(profile['model_calls'] == len(cleaned), 'MODEL_COUNT_MISMATCH')
        actual = length(merged([(r['start_ms'],r['end_ms']) for r in cleaned if r['end_ms'] is not None],timing['window_ms']))
        tolerance = .005+.002*len(cleaned)  # stored interval endpoints round to 3 decimals
        if numeric(timing.get('completed_union_ms')):
            require(abs(timing['completed_union_ms']-actual) <= tolerance, 'MODEL_UNION_MISMATCH')
        profile['model_attempt_timing'] = {'basis':'MODEL_ATTEMPT','window_ms':timing['window_ms'],
            'complete':complete,'completed_union_ms':actual,'intervals':cleaned,
            'raw_network_timing':'NOT_MEASURED','pure_model_inference_timing':'NOT_MEASURED'}
    return profile


def profiles_from(value):
    """Visit known wrappers only; do not inspect a request/journal/source body."""
    found = []
    seen_nodes = 0
    def visit(node, depth=0):
        nonlocal seen_nodes
        seen_nodes += 1
        require(depth <= 10 and seen_nodes <= 10000, 'WRAPPER_LIMIT')
        if type(node) is dict:
            if node.get('schema_version') in PROFILE_SCHEMAS:
                found.append(safe_profile(node))
                require(len(found) <= 100, 'PROFILE_COUNT_LIMIT')
                return
            for key in ('profile','profiles','events','fields','payload','summary','summaries','service_events','function_profiles'):
                if key in node:
                    visit(node[key],depth+1)
        elif type(node) is list:
            for item in node:
                visit(item,depth+1)
    if type(value) is dict:
        schema = str(value.get('schema_version','')).lower()
        require('micro' not in schema and 'benchmark' not in schema, 'MICROBENCHMARK_IS_NOT_SERVICE_TIMING')
    visit(value)
    require(found, 'NO_TIMING_PROFILE')
    return found


def analyze_profile(profile, *, service_wall_ms=None, top=12):
    warnings = list(profile.get('warnings',[]))
    segments = profile.get('segments',[])
    timing = profile.get('model_attempt_timing')
    scope = timing['window_ms'] if timing else profile.get('request_scope_ms')
    complete = timing['complete'] if timing else None
    model_union = None
    complete_union = None
    model_intervals = []
    if timing:
        model_intervals = merged([(r['start_ms'],r['end_ms']) for r in timing['intervals']
                                  if r['end_ms'] is not None],scope)
        complete_union = length(model_intervals)
        model_union = complete_union if complete else None
    elif segments and numeric(scope):
        valid = all(numeric(r.get('start_ms')) and numeric(r.get('wall_ms')) for r in segments)
        models = [r for r in segments if r['segment'].startswith('M')]
        count_matches = numeric(profile.get('model_calls')) and len(models) == profile['model_calls']
        if valid and count_matches and not any(w in warnings for w in ('MODEL_CALL_OPEN_AT_REQUEST_END','SEGMENT_LIMIT','BOUNDARY_ERROR')):
            model_intervals = merged([(r['start_ms'],r['start_ms']+r['wall_ms'])
                                      for r in segments if r['segment'].startswith('M')],scope)
            model_union = complete_union = length(model_intervals)
            complete = True
            warnings.append('LEGACY_SEGMENT_BOUNDARY_BASIS')
    scope_nonmodel = max(0,scope-model_union) if numeric(scope) and numeric(model_union) else None
    service_nonmodel = max(0,service_wall_ms-model_union) if numeric(service_wall_ms) and numeric(model_union) else None
    if numeric(service_wall_ms) and numeric(scope):
        require(service_wall_ms+.01 >= scope, 'SERVICE_WINDOW_SMALLER_THAN_PROFILE')
    phases = []
    for row in segments:
        phases.append({k:v for k,v in row.items() if k in ('segment','start_ms','wall_ms','stage','previous_stage',
            'next_stage','same_thread','thread_cpu_ms','runqueue_wait_ms','gc_ms','gc_count','hook_calls','threads_max')})
    phase_covered = None
    if numeric(scope_nonmodel) and segments and all(numeric(r.get('start_ms')) and numeric(r.get('wall_ms')) for r in segments):
        outside = merged([(r['start_ms'],r['start_ms']+r['wall_ms']) for r in segments
                          if not r['segment'].startswith('M')],scope)
        phase_covered = min(scope_nonmodel,max(0,without(outside,model_intervals)))
    categories = sorted(profile.get('attribution',{}).get('categories',[]),key=lambda r:-r['thread_wall_ms'])
    known_functions = [row for row in profile['functions'] if numeric(row.get('non_model_attempt_self_ms'))]
    function_basis = 'exclusive-instrumented-thread-wall-outside-MODEL_ATTEMPT'
    sort_key = 'non_model_attempt_self_ms'
    if not known_functions:
        known_functions = [r for r in profile['functions'] if numeric(r.get('self_ms'))]
        sort_key = 'self_ms'
        function_basis = 'legacy-exclusive-hook-wall-including-model-attempts'
    top_functions = sorted(known_functions,key=lambda r:-r[sort_key])[:top]
    named = sum(r['thread_wall_ms'] for r in categories if r['category'] != 'other_instrumented') if categories else None
    comparable = (profile.get('collection_complete') is True and numeric(named) and numeric(scope_nonmodel) and profile.get('thread_count') == 1
                  and profile.get('concurrency_peak') == 1 and named <= scope_nonmodel+.1)
    coverage = {'phase_covered_ms':phase_covered,
        'scope_phase_unattributed_ms':max(0,scope_nonmodel-phase_covered) if numeric(phase_covered) else None,
        'phase_coverage_pct':100*phase_covered/scope_nonmodel if numeric(phase_covered) and scope_nonmodel > 0 else None,
        'named_exclusive_thread_ms':named,
        'function_wall_comparable':comparable,
        'named_function_scope_coverage_pct':100*named/scope_nonmodel if comparable and scope_nonmodel > 0 else None,
        'scope_function_unattributed_ms':max(0,scope_nonmodel-named) if comparable else None,
        'service_function_unattributed_ms':max(0,service_nonmodel-named) if comparable and numeric(service_nonmodel) else None,
        'basis':'instrumented parents include their uninstrumented children; concurrency is not request wall attribution'}
    return {'schema_version':profile['schema_version'],'mode':profile.get('mode'),
        'probe_revision':profile.get('probe_revision'),'collection_complete':profile.get('collection_complete'),
        'service_wall_ms':service_wall_ms,'profile_scope_wall_ms':scope,
        'model_attempt_timing_complete':complete,'model_attempt_union_ms':model_union,
        'completed_attempt_union_ms':complete_union,'scope_non_model_attempt_wall_ms':scope_nonmodel,
        'service_non_model_attempt_wall_ms':service_nonmodel,
        'raw_network_timing':'NOT_MEASURED','pure_model_inference_timing':'NOT_MEASURED',
        'warnings':warnings,'coverage':coverage,'phases':phases,'categories':categories,
        'top_functions_basis':function_basis,'top_exclusive_functions':top_functions,
        'numeric_counters':profile.get('numeric_counters'),
        'sampling':profile.get('sampling') if profile.get('mode') != 'coarse' else None,
        'source_call_counts':({k:profile.get(k) for k in ('source_calls','source_unique_blocks','source_repeated_blocks')}
                              if profile.get('mode') == 'full' else None)}


def analyze(value, *, top=12):
    profiles = profiles_from(value)
    seconds = value.get('service_seconds') if type(value) is dict and value.get('schema_version') == 'non-model-service-profile-v1' else None
    service_ms = seconds*1000 if numeric(seconds) else None
    receipt_complete = value.get('profile_complete') if type(value) is dict and value.get('schema_version') == 'non-model-service-profile-v1' else None
    results = [analyze_profile(p,service_wall_ms=service_ms if len(profiles)==1 else None,top=top)
               for p in profiles]
    if receipt_complete is False:
        for result in results:
            result['service_non_model_attempt_wall_ms'] = None
            result['coverage']['service_function_unattributed_ms'] = None
            result['warnings'].append('INCOMPLETE_SERVICE_CAPTURE')
    return {'schema_version':VERSION,'analysis_kind':'saved-profile-extraction-not-performance-experiment',
        'profile_count':len(profiles),'reader':{'path':str(R2_PATH.relative_to(ROOT)),'sha256':R2_SHA},
        'service_capture_complete':receipt_complete if type(receipt_complete) is bool else None,
        'profiles':results,
        'microbenchmark_is_service_latency':False,'legal_quality_evaluated':False}


def fmt(value):
    return f'{value:,.3f}' if numeric(value) else '미측정/미확인'


def text_report(report):
    lines = ['저장 계측 분석 — 성능 실험·법률 품질 평가 아님',
        'MODEL_ATTEMPT는 send_once 전체(파싱·콜백 포함). 순수 추론·raw network 시간은 미측정.',
        '함수 시간은 계측된 자식만 제외한 thread wall이며 동시 스레드 합을 요청 wall로 합산하지 않음.']
    for number,p in enumerate(report['profiles'],1):
        lines += ['',f"[{number}] {p['schema_version']} / {p['mode'] or '모드 미확인'}",
            f"서비스 전체 ms: {fmt(p['service_wall_ms'])}; 프로브 scope ms: {fmt(p['profile_scope_wall_ms'])}",
            f"MODEL_ATTEMPT 합집합 ms: {fmt(p['model_attempt_union_ms'])}; scope 모델 밖 ms: {fmt(p['scope_non_model_attempt_wall_ms'])}",
            f"서비스 모델 밖 ms: {fmt(p['service_non_model_attempt_wall_ms'])}",
            f"phase 귀속 ms: {fmt(p['coverage']['phase_covered_ms'])}; scope 미귀속 ms: {fmt(p['coverage']['scope_phase_unattributed_ms'])}",
            f"이름 있는 함수 분류 coverage %: {fmt(p['coverage']['named_function_scope_coverage_pct'])}; 함수 미귀속 ms: {fmt(p['coverage']['scope_function_unattributed_ms'])}",
            '경고: '+(', '.join(p['warnings']) or '기록된 경고 없음')]
        lines.append('구간 | 단계 | wall ms | thread CPU ms')
        for row in p['phases']:
            lines.append(f"{row['segment']} | {row.get('stage') or row.get('next_stage') or '-'} | {fmt(row.get('wall_ms'))} | {fmt(row.get('thread_cpu_ms'))}")
        lines.append('분류 | exclusive thread ms')
        for row in p['categories']:
            lines.append(f"{row['category']} | {fmt(row['thread_wall_ms'])}")
        lines.append('상위 함수 ('+p['top_functions_basis']+') | 호출 | exclusive ms')
        for row in p['top_exclusive_functions']:
            value = row.get('non_model_attempt_self_ms') if 'non_model_attempt_self_ms' in row else row.get('self_ms')
            lines.append(f"{row.get('function','이름 미확인')} | {fmt(row.get('calls'))} | {fmt(value)}")
        lines.append('숫자 카운터 | 값')
        if p['numeric_counters'] is None:
            lines.append('미수집')
        else:
            for name,values in sorted(p['numeric_counters'].items()):
                for key,value in sorted(values.items()):
                    lines.append(f'{name}.{key} | {fmt(value)}')
    return '\n'.join(lines)+'\n'


def read(path):
    path = Path(path).resolve()
    require(path.is_file() and path.stat().st_size <= MAX_INPUT, 'INPUT_SIZE_OR_FILE')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path,'rb') as stream:
        raw = stream.read(MAX_INPUT+1)
    require(len(raw) <= MAX_INPUT, 'DECOMPRESSED_INPUT_LIMIT')
    def invalid_constant(value):
        raise ExtractionError('NONFINITE_JSON')
    def unique_pairs(pairs):
        out = {}
        for key,value in pairs:
            require(key not in out, 'DUPLICATE_JSON_FIELD')
            out[key] = value
        return out
    return json.loads(raw,parse_constant=invalid_constant,object_pairs_hook=unique_pairs),digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--top',type=int,default=12)
    args = parser.parse_args(argv)
    try:
        require(1 <= args.top <= 40, 'TOP_LIMIT')
        value,sha = read(args.input)
        report = analyze(value,top=args.top)
        report['input_sha256'] = sha
        root = args.output_dir.resolve()
        json_path,txt_path = root/'TIMING.json',root/'SUMMARY.txt'
        require(args.input.resolve() not in (json_path,txt_path), 'INPUT_OUTPUT_COLLISION')
        require(not json_path.exists() and not txt_path.exists(), 'OUTPUT_EXISTS')
        root.mkdir(parents=True,exist_ok=True)
        with json_path.open('x',encoding='utf-8') as stream:
            json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.write('\n')
        with txt_path.open('x',encoding='utf-8') as stream:
            stream.write(text_report(report))
        print(f'EXTRACTION_COMPLETE profiles={report["profile_count"]} json={json_path} text={txt_path}')
        return 0
    except (ExtractionError,ValueError,TypeError,KeyError,OverflowError,OSError,RecursionError) as error:
        code = str(error) if isinstance(error,ExtractionError) else type(error).__name__
        print('EXTRACTION_FAILED '+code,file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
