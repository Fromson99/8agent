"""Offline literal checks of current field citations, separate from prior alternatives."""
from pathlib import Path
import hashlib
import json
import sqlite3

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0948-research-decision-live-repeat'
for p in sorted((A / 'artifacts/run-001').glob('*/*/audit.json')):
    audit = json.loads(p.read_text())
    parent = next(j for j in audit['journals'] if j['side'] == 'parent')
    checks = []
    fields = []
    with sqlite3.connect('file:' + str(R / parent['path']) + '?mode=ro', uri=True) as db:
        for row in audit['field_rows']:
            for side in ('external', 'internal'):
                value = row.get(side, {})
                citations = value.get('citations', [])
                fields.append({
                    'field': row['field'], 'side': side, 'status': value.get('status'),
                    'primary_citation_count': len(citations),
                    'alternative_citation_count': sum(len(v.get('citations', [])) for v in value.get('alternatives', [])),
                    'primary_text': value.get('text'), 'missing': value.get('missing'),
                })
                for citation in citations:
                    evidence = citation['evidence']
                    spans = [r[0] for r in db.execute('SELECT text FROM evidence_span WHERE evidence_id=? ORDER BY ordinal', (evidence,))]
                    quote = citation['quote']
                    checks.append({
                        'field': row['field'], 'side': side, 'evidence_id': evidence,
                        'quote_sha256': hashlib.sha256(quote.encode()).hexdigest(),
                        'quote_chars': len(quote),
                        'literal_match': bool(quote and spans) and quote in '\n'.join(spans),
                    })
    result = {
        'fields': fields, 'primary_quote_checks': checks,
        'literal_mismatches': sum(not c['literal_match'] for c in checks),
        'confirmed_external_without_primary_quote': [f['field'] for f in fields if f['side'] == 'external' and f['status'] == 'CONFIRMED' and not f['primary_citation_count']],
        'limitation': 'Literal matching does not establish claim support or legal applicability. Prior alternatives remain in saved output and are counted separately from the current primary field.',
    }
    (p.parent / 'citation-audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('/'.join(p.parts[-3:-1]), 'primary_quotes', len(checks), 'literal_mismatches', result['literal_mismatches'], 'confirmed_without_primary_quote', result['confirmed_external_without_primary_quote'])
