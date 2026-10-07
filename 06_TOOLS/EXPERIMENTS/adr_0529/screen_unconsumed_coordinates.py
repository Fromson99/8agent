"""Read-only lexical screen of candidate reference coordinates, not legal adjudication."""
import collections
import hashlib
import json
import pathlib
import re
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0529-complete-qualifier-ingestion'
GEN = ROOT / '01_DATA/TERM_RELEASES/adr0529-frame-anchors-v1/generation'
SCOPE = ROOT / '04_EXPERIMENTS/ADR/ADR-0523-gemma-scoped-exploration-probe/product-cases.json'
scope = set(json.loads(SCOPE.read_text())['public_scope_document_ids'])
letters = json.loads((ADR / 'artifacts/frozen-design.json').read_text())['observed_mok_sequence']
patterns = {
    'following_mok': re.compile(r'\s*[' + letters + r']\s*목'),
    'following_branch': re.compile(r'\s*의\s*\d+'),
    'following_qualifier': re.compile(r'\s*(?:단서|본문|전단|후단)'),
    'following_head_only': re.compile(r'\s*각\s*(?:호|목)\s*외의\s*부분'),
}
counts = collections.Counter()
samples = collections.defaultdict(list)
with sqlite3.connect(f'file:{GEN}/navigation/navigation.sqlite?mode=ro', uri=True) as db:
    db.execute('PRAGMA query_only=ON')
    for (raw,) in db.execute('SELECT json FROM reference'):
        r = json.loads(raw)
        counts['all_reference_rows'] += 1
        if r['document_id'] not in scope or r['origins'] == ['official_delegation_lawgokr']:
            continue
        counts['public_literal_rows'] += 1
        tail = r['source_text'][r['mention_end']:]
        for name, pattern in patterns.items():
            if not pattern.match(tail):
                continue
            counts[name] += 1
            if r.get('targets') and r.get('coordinate_status') == 'EXACT':
                counts[name + '_exact_target'] += 1
            if len(samples[name]) < 25:
                samples[name].append({
                    'id': r['id'], 'source_id': r['source_id'], 'block_id': r['block_id'],
                    'mention': r['mention_text'], 'tail': tail[:50],
                    'coordinate_status': r.get('coordinate_status'),
                    'targets': [{'source_id': t['source_id'], 'unit_path': t.get('unit_path')}
                                for t in r.get('targets', [])],
                })
result = {
    'schema_version': 'lexical-coordinate-screen-v1',
    'generation': str(GEN.relative_to(ROOT)),
    'generation_manifest_sha256': hashlib.sha256((GEN / 'manifest.json').read_bytes()).hexdigest(),
    'scope_sha256': hashlib.sha256(SCOPE.read_bytes()).hexdigest(),
    'counts': dict(counts), 'samples': dict(samples),
    'limitations': 'Screened lexical suffix patterns only. Counts overlap and are not individually adjudicated errors or recall measurements.',
}
(ADR / 'artifacts/coordinate-screen.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'counts': result['counts'], 'limitations': result['limitations']}, ensure_ascii=False))
