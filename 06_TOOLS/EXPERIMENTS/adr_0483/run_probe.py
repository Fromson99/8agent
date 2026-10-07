"""Run one candidate-bound Qwen reference-resolution call for ADR-0483."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0483-qwen-ambiguous-reference-probe'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0483/qwen-reference-review'
MODEL = 'qwen/qwen3.5-122b-a10b'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text())

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def frozen_client():
    design = read(ADR / 'artifacts/frozen-design.json')
    for relative, expected in design['file_hashes'].items():
        if sha(ROOT / relative) != expected:
            raise RuntimeError('Frozen input changed: ' + relative)
    candidate = read(CAND / 'candidate.json')
    revision = candidate['revisions'][0]
    for row in revision['files']:
        if sha(ROOT / row['frozen_path']) != row['snapshot_sha256']:
            raise RuntimeError('Frozen candidate changed')
    module_path = CAND / 'revisions' / revision['revision_id'] / 'snapshot/02_BACKEND/lawrag/research/experiment_client.py'
    spec = importlib.util.spec_from_file_location('adr0483_experiment_client', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return design, module.OpenRouterProxyClient

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    design, Client = frozen_client()
    fixture = read(ADR / 'fixture.json')
    cases = fixture['cases']
    product_cases = [{k: v for k, v in case.items() if k != 'gold'} for case in cases]
    case_ids = [c['case_id'] for c in cases]
    all_candidate_ids = {c['case_id']: {x['id'] for x in c['candidates']} for c in cases}
    schema = {
        'type': 'object', 'additionalProperties': False, 'required': ['resolutions'],
        'properties': {'resolutions': {'type': 'array', 'minItems': 12, 'maxItems': 12, 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['case_id', 'decision', 'candidate_ids', 'evidence_ids', 'reason'],
            'properties': {
                'case_id': {'type': 'string', 'enum': case_ids},
                'decision': {'type': 'string', 'enum': ['RESOLVED', 'MULTI_TARGET', 'UNKNOWN']},
                'candidate_ids': {'type': 'array', 'items': {'type': 'string'}, 'uniqueItems': True},
                'evidence_ids': {'type': 'array', 'items': {'type': 'string'}, 'uniqueItems': True},
                'reason': {'type': 'string', 'minLength': 1, 'maxLength': 300}
            }}}}
    }
    if not args.execute:
        print(json.dumps({'preflight': 'pass', 'network_calls': 0, 'cases': len(cases), 'model': MODEL}, ensure_ascii=False))
        return
    out = ADR / 'artifacts/run-001'
    out.mkdir(exist_ok=False)
    client = Client(ROOT, out / 'calls', model=MODEL, max_calls=1, max_output_tokens=4096,
                    schema_in_prompt=True, max_repairs=0)
    system = ('한국어 규정의 명시 참조를 해소한다. 제공된 evidence와 candidate만 사용한다. '
              '범위는 양 끝을 포함하고, 근거가 유일할 때만 RESOLVED 또는 MULTI_TARGET을 선택한다. '
              '문서 버전 충돌, 구조에 없는 항, 후보를 고를 근거가 부족한 경우 UNKNOWN과 빈 candidate_ids를 낸다. '
              'candidate_ids와 evidence_ids는 제공된 ID의 부분집합이어야 한다. 정답은 제공되지 않는다.')
    start = time.monotonic()
    error = None
    try:
        result = client.generate(system, {'cases': product_cases}, schema, phase='reference-review')
    except Exception as exc:
        result = {'resolutions': []}
        error = {'type': type(exc).__name__, 'message': str(exc)}
    rows = {r['case_id']: r for r in result.get('resolutions', []) if isinstance(r, dict) and r.get('case_id') in case_ids}
    duplicate_or_missing = len(rows) != len(cases) or len(result.get('resolutions', [])) != len(cases)
    outside = []
    scored = []
    for case in cases:
        pred = rows.get(case['case_id'], {'decision': 'MISSING', 'candidate_ids': [], 'evidence_ids': [], 'reason': 'missing'})
        invalid = sorted(set(pred.get('candidate_ids', [])) - all_candidate_ids[case['case_id']])
        if invalid:
            outside.append({'case_id': case['case_id'], 'ids': invalid})
        expected = case['gold']
        exact = pred.get('decision') == expected['decision'] and sorted(pred.get('candidate_ids', [])) == sorted(expected['candidate_ids']) and not invalid
        baseline_exact = expected['decision'] == 'UNKNOWN' and expected['candidate_ids'] == []
        scored.append({'case_id': case['case_id'], 'baseline': {'decision': 'UNKNOWN', 'candidate_ids': []},
                       'baseline_exact': baseline_exact, 'prediction': pred, 'gold': expected, 'qwen_exact': exact})
    usage = client.usage
    total_cost = sum(float(x.get('cost_usd') or 0) for x in usage)
    seconds = round(time.monotonic() - start, 3)
    exact_count = sum(x['qwen_exact'] for x in scored)
    unknown_false = sum(1 for x in scored if x['gold']['decision'] == 'UNKNOWN' and x['prediction'].get('decision') != 'UNKNOWN')
    criteria = {
        'exact_cases': exact_count, 'exact_cases_pass': exact_count >= design['criteria']['exact_cases_min'],
        'unknown_false_resolutions': unknown_false, 'unknown_false_resolutions_pass': unknown_false <= design['criteria']['unknown_false_resolutions_max'],
        'outside_candidate_ids': len(outside), 'outside_candidate_ids_pass': not outside,
        'cost_usd': total_cost, 'cost_pass': total_cost <= design['criteria']['cost_usd_max'],
        'latency_seconds': seconds, 'latency_pass': seconds <= design['criteria']['latency_seconds_max'],
        'complete_output_pass': not duplicate_or_missing and error is None
    }
    output = {'schema_version': 'qwen-reference-probe-result-v1', 'model': MODEL, 'error': error,
              'system': system, 'product_input': {'cases': product_cases}, 'schema': schema,
              'raw_structured_output': result, 'scores': scored, 'outside_candidate_ids': outside,
              'baseline_exact': sum(x['baseline_exact'] for x in scored), 'qwen_exact': exact_count,
              'usage': usage, 'seconds': seconds, 'criteria': criteria,
              'success': all(v for k, v in criteria.items() if k.endswith('_pass')),
              'main_wiring': 'unchanged'}
    write(out / 'result.json', output)
    print(json.dumps({'error': error, 'baseline_exact': output['baseline_exact'], 'qwen_exact': exact_count,
                      'unknown_false_resolutions': unknown_false, 'cost_usd': total_cost, 'seconds': seconds,
                      'success': output['success']}, ensure_ascii=False))

if __name__ == '__main__':
    main()
