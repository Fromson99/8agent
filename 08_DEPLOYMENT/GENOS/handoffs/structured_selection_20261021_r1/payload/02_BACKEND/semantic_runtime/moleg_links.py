"""Official lexical links, compiled offline and consumed by the existing RAG.

No provider or network client lives on the request path. API article text is
never evidence: only coordinates reopened in the selected Store are returned.
"""
from collections import defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from urllib.parse import parse_qs, urlsplit

from .contracts import sha


def compact(text):
    return ''.join(unicodedata.normalize('NFKC', str(text)).split())


def matches(text, label):
    return list(Matcher([(label, label)]).find(text))


class Matcher:
    def __init__(self, labels):
        self.trie = {}
        for ident, label in labels:
            node = self.trie
            for char in compact(label):
                node = node.setdefault(char, {})
            node.setdefault('', []).append(ident)

    def find(self, text):
        chars, positions = [], []
        for i, char in enumerate(text):
            for normalized in unicodedata.normalize('NFKC', char):
                if not normalized.isspace():
                    chars.append(normalized)
                    positions.append(i)
        for i, _ in enumerate(chars):
            lo = positions[i]
            if lo and (text[lo - 1].isalnum() or text[lo - 1] == '_'):
                continue
            node = self.trie
            for j in range(i, len(chars)):
                node = node.get(chars[j])
                if node is None:
                    break
                hi = positions[j] + 1
                tail = text[hi:]
                boundary = not tail or not (tail[0].isalnum() or tail[0] == '_')
                particle = re.match(r'^(?:으로부터|으로|에서|에게|부터|까지|처럼|보다|에는|에도|이란|이라|하고|을|를|은|는|이|가|의|에|와|과|도|만)(?![\w가-힣])', tail)
                if boundary or particle:
                    for ident in node.get('', []):
                        yield ident, lo, hi


def main_article(store, did, uid):
    """A main-body article must have one article root and no supplement ancestor."""
    section = store.section(did, uid)
    ancestors = section['ancestors']
    if any(a.get('family') in {'buchik', 'kr_부칙', 'supplement', 'supplementary'}
           or a.get('title', '').strip().startswith('부칙') for a in ancestors):
        return None
    roots = [a for a in ancestors if a.get('family') in {'kr_article', 'kr_조'}]
    if len(roots) != 1:
        return None
    return store.section(did, roots[0]['id'])


def link_params(value, target):
    url = urlsplit(value)
    if url.netloc and url.hostname not in {'law.go.kr', 'www.law.go.kr'}:
        raise ValueError('unrecognized official link host')
    params = parse_qs(url.query)
    if params.get('target') != [target]:
        raise ValueError('unexpected official link target')
    return {k: v[0] for k, v in params.items() if len(v) == 1 and k != 'OC'}


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
                from lawrag.pipeline.glossary_enrichment import request_parameters
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
                from lawrag.pipeline.glossary_enrichment import request_parameters
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
    names = defaultdict(list)
    for did, name in store.db.execute('SELECT document_id,name FROM document'):
        names[compact(name)].append(did)
    law_ids = {}
    for record in (authority or {}).get('items', []):
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
        ids = names.get(compact(name), [])
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


