"""Frozen two-call synthetic reference benchmark. Never changes serving state."""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import jsonschema

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0553-qwen38-27b-reference-twelve'
PARENT = ROOT / '04_EXPERIMENTS/ADR/ADR-0483-qwen-ambiguous-reference-probe'
ARMS = ('qwen38-original', 'qwen38-normalized')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def frozen():
    design = read(ADR / 'artifacts/frozen-design.json')
    for path, expected in design['file_hashes'].items():
        if sha(ROOT / path) != expected:
            raise RuntimeError('Frozen input drift: ' + path)
    for candidate in design['candidates']:
        manifest = read(ROOT / candidate['manifest_path'])
        revision = next(r for r in manifest['revisions'] if r['revision_id'] == candidate['revision_id'])
        if revision['revision_sha256'] != candidate['revision_sha256']:
            raise RuntimeError('Frozen revision drift')
        for row in revision['files']:
            if sha(ROOT / row['frozen_path']) != row['snapshot_sha256']:
                raise RuntimeError('Frozen candidate drift: ' + row['target_path'])
    return design


def protocol_for(snapshot):
    sys.path.insert(0, str(snapshot / '02_BACKEND'))
    # The namespace package and its only relative dependency live in this snapshot.
    for name in list(sys.modules):
        if name == 'semantic_runtime' or name.startswith('semantic_runtime.'):
            del sys.modules[name]
    from semantic_runtime import reference_resolution_protocol
    assert Path(reference_resolution_protocol.__file__).resolve().is_relative_to(snapshot)
    return reference_resolution_protocol


