"""Read existing archives only; never import product code or call a model."""
from pathlib import Path
from collections import Counter, defaultdict
import csv, hashlib, json, sqlite3, tarfile, tempfile

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0717-main50-cm51-sequential-profile'
O = A / 'artifacts/run-001'
V = A / 'artifacts/observations'
V.mkdir(exist_ok=True)


def category(phase):
    if phase.startswith('memory-assess'):
        return 'assessment'
    if 'repair' in phase:
        return 'investigation_repair'
    if 'request-entry' in phase:
        return 'entry'
    if 'reference' in phase:
        return 'reference'
    if 'navigation' in phase:
        return 'navigation'
    return 'other_investigation'


for p in sorted(O.glob('*/raw-archive.json')):
    dest = V / (p.parent.name + '.json')
    if dest.exists():
        continue
    d = json.loads((p.parent / 'diagnostic.json').read_text())
    calls = []
    events = []
    with tarfile.open(p.parent / 'raw.tar.gz') as t:
        for a, call in zip(d['physical_attempts'], d['calls'], strict=True):
            prefix = 'provider/' + call['call'] + '/'
            request = json.load(t.extractfile(prefix + 'request.json'))
            try:
                response = json.load(t.extractfile(prefix + 'response.json'))
            except KeyError:
                response = {}
            usage = response.get('usage') or {}
            view = json.loads(request['messages'][1]['content'])['view']
            try:
                decision = json.loads(response['choices'][0]['message']['content'])
            except (KeyError, IndexError, ValueError, TypeError):
                decision = None
            calls.append({
                **a, 'category': category(a['phase']),
                'actual_model': response.get('model'),
                'actual_provider': response.get('provider'),
                'input_tokens': usage.get('prompt_tokens'),
                'output_tokens': usage.get('completion_tokens'),
                'cached_tokens': (usage.get('prompt_tokens_details') or {}).get('cached_tokens'),
                'reasoning_tokens': (usage.get('completion_tokens_details') or {}).get('reasoning_tokens'),
                'cost_usd': usage.get('cost'),
                'requested_provider': request.get('provider'),
                'requested_model': request.get('model'),
                'requested_reasoning': request.get('reasoning'),
                'view_fields': list(view),
                'decision': decision,
                'raw_member': prefix,
            })
        journals = [x for x in t.getnames() if x.startswith('runtime/') and x.endswith('/journal.sqlite')]
        if journals:
            assert len(journals) == 1
            with tempfile.TemporaryDirectory(prefix='cm-observation-') as temp:
                dbpath = Path(temp) / 'journal.sqlite'
                dbpath.write_bytes(t.extractfile(journals[0]).read())
                db = sqlite3.connect(dbpath.as_uri() + '?mode=ro', uri=True)
                for seq, kind, payload in db.execute('select seq, kind, payload_json from event order by seq'):
                    if 'REJECTED' in kind or kind in {'LAW_DECISION_REJECTED', 'ASSESSMENT_GAP_REENTRY_PLANNED',
                                'LAW_FULLTEXT_DIRECTORY', 'LAW_SCOPED_FULLTEXT',
                                'LAW_STRUCTURE_DIRECTORY', 'CASE_JUDGMENT_REJECTED'}:
                        events.append({'seq': seq, 'kind': kind, 'payload': json.loads(payload)})
                db.close()
    value = {
        'case_id': d['case_id'], 'observation_only': True,
        'product_or_evaluator_calls_added': 0,
        'source_archive_sha256': json.loads(p.read_text())['sha256'],
        'calls': calls, 'search_and_rejection_events': events,
        'provider_verified': all(c['actual_provider'] == 'Parasail' for c in calls if c['status'] == 'completed'),
        'model_verified': all(c['actual_model'] == 'qwen/qwen3.8-27b' for c in calls if c['status'] == 'completed'),
    }
    dest.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

rows = [json.loads(p.read_text()) for p in sorted(V.glob('cm-[0-9][0-9][0-9].json'))]
groups = defaultdict(lambda: {'calls': 0, 'seconds': 0.0, 'input_tokens': 0, 'output_tokens': 0})
for row in rows:
    for call in row['calls']:
        group = groups[call['category']]
        group['calls'] += 1
        for key in ('seconds', 'input_tokens', 'output_tokens'):
            group[key] += call.get(key) or 0
dispositions = {}
for row in rows:
    assessments = [c for c in row['calls'] if c['category'] == 'assessment' and isinstance(c['decision'], dict)]
    dispositions[row['case_id']] = assessments[-1]['decision'].get('disposition') if assessments else None
summary = {'completed': len(rows), 'by_phase': dict(groups),
           'final_model_dispositions': dispositions,
           'disposition_counts': dict(Counter(str(v) for v in dispositions.values())),
           'disposition_caveat': 'Model self-reported status only; not independently verified correctness',
           'model_and_provider_verified': all(x['model_verified'] and x['provider_verified'] for x in rows)}
summary['output_unresolved_counts'] = {}
response_outcomes = Counter()
for row in rows:
    result = json.loads((O / row['case_id'] / 'result.json').read_text())
    output = result.get('output', {})
    answer = output.get('answer', {})
    summary['output_unresolved_counts'][row['case_id']] = len(answer.get('unresolved', [])) if isinstance(answer, dict) else None
    label = 'returned_' + str(dispositions[row['case_id']]) if result['http_status'] == 200 else 'failed_HTTP_' + str(result['http_status'])
    response_outcomes[label] += 1
summary['response_outcomes'] = dict(response_outcomes)
(V / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
with (V / 'physical-calls.csv').open('w', encoding='utf-8-sig', newline='') as f:
    fields = ['case_id', 'call', 'phase', 'category', 'status', 'seconds', 'input_tokens', 'output_tokens', 'actual_model', 'actual_provider']
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for row in rows:
        for call in row['calls']:
            w.writerow({k: row['case_id'] if k == 'case_id' else call.get(k) for k in fields})
print(json.dumps({k: v for k, v in summary.items() if k not in {'final_model_dispositions', 'output_unresolved_counts'}}, ensure_ascii=False))
