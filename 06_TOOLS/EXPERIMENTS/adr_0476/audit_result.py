"""Post-run audit: joins decisive coordinates only after the product result is sealed."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0476-source-first-qwen-autonomy'
OUT = ADR / 'artifacts/run-001'


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    result = read(OUT / 'result.json')
    trace = read(OUT / 'trace.json') if (OUT / 'trace.json').exists() else {'cards': [], 'evidence': [], 'aliases': {}, 'selected_evidence_ids': []}
    spec = importlib.util.spec_from_file_location('ledger', ROOT / '06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py')
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    fixture = read(ADR / 'fixture.json')
    scope = fixture['public_scope_document_ids']
    with sqlite3.connect(f'file:{ROOT / fixture["generation"] / "navigation/navigation.sqlite"}?mode=ro', uri=True) as con:
        coord = {sid: {'doc_id': did, 'node': int(json.loads(raw)['unit_id'])}
                 for sid, did, raw in con.execute('SELECT id,document_id,json FROM source')
                 if did in scope and str(json.loads(raw).get('unit_id')).isdigit()}
    # This reference file is never opened by the product runner.
    gold_file = ROOT / '04_EXPERIMENTS/ADR/ADR-0474-double-harness-live-quality-probe/artifacts/frozen-inputs.json'
    case = next(c for c in read(gold_file)['cases'] if c['case_id'] == 'cm-003')
    gold_sids = set(case['decisive_source_ids'])
    gold = h.ordered(coord[sid] for sid in gold_sids)
    tables = read(OUT / 'journal-tables.json') if (OUT / 'journal-tables.json').exists() else {}
    ev = {e['evidence_id']: e['source_id'] for e in trace['evidence']}
    aliases = trace['aliases']
    successful = {a['view_id'] for a in tables.get('model_attempt', []) if a['status'] == 'SUCCEEDED'}
    views = [json.loads(v['body_json']) for v in tables.get('model_view', []) if v['view_id'] in successful]
    delivered = {ev[aliases[e['evidence']]] for v in views for e in v.get('evidence', [])}
    sets = [('discovered', {c['source_id'] for c in trace['cards']}), ('read', set(ev.values())),
            ('presented', delivered), ('selected', {ev[i] for i in trace['selected_evidence_ids']}),
            ('answer', {sid for c in result.get('result', {}).get('answer', {}).get('claims', []) for sid in c['source_ids']})]
    plan = read(ADR / 'artifacts/frozen-design.json')['stage_plan']
    arms = []
    summaries = {}
    for arm in ('baseline', 'qwen-autonomous'):
        rows, before = [], []
        for spec, (name, sids) in zip(plan[arm], sets):
            after = h.ordered(coord[sid] for sid in sids) if arm != 'baseline' else []
            if spec['kind'] != 'source' and any(i not in before for i in after):
                raise AssertionError('Non-monotonic evidence chain: ' + name)
            discarded = [i for i in before if i not in after]
            reasons = {h.key(i): 'not_' + name + '_by_autonomous_run' for i in discarded}
            row = h.stage(name, spec['kind'], spec['parent_stage_ids'], before,
                          after if spec['kind'] == 'source' else [], discarded, reasons, gold,
                          skip_reason='No baseline run; structural parent only, not zero recall' if arm == 'baseline' else None)
            rows.append(row)
            before = row['after']
        rec = {'schema_version': h.SCHEMA, 'computed_post_selection': True, 'gold_visible_to_product': False,
               'accounting_unit': h.UNIT, 'arm_id': arm, 'case_id': 'cm-003', 'gold_total': len(gold),
               'gold_identities': gold, 'stages': rows}
        arms.append({'arm_id': arm, 'declared_stage_ids': [r['stage_id'] for r in rows], 'cases': [rec],
                     'aggregate': {'presented_total': rows[-1]['after_count'], 'gold_after': rows[-1]['gold_after'], 'gold_total': len(gold)}})
        summaries[arm] = rows[-1]
    ledger = {'schema_version': h.SCHEMA, 'adr_id': 'ADR-0476', 'experiment_id': 'ADR-0476-experiment-v1',
              'accounting_unit': h.UNIT, 'computed_post_selection': True, 'gold_visible_to_product': False,
              'runs': [{'run_id': 'run-001', 'arms': arms}],
              'audit': {'gold_source_sha256': sha(gold_file), 'stage_plan_frozen_before_run': True,
                        'baseline_not_executed': True, 'quality_judged': False}}
    ledger['artifact_sha256'] = h._canonical_value_sha256(ledger)
    ledger_path = ADR / 'artifacts/retrieval-stage-ledger.json'
    write(ledger_path, ledger)
    decisions = [json.loads(e['payload_json'])['decision'] for e in tables.get('event', []) if e['kind'] == 'SOURCE_FIRST_DECISION']
    actions = [a for d in decisions for a in d['actions']]
    first_view = views[0] if views else {}
    initial_sids = {ev[aliases[e['evidence']]] for e in first_view.get('evidence', [])}
    calls = result['physical_calls']
    attempts = tables.get('model_attempt', [])
    metrics = {'error': result['error'], 'physical_calls': calls, 'journal_attempts': len(attempts),
               'call_accounting_matches': calls == len(attempts),
               'tool_actions_requested': actions, 'initial_preread_source_count': len(initial_sids),
               'initial_preread_decisive_count': len(initial_sids & gold_sids),
               'stages': {name: {'sources': len(sids), 'decisive': len(sids & gold_sids)} for name, sids in sets},
               'claim_count': len(result.get('result', {}).get('answer', {}).get('claims', [])),
               'gate': result.get('control', {}).get('gate'),
               'independent_accuracy': 'not_evaluated',
               'controller_completed': result.get('control', {}).get('decision') == 'FINAL' and result['error'] is None,
               'input_tokens': sum(u.get('input_tokens') or 0 for u in result['usage']),
               'output_tokens': sum(u.get('output_tokens') or 0 for u in result['usage']),
               'provider_reported_cost_usd': sum(u.get('cost_usd') or 0 for u in result['usage']),
               'seconds': result['seconds'], 'source_manifest_unchanged': result['source_manifest_unchanged']}
    write(ADR / 'artifacts/metrics.json', metrics)
    manifest = read(ADR / '실험/manifest.json')
    ra = manifest['retrieval_accounting']
    ra['corpus_total'] = len(h.ordered(coord.values()))
    for metric in ('before_filter', 'after_filter', 'presented_total', 'presented_mean', 'presented_p50', 'presented_p95', 'golden_recall', 'selectivity'):
        ra[metric] = {}
        for arm, row in summaries.items():
            n = row['after_count']
            ra[metric][arm] = row['golden_recall'] if metric == 'golden_recall' else n / ra['corpus_total'] if metric == 'selectivity' else n
    ra['before_filter']['qwen-autonomous'] = len(sets[0][1])
    ra['stage_ledger'].update(summary_run_id='run-001', artifact_path=str(ledger_path.relative_to(ROOT)), sha256=sha(ledger_path))
    manifest['runs'][0].update(status='complete', artifact_path=str((OUT / 'result.json').relative_to(ROOT)), sha256=sha(OUT / 'result.json'))
    manifest['results'].update(status='complete', by_arm={'baseline': {'executed': False}, 'qwen-autonomous': metrics},
                               usage={'physical_calls': calls, 'input_tokens': metrics['input_tokens'], 'output_tokens': metrics['output_tokens']},
                               latency={'single_case_seconds': result['seconds']}, comparisons=[], judge_disagreements=None,
                               error_taxonomy=[] if result['error'] is None else [result['error']['type']])
    write(ADR / '실험/manifest.json', manifest)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