def run(execute):
    design = frozen()
    cases = read(ADR / 'fixture.json')['cases']
    gold_free = [{k: v for k, v in row.items() if k != 'gold'} for row in cases]
    old = read(PARENT / 'artifacts/run-001/result.json')
    assert old['product_input'] == {'cases': gold_free}
    if not execute:
        print(json.dumps({'preflight': 'pass', 'cases': len(cases), 'physical_calls': 0,
                          'arms': ARMS, 'model': 'qwen/qwen3.8-27b', 'provider': 'parasail/fp8'}))
        return
    out = ADR / 'artifacts/run-001'
    out.mkdir(exist_ok=False)
    results = {}
    for arm in ARMS:
        candidate = next(c for c in design['candidates'] if c['arm_id'] == arm)
        snapshot = ROOT / candidate['snapshot_path']
        client_module = module('adr0553_client_' + arm.replace('-', '_'),
                               snapshot / '02_BACKEND/lawrag/research/experiment_client.py')
        client = client_module.ExperimentClient(
            ROOT, out / arm / 'calls', scoped_policy_path=ADR / 'artifacts/scoped-model-policy.json',
            scoped_policy_sha256=design['scoped_policy_sha256'], max_calls=1,
            max_output_tokens=4096, schema_in_prompt=True, max_repairs=0)
        started = time.monotonic()
        raw = None
        predictions = {}
        error = None
        try:
            if arm == 'qwen38-original':
                original_request = next((PARENT / 'artifacts/run-001/calls').glob('call-*/request.json'))
                payload = copy.deepcopy(read(original_request))
                payload['model'] = client.model
                payload['provider'] = client.proxy['provider_routing']
                payload['reasoning'] = client.proxy['reasoning']
                envelope = client.chat_completions(payload, phase='reference-original', timeout_seconds=120)
                raw = json.loads(envelope['body_json']['choices'][0]['message']['content'])
                jsonschema.validate(raw, old['schema'])
                rows = raw['resolutions']
                for row in rows:
                    predictions[row['case_id']] = {'decision': row['decision'],
                        'candidate_ids': row['candidate_ids'], 'evidence_ids': row['evidence_ids'],
                        'reason': row['reason']}
            else:
                protocol = protocol_for(snapshot)
                raw = client.generate(design['normalized_system'], {'cases': gold_free},
                                      protocol.schema('ReferenceResolutionOutput'), phase='reference-normalized')
                normalized = protocol.validate_batch(raw, gold_free)
                write(out / arm / 'server-normalized.json', normalized)
                rows = normalized
                for row in rows:
                    predictions[row['case_id']] = {'decision': row['resolution_state'],
                        'candidate_ids': row['selected_candidate_ids'], 'evidence_ids': row['evidence_ids'],
                        'reason': row['explanation'], 'abstain_reason': row['abstain_reason']}
            if len(rows) != 12 or len(predictions) != 12 or set(predictions) != {c['case_id'] for c in cases}:
                raise ValueError('output must cover all twelve cases exactly once')
        except Exception as exc:
            error = {'type': type(exc).__name__, 'message': str(exc)}
        elapsed = round(time.monotonic() - started, 3)
        cost = sum(float(u.get('cost_usd') or 0) for u in client.usage)
        scores = []
        outside_candidates = outside_evidence = 0
        for case in cases:
            pred = predictions.get(case['case_id'])
            gold = case['gold']
            outside = sorted(set((pred or {}).get('candidate_ids', [])) - {c['id'] for c in case['candidates']})
            evidence_out = sorted(set((pred or {}).get('evidence_ids', [])) - {e['id'] for e in case['evidence']})
            outside_candidates += len(outside)
            outside_evidence += len(evidence_out)
            target_exact = bool(pred) and not outside and set(pred['candidate_ids']) == set(gold['candidate_ids'])
            exact = target_exact and pred['decision'] == gold['decision']
            scores.append({'case_id': case['case_id'], 'gold': gold, 'prediction': pred,
                           'exact': bool(exact), 'target_set_exact': bool(target_exact),
                           'outside_candidate_ids': outside, 'outside_evidence_ids': evidence_out,
                           'historical_exact': next(r['qwen_exact'] for r in old['scores'] if r['case_id'] == case['case_id'])})
        count = sum(r['exact'] for r in scores)
        unknown_false = sum(r['gold']['decision'] == 'UNKNOWN' and bool(r['prediction'])
                            and bool(r['prediction']['candidate_ids']) for r in scores)
        criteria = {'exact_cases_pass': count >= 10, 'unknown_false_pass': unknown_false == 0,
                    'outside_ids_pass': outside_candidates == outside_evidence == 0,
                    'complete_output_pass': error is None and len(predictions) == 12,
                    'cost_pass': bool(client.usage) and cost <= 0.10,
                    'latency_pass': elapsed <= 120, 'physical_calls_pass': client.calls == 1}
        result = {'model': client.model, 'arm': arm, 'error': error,
                  'raw_structured_output': raw, 'predictions': predictions, 'scores': scores,
                  'exact': count, 'total': 12, 'accuracy': count / 12,
                  'target_set_exact': sum(r['target_set_exact'] for r in scores),
                  'unknown_false_resolutions': unknown_false, 'unknown_cases': 4,
                  'outside_candidate_ids': outside_candidates, 'outside_evidence_ids': outside_evidence,
                  'physical_calls': client.calls, 'cost_usd': cost, 'seconds': elapsed,
                  'usage': client.usage, 'criteria': criteria, 'success': all(criteria.values())}
        write(out / arm / 'result.json', result)
        results[arm] = result
        print(json.dumps({k: result[k] for k in ('arm', 'error', 'exact', 'total',
                         'unknown_false_resolutions', 'cost_usd', 'seconds', 'success')}, ensure_ascii=False), flush=True)
    write(out / 'result.json', {'schema_version': 'reference-twelve-model-comparison-v1',
        'historical_baseline': {'model': old['model'], 'exact': old['qwen_exact'], 'total': 12,
                                'usage': old['usage'], 'seconds': old['seconds'], 'scores': old['scores']},
        'by_arm': results, 'main_wiring': 'unchanged'})
    print('both frozen arms finished', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    run(args.execute)
