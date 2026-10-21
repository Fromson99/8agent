"""Official law abbreviations (법령명약칭) as a pinned projection of one serving generation.

The store of an existing generation is bound by hash to its navigation index, so the
abbreviation is not written into it. It is read from the law.go.kr XML that the origin
projection already verified for each document, and served as navigation metadata:
a document-name alias, never legal evidence.
"""
import hashlib
import json
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

SCHEMA = 'document-alias-projection-v1'


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# law.go.kr writes the 가운뎃점 as ㆍ (U+318D, NFKC -> U+119E); stored names may carry · or ・.
MIDDLE_DOTS = str.maketrans({'ㆍ': '·', '\u119e': '·', '・': '·', '‧': '·', '•': '·'})


def _key(text):
    return ''.join(unicodedata.normalize('NFKC', text).translate(MIDDLE_DOTS).split())


def build(root, store, origin_projection):
    """Abbreviations of the documents whose verified XML names the same law as the store."""
    root = Path(root).resolve()
    for k in ('generation_id', 'store_sha256'):
        if origin_projection[k] != store.manifest[k]:
            raise ValueError('stale origin projection')
    names = {r['document_id']: r['name'] for r in store.db.execute('SELECT document_id,name FROM document')}
    documents, skipped = {}, {}
    for did, evidence in sorted(origin_projection['evidence'].items()):
        if did not in names:
            continue
        found = {}
        for link in evidence['chain']:
            if not link['source_artifact'].endswith('.xml'):
                continue
            package = (root / link['package_manifest']).resolve()
            package.relative_to(root)
            if _sha(package) != link['package_manifest_sha256']:
                raise ValueError('package manifest hash mismatch: ' + link['package_manifest'])
            path = (package.parent / link['source_artifact']).resolve()
            path.relative_to(package.parent)
            if _sha(path) != link['source_sha256']:
                raise ValueError('source artifact hash mismatch: ' + str(path))
            law = ET.parse(path).getroot()
            title = (law.findtext('.//법령명_한글') or '').strip()
            short = (law.findtext('.//법령명약칭') or '').strip()
            if not title:
                continue
            if _key(title) != _key(names[did]):
                skipped[did] = 'XML 법령명_한글과 저장 문서명이 다릅니다: ' + title
                found = {}
                break
            if short and _key(short) != _key(title):
                found.setdefault(short, {'surface': short, 'field': '법령명약칭', 'source_artifact':
                                         str(path.relative_to(root)), 'source_sha256': link['source_sha256']})
        if len(found) > 1:
            skipped[did] = '출처 XML의 약칭이 서로 다릅니다: ' + ', '.join(sorted(found))
        elif found:
            documents[did] = {'name': names[did], 'aliases': list(found.values())}
    return {'schema_version': SCHEMA, 'generation_id': store.manifest['generation_id'],
            'store_sha256': store.manifest['store_sha256'],
            'origin_projection_store_sha256': origin_projection['store_sha256'],
            'method': 'law.go.kr XML 법령명약칭 of origin-verified source artifacts; name must equal the stored document name',
            'documents': documents, 'skipped': skipped}


def load(root, config, store):
    """Select the pinned alias projection for this exact generation; other generations get none."""
    bindings = [b for b in (config or {}).get('alias_projections', [])
                if b.get('generation_id') == store.manifest['generation_id']]
    if not bindings:
        return {}
    if len(bindings) != 1:
        raise ValueError('multiple alias projections for one generation')
    base = Path(root).resolve()
    path = (base / bindings[0]['path']).resolve()
    path.relative_to(base)
    from .navigation_agent import _verified_json
    try:
        value = _verified_json(path, bindings[0]['sha256'])
    except ValueError as exc:
        raise ValueError('alias projection hash mismatch') from exc
    if value.get('schema_version') != SCHEMA:
        raise ValueError('unsupported alias projection')
    for k in ('generation_id', 'store_sha256'):
        if value.get(k) != store.manifest[k]:
            raise ValueError('stale alias projection')
    return {did: tuple(a['surface'] for a in doc['aliases']) for did, doc in value['documents'].items()}


def status(root, config, store):
    """Where this generation's law abbreviations come from; NONE is reported, never implied."""
    stored = set()
    for did, raw in store.db.execute("SELECT document_id,json_extract(json,'$.document_metadata') FROM document"):
        meta = json.loads(raw) if raw else {}
        if any(item.get('official_abbreviation') for item in [meta, *meta.get('aliases', [])]):
            stored.add(did)
    projected = set(load(root, config, store)) - stored
    binding = next((b['path'] for b in (config or {}).get('alias_projections', [])
                    if b.get('generation_id') == store.manifest['generation_id']), None)
    kind = '+'.join(k for k, v in (('STORE', stored), ('PROJECTION', projected)) if v) or 'NONE'
    return {'status': kind, 'store_documents': len(stored), 'projection_documents': len(projected),
            'projection': binding}