class TermLinks:
    def __init__(self, store):
        self.store = store
        self.descriptor = store.manifest.get('term_links')
        if self.descriptor is not None and type(self.descriptor.get('enabled')) is not bool:
            raise ValueError('term link enabled flag must be boolean')
        self.enabled = bool(self.descriptor and self.descriptor.get('enabled'))
        self.receipt = {'status': 'DISABLED_OR_NOT_CONFIGURED'}
        if not self.enabled:
            return
        d = self.descriptor
        if d.get('schema_version') != 'moleg-rag-links-v1' or d.get('source_store_sha256') != store.manifest['store_sha256']:
            raise ValueError('term link/source generation mismatch')
        path = store.path / d['path']
        if path.is_symlink() or path.resolve().parent != store.path or sha(path) != d['sha256']:
            raise ValueError('term link index path/hash mismatch')
        self.uri = path.resolve().as_uri() + '?mode=ro'
        with closing(sqlite3.connect(self.uri, uri=True)) as db:
            self.labels = dict(db.execute('SELECT id,label FROM label'))
            self.edges = defaultdict(list)
            for source, target, kind, provenance in db.execute('SELECT * FROM edge ORDER BY source,target'):
                self.edges[source].append({'term_id': target, 'kind': kind, 'package_sha256': provenance})
        self.matcher = Matcher(sorted(self.labels.items()))
        self.receipt = {'status': 'ENABLED', 'index_sha256': d['sha256'], 'counts': d['counts'],
                        'package_sha256s': d['package_sha256s'], 'legal_effect': 'NOT_INFERRED'}

    def query_terms(self, question):
        found = sorted(self.matcher.find(question), key=lambda x: (-(x[2] - x[1]), x[1], x[0]))
        spans, terms = [], {}
        for ident, lo, hi in found:
            if any(a <= lo and hi <= b and (a, b) != (lo, hi) for a, b in spans):
                continue
            spans.append((lo, hi))
            origin = {'query_surface': question[lo:hi], 'query_start': lo, 'query_end': hi, 'source_term_id': ident}
            if ident.startswith('legal:'):
                terms.setdefault(ident, {**origin, 'kind': 'LITERAL'})
            for edge in self.edges.get(ident, [])[:4]:
                terms.setdefault(edge['term_id'], {**origin, **edge})
            if len(terms) >= 8:
                break
        return dict(list(terms.items())[:8])

    def retrieve(self, plan, limit):
        if not self.enabled:
            return [], self.receipt
        terms = self.query_terms(plan['question'])
        allowed = sorted(set(plan['scope']['document_version_ids']))
        rows, proofs, unresolved = {}, defaultdict(list), []
        with closing(sqlite3.connect(self.uri, uri=True)) as db:
            for tid, origin in terms.items():
                unresolved.extend({'term_id': tid, 'reason': r, 'detail': detail} for r, detail in
                                  db.execute('SELECT reason,detail FROM unresolved WHERE term=? LIMIT 20', (tid,)))
                if not allowed:
                    continue
                sql = 'SELECT document_id,block_id,kind,proof FROM hit WHERE term=? AND document_id IN (' + ','.join('?' for _ in allowed) + ') ORDER BY kind,document_id,CAST(block_id AS INTEGER) LIMIT ?'
                for did, bid, kind, raw in db.execute(sql, [tid, *allowed, limit]):
                    source = self.store.source(did, bid)
                    proof = json.loads(raw)
                    if source['source_artifact_sha256'] != proof['source_artifact_sha256']:
                        raise ValueError('term hit source drift')
                    if kind == 'SOURCE_TERM' and source['text'][proof['start']:proof['end']] != proof['quote']:
                        raise ValueError('term hit quote mismatch')
                    key = (did, bid)
                    rows[key] = source
                    proofs[key].append({'term_id': tid, 'term': self.labels[tid], **origin,
                                        'relation_kind': origin['kind'], **proof})
        keys = sorted(rows, key=lambda k: (not any(p['kind'] == 'OFFICIAL_TERM_ARTICLE' for p in proofs[k]), k))[:limit]
        receipt = {**self.receipt, 'terms': [{'term_id': tid, 'term': self.labels[tid], **origin} for tid, origin in terms.items()],
                   'hits': [{'document_id': d, 'block_id': b, 'proofs': proofs[(d, b)][:8]} for d, b in keys],
                   'unresolved': unresolved, 'query_network_calls': 0}
        return [rows[k] for k in keys], receipt

    def selected_context(self, selected):
        additions, seen, unresolved, chars, articles = [], set(), [], 0, set()
        for hit in selected:
            if 'moleg_terms' not in hit.get('routes', []):
                continue
            section = main_article(self.store, hit['document_id'], hit['unit_id'])
            if section is None:
                continue
            key = (section['document_id'], section['unit_id'])
            if key in articles:
                continue
            blocks = [b for b in section['blocks'] if (key[0], str(b['block_id'])) not in seen]
            size = sum(len(b['text']) for b in blocks)
            if len(articles) >= 4 or len(additions) + len(blocks) > 128 or chars + size > 24000:
                unresolved.append('MOLEG_ARTICLE_CONTEXT_BUDGET:' + ':'.join(key))
                continue
            articles.add(key)
            chars += size
            for b in blocks:
                seen.add((key[0], str(b['block_id'])))
                additions.append((key[0], str(b['block_id'])))
        return additions, unresolved


def build_generation(source, packages, output, *, authority=None):
    """Carry an immutable source generation forward with a freshly bound index."""
    import shutil
    from .storage import Store
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


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Bind completed official term packages to a source generation')
    parser.add_argument('--source-generation', type=Path, required=True)
    parser.add_argument('--package', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--authority-manifest', type=Path)
    args = parser.parse_args()
    authority = json.loads(args.authority_manifest.read_text()) if args.authority_manifest else None
    result = build_generation(args.source_generation, args.package, args.output, authority=authority)
    print(json.dumps({'generation_id': result['generation_id'], 'term_links': result['term_links']}, ensure_ascii=False, indent=2))
