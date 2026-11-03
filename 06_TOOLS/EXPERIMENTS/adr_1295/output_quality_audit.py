"""Inspect original output, including numbered gap filler missed by exact-repeat counts."""
from common import *
import re

P = ART / 'live/review-whatif'
rows = []
for folder in sorted((P / 'raw').glob('call-*')):
    response_path = folder / 'response.json.gz'
    if not response_path.exists():
        continue
    started = read(folder / 'started.json')
    response = read(response_path)
    try:
        value = json.loads(response['choices'][0]['message']['content'])
    except (ValueError, KeyError, IndexError, TypeError):
        continue
    number = started['number']
    canonical_path = P / 'canonical' / f'{number:03d}-output.json.gz'
    canonical = read(canonical_path) if canonical_path.exists() else {}
    gaps = value.get('gaps', [])
    findings = []
    for i, gap in enumerate(gaps):
        reason = gap.get('reason', '')
        refs = [int(n) for n in re.findall(r'gap\s*(\d+)\s*참조', reason)]
        saved = canonical.get('gaps', [])
        findings.append({'gap_index': i + 1, 'reason_chars': len(reason),
            'reason_sha256': hashlib.sha256(reason.encode()).hexdigest(),
            'reference_occurrences': len(refs), 'referenced_numbers': refs,
            'references_outside_response_gaps': sorted(set(refs) - set(range(1, len(gaps) + 1))),
            'raw_equals_canonical': i < len(saved) and reason == saved[i].get('reason'),
            'reason': reason})
    rows.append({'number': number, 'turn': started['turn'], 'stage': started['stage'],
        'raw_response': str(response_path.relative_to(ROOT)), 'raw_sha256': sha(response_path),
        'gap_count': len(gaps), 'gaps': findings})

put(ART / 'output-quality-audit.json', {
    'method': 'Inspect untouched provider message JSON; compare canonical gap reasons exactly. No model calls or output modification.',
    'rows': rows,
    'limits': ['Reference detection is diagnostic, not a legal-quality judge.',
        'The existing exact-parenthesis repetition counter does not detect changing numbers; this additional inspection preserves that earlier audit unchanged.',
        'An exact 600-character output does not establish a provider or schema root cause. The transmitted reason schema allows 1 through 600 characters, not a required length of 600.']})
print(json.dumps([{'number': r['number'], 'turn': r['turn'],
    'gap_chars': [g['reason_chars'] for g in r['gaps']],
    'reference_counts': [g['reference_occurrences'] for g in r['gaps']],
    'raw_equals_canonical': all(g['raw_equals_canonical'] for g in r['gaps'])} for r in rows], ensure_ascii=False))
