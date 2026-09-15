"""GENOS offline MOLEG compiler, derived from ADR-0363 and source-bound XML aliases.

Produces the unchanged moleg-rag-links-v1 format consumed by the released RAG.
No request-time adapter or active engine code is replaced.
"""
from collections import defaultdict
import json
from pathlib import Path
import re
import sqlite3
from semantic_runtime.contracts import sha
from semantic_runtime.moleg_links import compact, matches, main_article, link_params


def compile_links(store, packages, output, *, authority=None):
    """Build a standalone index from completed DatasetPackages; never query APIs."""
    from lawrag.datasets.catalog import load_package
    from lawrag.pipeline.glossary_enrichment import relation_target, package_rows
    output = Path(output)
    if output.exists():
        raise ValueError('immutable term index already exists')
    labels, edges, article_records, package_hashes = {}, [], [], []
    excluded = defaultdict(int)
    for path in map(Path, packages):
        package = load_package(path, verify_files=True)
        manifest = json.loads(path.read_text())
        if manifest.get('source_origin') != 'public_external' or manifest.get('authority') != 'authoritative':
            raise ValueError('official source package required')
        artifacts = {Path(a.path).name: a for a in package.artifacts}
        plan = json.loads((path.parent / artifacts['request-plan.json'].path).read_text())
        if not plan.get('checkpoint', {}).get('completed'):
            raise ValueError('unfinished term package')
        provenance = sha(path)
        package_hashes.append(provenance)
        for r in package_rows(path.parent / artifacts['records.jsonl'].path):
            fields = r['fields']
            if r['entity_type'] in {'everyday_term_relations', 'legal_term_relations'}:
                prefix = 'daily:' if r['entity_type'] == 'everyday_term_relations' else 'legal:'
                from .glossary_enrichment import request_parameters
                source_id = request_parameters(r, plan).get('MST')
                if not source_id or not fields.get('_기준용어명'):
                    raise ValueError('term package must preserve requested source MST')
                source = prefix + source_id
                resolved = relation_target(r)
                target = ('daily:' if resolved.startswith('moleg:everyday_terms:') else 'legal:') + resolved.rsplit(':', 1)[1]
                labels[source] = fields['_기준용어명']
                labels[target] = r['label']
                kind = {'140301': 'SYNONYM', '140305': 'RELATED'}.get(fields.get('용어관계코드'))
                expected = {'동의어': 'SYNONYM', '연관어': 'RELATED', '관련어': 'RELATED'}.get(fields.get('용어관계'))
                if kind is None or kind != expected:
                    excluded[fields.get('용어관계코드', 'UNKNOWN')] += 1
                    continue
                edges.append((source, target, kind, provenance))
            elif r['entity_type'] == 'term_articles':
                from .glossary_enrichment import request_parameters
                mst = request_parameters(r, plan).get('MST')
                if not mst:
                    raise ValueError('article package must preserve requested term MST')
                tid = 'legal:' + mst
                labels[tid] = fields['_기준용어명']
                params = link_params(fields['조문연계용어링크'], 'joRltLstrm')
                if not re.fullmatch(r'\d{6}', params.get('ID', '')) or not re.fullmatch(r'\d{6}', params.get('JO', '')):
                    raise ValueError('invalid law ID/article coordinate')
                jo = fields['조번호'].zfill(4) + fields.get('조가지번호', '00').zfill(2)
                if jo != params['JO']:
                    raise ValueError('article coordinate/link mismatch')
                article_records.append((tid, r['label'], params['ID'], jo, provenance))
            else:
                raise ValueError('unsupported relation package')
    names = defaultdict(set)
    source_hashes = {}
    for did, name, fingerprint in store.db.execute('SELECT document_id,name,source_artifact_sha256 FROM document'):
        names[compact(name)].add(did)
        source_hashes[did] = fingerprint
    law_ids = {}
    for record in (authority or {}).get('items', []):
        # GENOS display names contain folder labels. Accept the separately
        # parsed official XML title only when bound to these exact source bytes.
        fingerprint = record.get('body_sha256', '')
        did = fingerprint[:16]
        if record.get('official_name') and source_hashes.get(did) == fingerprint:
            names[compact(record['official_name'])].add(did)
        if record.get('law_id') and record.get('body_sha256'):
            law_ids[record['body_sha256'][:16]] = record['law_id']
    output.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(output)
    db.executescript('''
      CREATE TABLE label(id TEXT PRIMARY KEY,label TEXT NOT NULL);
      CREATE TABLE edge(source TEXT,target TEXT,kind TEXT,provenance TEXT,PRIMARY KEY(source,target,kind,provenance));
      CREATE TABLE hit(term TEXT,document_id TEXT,block_id TEXT,unit_id TEXT,kind TEXT,proof TEXT,
                       PRIMARY KEY(term,document_id,block_id,kind));
      CREATE INDEX hit_term_document ON hit(term,document_id);
      CREATE TABLE unresolved(term TEXT,reason TEXT,detail TEXT);
    ''')
    db.executemany('INSERT INTO label VALUES (?,?)', sorted(labels.items()))
    db.executemany('INSERT OR IGNORE INTO edge VALUES (?,?,?,?)', edges)
    for tid, name, lawid, jo, provenance in sorted(set(article_records)):
        ids = sorted(names.get(compact(name), []))
        reason = None
        if len(ids) != 1:
            reason = 'LAW_NOT_IN_CORPUS' if not ids else 'AMBIGUOUS_LAW'
        elif law_ids.get(ids[0], lawid) != lawid:
            reason = 'LAW_ID_MISMATCH'
        if reason:
            db.execute('INSERT INTO unresolved VALUES (?,?,?)', (tid, reason, name + ':' + jo))
            continue
        did = ids[0]
        surface = '제' + str(int(jo[:4])) + '조' + ('의' + str(int(jo[4:])) if int(jo[4:]) else '')
        units = []
        for uid, in store.db.execute("SELECT unit_id FROM source_unit WHERE document_id=? AND json_extract(json,'$.surface')=? AND json_extract(json,'$.family') IN ('kr_article','kr_조')", (did, surface)):
            section = main_article(store, did, uid)
            if section:
                units.append(section)
        if len(units) != 1 or not units[0]['blocks']:
            db.execute('INSERT INTO unresolved VALUES (?,?,?)', (tid, 'ARTICLE_MISSING_OR_AMBIGUOUS', name + ':' + jo))
            continue
        section = units[0]
        block = section['blocks'][0]
        if re.match(r'^제\s*\d+\s*조(?:의\d+)?(?:\([^)]*\))?\s*삭제', block['text']):
            db.execute('INSERT INTO unresolved VALUES (?,?,?)', (tid, 'DELETED_ARTICLE', name + ':' + jo))
            continue
        # Prefer the actual matching block within this article for selector context.
        block = next((b for b in section['blocks'] if matches(b['text'], labels[tid])), block)
        current = store.source(did, block['block_id'])
        proof = {'kind': 'OFFICIAL_TERM_ARTICLE', 'law_id': lawid, 'jo': jo,
                 'resolution': 'ID_AND_TITLE' if did in law_ids else 'UNIQUE_OFFICIAL_TITLE',
                 'package_sha256': provenance, 'source_artifact_sha256': current['source_artifact_sha256']}
        db.execute('INSERT OR IGNORE INTO hit VALUES (?,?,?,?,?,?)',
                   (tid, did, str(block['block_id']), section['unit_id'], 'API_ARTICLE', json.dumps(proof, ensure_ascii=False)))
    for tid, label in sorted(labels.items()):
        if not tid.startswith('legal:') or len(compact(label)) < 2:
            continue
        if len(label) >= 3:
            rows = store.db.execute('SELECT document_id,block_id,text FROM lexical WHERE lexical MATCH ? ORDER BY bm25(lexical),document_id,block_id LIMIT 500', ('"' + label.replace('"', '""') + '"',))
        else:
            rows = store.db.execute('SELECT document_id,block_id,text FROM source_block WHERE instr(text,?)>0 ORDER BY document_id,CAST(block_id AS INTEGER) LIMIT 500', (label,))
        for did, bid, text in rows:
            found = matches(text, label)
            if not found:
                continue
            source = store.source(did, bid)
            if not source.get('unit_id'):
                continue
            section = main_article(store, did, source['unit_id'])
            if section is None:
                continue
            _, lo, hi = found[0]
            proof = {'kind': 'CURRENT_SOURCE_TERM', 'start': lo, 'end': hi, 'quote': text[lo:hi],
                     'source_artifact_sha256': source['source_artifact_sha256']}
            db.execute('INSERT OR IGNORE INTO hit VALUES (?,?,?,?,?,?)',
                       (tid, did, str(bid), section['unit_id'], 'SOURCE_TERM', json.dumps(proof, ensure_ascii=False)))
    db.commit()
    counts = {table: db.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in ('label', 'edge', 'hit', 'unresolved')}
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    db.close()
    return {'schema_version': 'moleg-rag-links-v1', 'enabled': True, 'path': output.name,
            'sha256': sha(output), 'source_store_sha256': store.manifest['store_sha256'],
            'package_sha256s': sorted(package_hashes), 'counts': counts,
            'excluded_relation_counts': dict(excluded), 'query_network_calls': 0}


