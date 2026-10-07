"""Read-only inspection of the pinned public DB; no rebuild or model evaluation."""
import collections
import hashlib
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
GEN = ROOT / '01_DATA/TERM_RELEASES/adr0523-gemma-bound-fulltext-v1/generation'
SCOPE = ROOT / '04_EXPERIMENTS/ADR/ADR-0523-gemma-scoped-exploration-probe/product-cases.json'
scope = set(json.loads(SCOPE.read_text())['public_scope_document_ids'])
db = sqlite3.connect(f'file:{GEN}/navigation/navigation.sqlite?mode=ro', uri=True)
db.execute('PRAGMA query_only=ON')
examples = {
    'ref:580564c20a70f5017e35cb66': 'inline_mok_child_lost',
    'ref:1c27f375846731a6f6b5d3b9': 'separate_blocks_mok_children_lost',
    'ref:1cbfdb260b08cd18652d91e6': 'ho_misclassified_as_hang',
    'ref:ba4238302c755e21d6e8b978': 'head_only_includes_children',
    'ref:b5dcff4071c825a9cb2c35e2': 'merged_letter_markers_and_role_gap',
    'ref:e92198ce916add3b4a5b53a5': 'reverse_endpoint_includes_mok_siblings',
}
counts = collections.Counter()
rows = collections.defaultdict(list)
evidence = {}


def source(sid):
    return json.loads(db.execute('SELECT json FROM source WHERE id=?', (sid,)).fetchone()[0])


def units(sid):
    return [dict(zip(('unit_id', 'parent_id', 'ordinal', 'surface', 'block_ids', 'family'), r))
            for r in db.execute('SELECT unit_id,parent_id,ordinal,surface,block_ids,family '
                                'FROM source_unit_map WHERE source_id=?', (sid,))]


for (raw,) in db.execute('SELECT json FROM reference'):
    r = json.loads(raw)
    counts['all_reference_rows'] += 1
    if r['document_id'] not in scope:
        continue
    counts['public_reference_rows'] += 1
    tail = r['source_text'][r['mention_end']:]
    hits = []
    if re.search(r'[가나다라마바사아자차카타파하]\s*목\s*$', r['mention_text']) and re.match(r'\s*\(?\d+\)', tail):
        hits.append('unconsumed_number_after_mok')
    if re.match(r'\s*각\s*(?:호|목)\s*외의\s*부분', tail):
        hits.append('unconsumed_head_only_qualifier')
    for kind in hits:
        rows[kind].append({k: r.get(k) for k in ('id', 'source_id', 'document_id', 'block_id',
                         'mention_text', 'mention_start', 'mention_end', 'coordinate_status')})
        counts[kind] += 1
        if r.get('coordinate_status') == 'EXACT' and r.get('targets'):
            counts[kind + '_exact'] += 1
    if r['id'] in examples:
        s = source(r['source_id'])
        targets = []
        for t in r['targets']:
            dest = source(t['source_id'])
            targets.append({'extent': t, 'source_id': dest['id'], 'document_name': dest['document_name'],
                            'heading': dest['heading'], 'source_artifact_sha256': dest['source_artifact_sha256'],
                            'blocks': [b for b in dest['blocks'] if b['block_id'] in t['block_ids']],
                            'units': units(dest['id'])})
        evidence[examples[r['id']]] = {'reference': r, 'source': s, 'source_units': units(s['id']),
                                     'targets': targets}

families = collections.Counter()
children_of_mok = collections.Counter()
for sid, family, parent_family, did in db.execute(
        'SELECT c.source_id,c.family,p.family,s.document_id FROM source_unit_map c '
        'JOIN source s ON s.id=c.source_id LEFT JOIN source_unit_map p '
        'ON c.source_id=p.source_id AND c.parent_id=p.unit_id'):
    if did in scope:
        families[family] += 1
        if parent_family == 'hangul_dot':
            children_of_mok[family] += 1
frames = {d: json.loads(j) for d, j in db.execute('SELECT document_id,json FROM document_frame') if d in scope}
manifest = json.loads((GEN / 'navigation/manifest.json').read_text())
compiler = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0522/guarded/revisions/rev-002/snapshot/02_BACKEND/semantic_runtime/term_references.py'
compiler_hash = hashlib.sha256(compiler.read_bytes()).hexdigest()
assert compiler_hash == manifest['reference_rebuild']['reference_compiler_sha256']
assert len(evidence) == len(examples)
result = {
    'kind': 'read_only_public_hierarchy_and_reference_audit',
    'generation': str(GEN.relative_to(ROOT)),
    'scope_document_count': len(scope), 'scope_sha256': hashlib.sha256(SCOPE.read_bytes()).hexdigest(),
    'navigation_sha256_from_manifest': manifest['index_sha256'], 'navigation_hash_recomputed': False,
    'compiler_sha256': compiler_hash, 'compiler_matches_rebuild_receipt': True,
    'counts': dict(counts), 'public_unit_map_families': dict(families),
    'public_unit_map_children_of_hangul_dot': dict(children_of_mok),
    'public_document_frames': frames, 'examples': evidence, 'screen_rows': dict(rows),
    'limitations': ['Screen counts are not adjudicated error counts or retrieval measurements.',
                   'Only public scope of the explicitly pinned candidate generation inspected.',
                   'No compiler/model execution, product modification, DB rebuild, or activation.',
                   'Current lawxml code is explanatory; original ingestion revision was not verified.'],
}
(OUT / 'hierarchy_audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
summary = {k: v for k, v in result.items() if k not in ('examples', 'screen_rows', 'public_document_frames')}
(OUT / 'hierarchy_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(summary, ensure_ascii=False, indent=2))
db.close()
