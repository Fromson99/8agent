"""Select glossary requests from one explicit, immutable document generation."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .collect_moleg_knowledge import _atomic_json, _hash_file, _digest
from .glossary_alignment import Matcher

MODE = 'document-occurrences-one-hop-v1'


def compact(text):
    return ''.join(text.split())


def build_scope(catalogue, generation, folder, emit=print):
    generation, folder = Path(generation).resolve(), Path(folder)
    manifest = generation / 'manifest.json'
    store = generation / 'store.sqlite'
    if not manifest.is_file() or not store.is_file():
        raise ValueError('scope requires a document generation with manifest.json and store.sqlite')
    metadata = json.loads(manifest.read_text())
    fingerprint = _hash_file(store)
    if metadata.get('store_sha256') != fingerprint:
        raise ValueError('scope document store hash differs from its generation manifest')
    with closing(sqlite3.connect(Path(catalogue).resolve().as_uri() + '?mode=ro', uri=True)) as terms:
        terms.execute('BEGIN')
        catalog_hash = hashlib.sha256()
        entries = []
        for ident, key, digest in terms.execute("SELECT id,key,fingerprint FROM terms WHERE dataset IN ('moleg-knowledge-legal-terms','moleg-knowledge-knowledge-terms') ORDER BY id"):
            entries.append((ident, key))
            catalog_hash.update(json.dumps([ident, key, digest], separators=(',', ':')).encode())
    identity = {'mode': MODE, 'generation': str(generation), 'store_sha256': fingerprint,
                'manifest_sha256': _hash_file(manifest), 'catalogue_sha256': catalog_hash.hexdigest(),
                'scope_compiler_sha256': _hash_file(Path(__file__)),
                'matcher_sha256': _hash_file(Path(__file__).with_name('glossary_alignment.py'))}
    report_path = folder / 'scope.json'
    target = folder / 'scope.sqlite'
    if report_path.exists():
        report = json.loads(report_path.read_text())
        if report['identity'] != identity or _hash_file(target) != report['scope_sha256']:
            raise ValueError('document scope changed; use a new completion snapshot')
        return report
    if target.exists():
        raise ValueError('unfinished scope.sqlite: preserve it and use a new snapshot')
    folder.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(store.as_uri() + '?mode=ro', uri=True)) as source, closing(sqlite3.connect(target)) as out:
        source.execute('BEGIN')
        out.executescript('''
          CREATE TABLE document(id TEXT PRIMARY KEY,name TEXT NOT NULL,source_sha256 TEXT NOT NULL);
          CREATE TABLE occurrence(term_id TEXT NOT NULL,document_id TEXT NOT NULL,block_id TEXT NOT NULL,
            start INTEGER,end INTEGER,surface TEXT,is_definition INTEGER,
            PRIMARY KEY(term_id,document_id));
          CREATE TABLE local_definition(document_id TEXT,block_id TEXT,term TEXT,source_text TEXT,
            PRIMARY KEY(document_id,block_id,term));
          CREATE TABLE article(document_id TEXT,jo TEXT,PRIMARY KEY(document_id,jo));
        ''')
        docs = source.execute('SELECT document_id,name,source_artifact_sha256 FROM document ORDER BY document_id').fetchall()
        out.executemany('INSERT INTO document VALUES (?,?,?)', docs)
        for did, raw in source.execute('SELECT document_id,json FROM source_unit'):
            unit = json.loads(raw)
            if unit.get('family') != 'kr_article':
                continue
            match = re.fullmatch(r'제\s*(\d+)\s*조(?:\s*의\s*(\d+))?', unit.get('surface', '').strip())
            if match and int(match[1]) <= 9999 and int(match[2] or 0) <= 99:
                out.execute('INSERT OR IGNORE INTO article VALUES (?,?)',
                            (did, f'{int(match[1]):04d}{int(match[2] or 0):02d}'))
        matcher = Matcher(entries)
        quote = re.compile(r'["“「]([^"”」\n]{1,100})["”」]\s*(?:이란|란|이라\s*함은|라\s*함은)')
        for count, (did, name, _) in enumerate(docs, 1):
            found = {}
            for bid, text in source.execute('SELECT block_id,text FROM source_block WHERE document_id=? ORDER BY block_id', (did,)):
                for ident, lo, hi, definition in matcher.find(text):
                    if ident not in found or (definition and not found[ident][-1]):
                        found[ident] = (ident, did, str(bid), lo, hi, text[lo:hi], int(definition))
                for match in quote.finditer(text):
                    out.execute('INSERT OR IGNORE INTO local_definition VALUES (?,?,?,?)',
                                (did, str(bid), match[1], text))
            out.executemany('INSERT INTO occurrence VALUES (?,?,?,?,?,?,?)', found.values())
            out.commit()
            if count == 1 or count % 20 == 0 or count == len(docs):
                emit(f'glossary scope: {count}/{len(docs)} documents scanned', flush=True)
        counts = {name: out.execute('SELECT count(*) FROM ' + name).fetchone()[0]
                  for name in ('document', 'occurrence', 'article', 'local_definition')}
        counts['seed_terms'] = out.execute('SELECT count(DISTINCT term_id) FROM occurrence').fetchone()[0]
        counts['legal_terms'] = out.execute("SELECT count(DISTINCT term_id) FROM occurrence WHERE term_id LIKE 'moleg:legal_terms:%'").fetchone()[0]
        counts['knowledge_terms'] = out.execute("SELECT count(DISTINCT term_id) FROM occurrence WHERE term_id LIKE 'moleg:knowledge_terms:%'").fetchone()[0]
        if not counts['document'] or not counts['seed_terms']:
            raise ValueError('scope has no documents or registered terms; do not collect globally')
        if out.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('scope index integrity failure')
    if _hash_file(store) != fingerprint:
        raise ValueError('document store changed during scope selection')
    report = {'identity': identity, 'scope_sha256': _hash_file(target), 'counts': counts,
              'path': str(target.resolve()), 'max_relation_hops': 1,
              'article_filter': 'selected document name and article coordinate',
              'definition_policy': 'source-scoped candidates for occurring terms; applicability is not inferred',
              'local_definition_policy': 'quoted definition evidence from source blocks; not canonical approval'}
    _atomic_json(report_path, report)
    return report


def seed_terms(scope):
    with closing(sqlite3.connect(Path(scope['path']).as_uri() + '?mode=ro', uri=True)) as db:
        return {r[0] for r in db.execute('SELECT DISTINCT term_id FROM occurrence')}


def article_scope(scope):
    with closing(sqlite3.connect(Path(scope['path']).as_uri() + '?mode=ro', uri=True)) as db:
        return {(compact(name), jo) for name, jo in db.execute(
            'SELECT d.name,a.jo FROM document d JOIN article a ON a.document_id=d.id')}


def include_article(row, allowed):
    fields = row.get('fields', {})
    from urllib.parse import parse_qs, urlsplit
    link = parse_qs(urlsplit(fields.get('조문연계용어링크', '').replace('&amp;', '&')).query)
    jo = link.get('JO', [''])[0]
    return (compact(row.get('label', '')), jo) in allowed



def compile_scope(db, path, report):
    if _hash_file(Path(path)) != report['scope_sha256']:
        raise ValueError('packaged document scope hash mismatch')
    if db.execute('SELECT count(*) FROM scope_document').fetchone()[0]:
        raise ValueError('choose one document scope per dictionary generation')
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as source:
        for table, target, columns in [('document', 'scope_document', 3),
                                        ('local_definition', 'scope_definition', 4),
                                        ('occurrence', 'scope_occurrence', 7)]:
            db.executemany('INSERT INTO ' + target + ' VALUES (' + ','.join('?' for _ in range(columns)) + ')',
                           source.execute('SELECT * FROM ' + table))