def build_generation(source, packages, output, *, authority=None):
    """Carry an immutable source generation forward with a freshly bound index."""
    import shutil
    from semantic_runtime.storage import Store
    source, output = Path(source), Path(output)
    if output.exists():
        raise ValueError('immutable generation already exists')
    store = Store(source)
    try:
        output.mkdir(parents=True)
        manifest = dict(store.manifest)
        descriptor = compile_links(store, packages, output / 'moleg-links.sqlite', authority=authority)
        for name in ('store.sqlite', 'projection.json'):
            shutil.copyfile(source / name, output / name)
        vector = manifest.get('vectors')
        if vector:
            path = source / vector['path']
            if path.resolve().parent != source.resolve() or sha(path) != vector['sha256']:
                raise ValueError('parent vector artifact mismatch')
            shutil.copyfile(path, output / vector['path'])
        if manifest.get('source_selection'):
            name = manifest['source_selection']['path']
            if Path(name).name != name or sha(source / name) != manifest['source_selection']['sha256']:
                raise ValueError('parent source selection artifact mismatch')
            shutil.copyfile(source / name, output / name)
        manifest.update(generation_id=output.name, term_links=descriptor,
                        parent_generation_manifest_sha256=sha(source / 'manifest.json'))
        (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        return manifest
    finally:
        store.close()
