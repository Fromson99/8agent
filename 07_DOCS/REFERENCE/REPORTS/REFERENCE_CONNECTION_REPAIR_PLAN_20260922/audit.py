"""Read-only lexical/coordinate audit; no compiler run, model call, or DB mutation.

Run with the repository Python from the repository root. Findings are screening
counts, not independently adjudicated legal-edge precision measurements.
"""
import collections
import hashlib
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
GEN = ROOT / '01_DATA/TERM_RELEASES/adr0523-gemma-bound-fulltext-v1/generation'
CODE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0522/guarded/revisions/rev-002/snapshot/02_BACKEND'
SCOPE = ROOT / '04_EXPERIMENTS/ADR/ADR-0523-gemma-scoped-exploration-probe/product-cases.json'
scope = set(json.loads(SCOPE.read_text())['public_scope_document_ids'])
db = sqlite3.connect(f'file:{GEN}/navigation/navigation.sqlite?mode=ro', uri=True)
db.execute('PRAGMA query_only=ON')
letters = '가나다라마바사아자차카타파하'
groups = collections.defaultdict(list)
totals = collections.Counter()
by_block = collections.defaultdict(list)
examples = {}
example_ids = {
    'ref:248869a54d123fd8d8889703': 'known_mok_truncation',
    'ref:6e208653c2c2a0ddd4bfa07c': 'additional_mok_truncation',
    'ref:9a195362dba80bea8d1f3208': 'range_parent_mismatch',
    'ref:6a032357c1cf57e93c4c1212': 'same_paragraph_mismatch',
    'ref:0815dcc19d7c988950536721': 'annex_branch_and_self_heading',
    'ref:945d0f9b92fa1620d1b7d024': 'enumerated_mok_omission',
}


def summarize(r):
    return {k: r.get(k) for k in ('id', 'source_id', 'document_id', 'block_id',
        'source_text', 'mention_text', 'mention_start', 'mention_end',
        'source_unit_path', 'target_unit_path', 'targets', 'resolution',
        'coordinate_status', 'reason')}


for (raw,) in db.execute('SELECT json FROM reference'):
    r = json.loads(raw)
    totals['all_reference_rows'] += 1
    if r['document_id'] not in scope:
        continue
    totals['public_reference_rows'] += 1
    by_block[(r['source_id'], r['block_id'])].append(r)
    text = r['source_text']
    start, end = r.get('mention_start', 0), r.get('mention_end', 0)
    tail = text[end:]
    hits = []
    if re.match(r'\s*[' + letters + r']\s*목', tail):
        hits.append('unconsumed_mok_suffix')
    if re.match(r'\s*의\s*\d+', tail):
        hits.append('unconsumed_branch_suffix')
    if re.match(r'\s*(단서|본문|전단|후단)', tail):
        hits.append('following_qualifier_screen')
    # Only a range actually starting at an item, immediately preceded by an
    # explicit paragraph. Do not count every reference in a range-bearing block.
    parent = re.search(r'제\s*(\d+)\s*항\s*$', text[:start])
    if parent and re.match(r'제\s*\d+\s*호\s*(?:부터|내지|[~～∼])', r['mention_text']):
        hits.append('range_omits_explicit_parent')
        n = int(parent[1])
        expected = chr(0x2460 + n - 1) if 1 <= n <= 20 else None
        if expected and r.get('targets') and any(
            t.get('unit_path') and t['unit_path'][0] != expected for t in r['targets']
        ):
            hits.append('range_target_parent_mismatch_screen')
    if re.search(r'(?:같은|동)\s*항\s*$', text[:start]) and re.match(r'제\s*\d+\s*호', r['mention_text']):
        hits.append('same_paragraph_item_screen')
    for kind in hits:
        groups[kind].append(summarize(r))
    if r['id'] in example_ids:
        examples[example_ids[r['id']]] = {'reference': r}

# Bare letter mentions that have no covering DB mention span. This is a lexical
# coverage screen only; it does not automatically supply an owner or target.
uncovered = []
for (sid, bid), refs in by_block.items():
    text = refs[0]['source_text']
    for m in re.finditer(r'(?<![가-힣])[' + letters + r']\s*목(?=\s|[에을를의과와ㆍ·,])', text):
        if not any(r.get('mention_start', 0) <= m.start() and r.get('mention_end', 0) >= m.end() for r in refs):
            uncovered.append({'source_id': sid, 'block_id': bid, 'span': [m.start(), m.end()],
                              'mention': m[0], 'source_text': text})


def source(sid):
    return json.loads(db.execute('SELECT json FROM source WHERE id=?', (sid,)).fetchone()[0])


for example in examples.values():
    r = example['reference']
    s = source(r['source_id'])
    example['source'] = s
    example['source_structure'] = [dict(zip(('unit_id', 'parent_id', 'surface', 'block_ids'), row))
        for row in db.execute('SELECT unit_id,parent_id,surface,block_ids FROM source_unit_map WHERE source_id=?', (s['id'],))]
    example['targets'] = []
    for target in r['targets']:
        dest = source(target['source_id'])
        example['targets'].append({'coordinate': target, 'source_id': dest['id'],
            'document_name': dest['document_name'], 'heading': dest['heading'],
            'blocks': [b for b in dest['blocks'] if not target['block_ids'] or b['block_id'] in target['block_ids']]})
    example['other_references_in_block'] = [summarize(x) for x in by_block[(r['source_id'], r['block_id'])]]

summary = {}
for kind, rows in groups.items():
    exact = [r for r in rows if r['coordinate_status'] == 'EXACT' and r['targets']]
    summary[kind] = {'rows': len(rows), 'exact_with_targets': len(exact),
        'source_count': len({r['source_id'] for r in rows}),
        'document_count': len({r['document_id'] for r in rows}),
        'resolution_counts': dict(collections.Counter(r['resolution'] for r in rows))}

manifest = json.loads((GEN / 'navigation/manifest.json').read_text())
compiler_hash = hashlib.sha256((CODE / 'semantic_runtime/term_references.py').read_bytes()).hexdigest()
assert compiler_hash == manifest['reference_rebuild']['reference_compiler_sha256']
result = {'audit_kind': 'read_only_coordinate_screen_and_source_inspection',
    'generation': str(GEN.relative_to(ROOT)), 'navigation_sha256_from_manifest': manifest['index_sha256'],
    'navigation_hash_recomputed_this_audit': False,
    'compiler_sha256': compiler_hash,
    'compiler_matches_generation_rebuild_receipt': True,
    'navigation_manifest_sha256': hashlib.sha256((GEN / 'navigation/manifest.json').read_bytes()).hexdigest(),
    'scope_sha256': hashlib.sha256(SCOPE.read_bytes()).hexdigest(),
    'scope_document_count': len(scope), 'counts': dict(totals), 'screens': summary,
    'uncovered_bare_mok_in_reference_bearing_blocks': len(uncovered),
    'limitations': ['Screen classes overlap; do not add counts.',
        'No blanket legal correctness judgment from UNKNOWN roles or qualifiers.',
        'Bare mok screen covers blocks already containing at least one reference only.',
        'No model call, compiler execution, DB mutation, or new retrieval run.'],
    'examples': examples, 'screen_rows': groups, 'uncovered_bare_mok': uncovered}
(OUT / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
(OUT / 'summary.json').write_text(json.dumps({k: v for k, v in result.items()
    if k not in ('examples', 'screen_rows', 'uncovered_bare_mok')}, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: result[k] for k in ('counts', 'screens', 'uncovered_bare_mok_in_reference_bearing_blocks')}, ensure_ascii=False, indent=2))
db.close()
