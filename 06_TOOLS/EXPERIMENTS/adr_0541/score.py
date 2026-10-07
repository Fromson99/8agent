"""Offline gold join for ADR-0541, never imported by the model runner."""
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'00_SYSTEM/WORKSPACE.json').is_file())
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-0541-reverse-hint-larger-sample'


def load(path):
    return json.loads(path.read_text())


def write(path, value):
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def summary(values):
    return {'total': sum(values), 'mean': statistics.mean(values),
            'p50': statistics.median(values),
            'p95': sorted(values)[min(len(values)-1, round((len(values)-1)*.95))]}


def main():
    design = load(ADR/'artifacts/frozen-design.json')
    result = load(ADR/'artifacts/run-001/result.json')
    assert list(result['cases']) == design['case_order']
    gold_cases = load(ROOT/design['offline_targets_path'])
    gold = {case['case_id']: set(case['decisive_source_ids']) for case in gold_cases['cases']}
    assert set(gold) == set(design['case_order'])
    product = load(ROOT/design['product_cases'])
    scope = set(product['public_scope_document_ids'])
    nav = ROOT/product['generation']/'navigation/navigation.sqlite'
    with sqlite3.connect(f'file:{nav}?mode=ro', uri=True) as db:
        source = {sid: (did, json.loads(raw).get('unit_id'))
                  for sid,did,raw in db.execute('SELECT id,document_id,json FROM source') if did in scope}
    assert all(sid in source for ids in gold.values() for sid in ids)
    corpus_ids = sorted(source)
    corpus_sha = hashlib.sha256(json.dumps(corpus_ids,separators=(',',':')).encode()).hexdigest()
    per_case = []
    aggregate = {arm: {'protected_gold': 0,'top64_gold': 0,'gold_total': 0,
                       'protected_counts': [], 'tokens': [], 'seconds': [], 'cost_usd': 0.0}
                 for arm in ('baseline','hint-plan')}
    for cid in design['case_order']:
        target = gold[cid]
        arm_rows = {}
        for arm in ('baseline','hint-plan'):
            item = result['cases'][cid]['arms'][arm]
            protected = set(item['protected_union']) & source.keys()
            broad = set(item['top64_union']) & source.keys()
            usage = item['usage'][0]
            row = {'protected_gold_ids': sorted(protected & target),
                   'top64_gold_ids': sorted(broad & target),
                   'protected_source_ids': sorted(protected),
                   'top64_source_ids': sorted(broad),
                   'lost_after_top64_ids': sorted((broad & target)-protected),
                   'gold_total': len(target), 'input_tokens': usage['input_tokens'],
                   'call_seconds': usage['seconds'], 'cost_usd': usage['cost_usd']}
            arm_rows[arm] = row
            a = aggregate[arm]
            a['protected_gold'] += len(row['protected_gold_ids'])
            a['top64_gold'] += len(row['top64_gold_ids'])
            a['gold_total'] += len(target)
            a['protected_counts'].append(len(protected))
            a['tokens'].append(usage['input_tokens'])
            a['seconds'].append(usage['seconds'])
            a['cost_usd'] += usage['cost_usd']
        base = set(arm_rows['baseline']['protected_gold_ids'])
        hint = set(arm_rows['hint-plan']['protected_gold_ids'])
        per_case.append({'case_id': cid,'gold_source_ids': sorted(target), 'arms': arm_rows,
                         'gained': sorted(hint-base),'lost': sorted(base-hint)})
    scores = {}
    for arm,a in aggregate.items():
        scores[arm] = {'case_count': len(per_case),'gold_total': a['gold_total'],
                       'protected_gold': a['protected_gold'], 'top64_gold': a['top64_gold'],
                       'protected_recall': a['protected_gold']/a['gold_total'],
                       'presented': summary(a['protected_counts']),
                       'input_tokens': sum(a['tokens']),
                       'call_seconds': summary(a['seconds']),
                       'cost_usd': round(a['cost_usd'],8)}
    scores['paired'] = {'cases_with_gain': sum(bool(c['gained']) for c in per_case),
                        'cases_with_loss': sum(bool(c['lost']) for c in per_case),
                        'gained_gold': sum(len(c['gained']) for c in per_case),
                        'lost_gold': sum(len(c['lost']) for c in per_case)}
    scores['criteria_met'] = (scores['paired']['gained_gold'] > 0
                              and scores['paired']['lost_gold'] == 0
                              and scores['hint-plan']['input_tokens'] <= 1.5*scores['baseline']['input_tokens']
                              and scores['hint-plan']['call_seconds']['p50'] <= 2*scores['baseline']['call_seconds']['p50'])
    ledger = {'schema_version':'adr0541-offline-stage-ledger-v1',
              'corpus': {'source_count':len(corpus_ids),'sorted_source_ids_sha256':corpus_sha,
                         'generation':product['generation']},
              'stages':['public-corpus','query-top64','protected-top8'],
              'gold_joined_only_after_model_calls':True,'cases':per_case}
    write(ADR/'artifacts/run-001/scores.json',scores)
    write(ADR/'artifacts/run-001/retrieval-stage-ledger.json',ledger)
    print(json.dumps(scores,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
