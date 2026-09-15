"""Versioned source knowledge for authoring; no canonical approval or model calls.

Copies source ledgers unchanged, adds lookup indexes in a new generation, and
keeps original predicates, mapping decisions and translation provenance separate.
"""
from contextlib import closing
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile

from lawrag.platform.workspace import load_layout
from .glossary_v1 import compact, encode

VERSION = 'glossary-knowledge-bundle-v1'
_VERIFIED = {}


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read_db(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def location(layout, ref):
    relative = Path(ref['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Invalid knowledge relative path')
    base = layout.inspection_path(ref['root_id'], layout_version='v2').resolve()
    path = base / relative
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Knowledge symlinks are forbidden')
    path.resolve().relative_to(base)
    return path


def configured(root=None):
    layout = load_layout(root)
    config = json.loads((layout.root / '00_SYSTEM/GLOSSARY_PIPELINE.json').read_text())
    ref = config.get('knowledge_bundle')
    if not ref or not ref.get('enabled'):
        return None
    path = location(layout, ref)
    if sha(path / 'manifest.json') != ref['manifest_sha256']:
        raise ValueError('Configured knowledge manifest hash mismatch')
    return path


def selected_for(glossary):
    layout = load_layout()
    # Explicit standalone test/custom dictionaries have their own contracts.
    if not Path(glossary).resolve().is_relative_to(layout.inspection_path('data', layout_version='v2').resolve()):
        return None
    return configured(layout.root)


def verify(directory, *, force=False):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest['schema_version'] != VERSION:
        raise ValueError('Unknown knowledge bundle version')
    for row in manifest['files']:
        relative = Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe knowledge file')
        path = directory / relative
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('Knowledge symlink')
        st = path.stat()
        if path.suffix == '.sqlite' and Path(str(path) + '-wal').exists() and Path(str(path) + '-wal').stat().st_size:
            raise ValueError('Knowledge database has unbound WAL changes')
        identity = (str(path), st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino)
        if force or _VERIFIED.get(identity) != row['sha256']:
            if st.st_size != row['bytes'] or sha(path) != row['sha256']:
                raise ValueError('Knowledge payload hash mismatch: ' + row['path'])
            _VERIFIED[identity] = row['sha256']
    return manifest


def binding(directory):
    manifest = verify(directory)
    return {'schema_version': VERSION, 'manifest_sha256': sha(Path(directory) / 'manifest.json'),
            'dictionary_sha256': manifest['dictionary_sha256'], 'code_sha256': sha(__file__),
            'counts': manifest['counts'], 'canonical_approval': False}


def build(config_path, output):
    layout = load_layout()
    config = json.loads(Path(config_path).read_text())
    output = Path(output).resolve()
    output.relative_to(layout.inspection_path('data', layout_version='v2').resolve())
    if output.exists():
        raise ValueError('Use a new knowledge output directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.' + output.name + '-', dir=output.parent))
    inputs = []
    for row in config['sources']:
        source = location(layout, row)
        if sha(source) != row['sha256']:
            raise ValueError('Pinned knowledge source changed: ' + row['path'])
        if source.suffix == '.sqlite' and Path(str(source) + '-wal').exists() and Path(str(source) + '-wal').stat().st_size:
            raise ValueError('Snapshot a completed database without pending WAL writes')
        destination = Path(row['destination'])
        if destination.is_absolute() or '..' in destination.parts:
            raise ValueError('Unsafe knowledge destination')
        target = temp / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha(target) != row['sha256'] or sha(source) != row['sha256']:
            raise ValueError('Source changed while copying')
        inputs.append(row)
        print('copied:', row['destination'], flush=True)
    # Original ledgers are preserved locally. These new copies only gain indexes.
    indexes = {
        'graph.sqlite': ['CREATE INDEX delivery_edge_target ON edge(source,target)',
                         'CREATE INDEX delivery_label_value ON label(value)'],
        'translations.sqlite': ['CREATE INDEX delivery_unit_node ON unit(source,node_id,kind)'],
        'identity.sqlite': ['CREATE INDEX delivery_mapping_entry ON concept_mapping(entry_id)',
                            'CREATE INDEX delivery_mapping_node ON concept_mapping(source,node_id)',
                            'CREATE INDEX delivery_official_source ON official_relation(source_id)',
                            'CREATE INDEX delivery_official_target ON official_relation(target_id)'],
    }
    for name, statements in indexes.items():
        with sqlite3.connect(temp / name) as db:
            db.execute('PRAGMA journal_mode=DELETE')
            for sql in statements:
                db.execute(sql)
    with closing(read_db(temp / 'graph.sqlite')) as graph, closing(read_db(temp / 'translations.sqlite')) as tr, sqlite3.connect(temp / 'lookup.sqlite') as lookup:
        lookup.executescript('''CREATE TABLE surface(key TEXT,source TEXT,node_id TEXT,label TEXT,kind TEXT,
            PRIMARY KEY(key,source,node_id,label,kind));''')
        lookup.executemany('INSERT OR IGNORE INTO surface VALUES (?,?,?,?,?)',
            ((compact(r['value']), r['source'], r['node_id'], r['value'], 'SOURCE_LABEL')
             for r in graph.execute('SELECT * FROM label') if compact(r['value'])))
        lookup.executemany('INSERT OR IGNORE INTO surface VALUES (?,?,?,?,?)',
            ((compact(r['translation_ko']), r['source'], r['node_id'], r['translation_ko'], r['status'])
             for r in tr.execute("SELECT * FROM unit WHERE kind='LABEL' AND status IN ('NATIVE','TRANSLATED')")
             if compact(r['translation_ko'] or '')))
    counts = {}
    for name in ('graph', 'translations', 'identity', 'legal', 'lookup'):
        with closing(read_db(temp / (name + '.sqlite'))) as db:
            counts[name] = {r[0]: db.execute('SELECT count(*) FROM "' + r[0] + '"').fetchone()[0]
                           for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Knowledge database integrity failure: ' + name)
    files = [{'path': p.relative_to(temp).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}
             for p in sorted(temp.rglob('*')) if p.is_file()]
    manifest = {'schema_version': VERSION, 'dictionary_sha256': config['dictionary_sha256'],
                'inputs': inputs, 'transform': 'byte copies plus declared SQLite indexes; separate literal lookup index',
                'indexes': indexes, 'counts': counts, 'files': files, 'model_calls': 0,
                'canonical_approval': False, 'runtime_promoted': False,
                'consumer': 'build-all preflight; glossary_linking document matches and authoring dictionary_lookup'}
    (temp / 'manifest.json').write_text(encode(manifest) + '\n')
    if output.exists():
        raise ValueError('Output appeared during build')
    os.rename(temp, output)
    return manifest


class Knowledge:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.identity = binding(directory)
        self.dbs = {name: read_db(self.directory / (name + '.sqlite'))
                    for name in ('graph', 'translations', 'identity', 'legal', 'lookup')}

    def close(self):
        for db in self.dbs.values():
            db.close()

    def surfaces(self):
        return (r[0] for r in self.dbs['lookup'].execute('SELECT DISTINCT key FROM surface'))

    def matches(self, key):
        return [dict(r) for r in self.dbs['lookup'].execute(
            'SELECT * FROM surface WHERE key=? ORDER BY source,node_id,label,kind', (key,))]

    def node(self, source, ident, *, limit=8, offset=0):
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError('Invalid relation page')
        graph = self.dbs['graph']
        row = graph.execute('SELECT payload FROM node WHERE source=? AND id=?', (source, ident)).fetchone()
        translations = [dict(r) for r in self.dbs['translations'].execute(
            'SELECT id,kind,original,original_sha256,translation_ko,status,needs_review,origin_locator FROM unit WHERE source=? AND node_id=? ORDER BY kind,id', (source, ident))]
        # An OR under source=? makes SQLite scan every edge of the source.
        # Separate indexed endpoints keep lookup proportional to the neighbourhood.
        ids = 'SELECT id FROM edge WHERE source=? AND subject=? UNION SELECT id FROM edge WHERE source=? AND target=?'
        params = (source, ident, source, ident)
        total = graph.execute('SELECT count(*) FROM (' + ids + ')', params).fetchone()[0]
        edges = [dict(r) for r in graph.execute('SELECT * FROM edge WHERE id IN (' + ids +
                 ') ORDER BY id LIMIT ? OFFSET ?', (*params, limit, offset))]
        for edge in edges:
            edge['status'] = 'MAPPING_CANDIDATE' if edge['predicate'] == 'shared_external_concept_candidate' else 'SOURCE_RECORDED'
        return {'source': source, 'node_id': ident, 'source_payload': json.loads(row[0]) if row else None,
                'translations': translations, 'relations': edges, 'relations_total': total,
                'offset': offset, 'next_offset': offset + len(edges) if offset + len(edges) < total else None,
                'canonical_approval': False}

    def context(self, key, entry_ids=()):
        if not entry_ids:
            entry_ids=[r[0] for r in self.dbs['graph'].execute('SELECT DISTINCT entry_id FROM term_surface WHERE normalized=?',(key,))]
        matches = self.matches(key)
        nodes = sorted({(r['source'], r['node_id']) for r in matches})
        mappings, legal_edges, official_edges = [], {}, {}
        for entry in entry_ids:
            mappings.extend(dict(r) for r in self.dbs['identity'].execute(
                'SELECT * FROM concept_mapping WHERE entry_id=? ORDER BY source,node_id', (entry,)))
            for row in self.dbs['legal'].execute('SELECT * FROM edge WHERE source_id=? OR target_id=? ORDER BY id', (entry, entry)):
                legal_edges[row['id']] = dict(row)
            for row in self.dbs['identity'].execute('SELECT * FROM official_relation WHERE source_id=? OR target_id=? ORDER BY id', (entry,entry)):
                value=dict(row); value.pop('payload',None); official_edges[row['id']]=value
        mapped = {(r['source'], r['node_id']) for r in mappings}
        nodes = sorted(set(nodes) | mapped)
        selected = []
        chosen=[]
        for source in sorted({r[0] for r in nodes}):
            chosen.append(next(r for r in nodes if r[0]==source))
        chosen=(chosen+[r for r in nodes if r not in chosen])[:3]
        for source, ident in chosen:
            detail = self.node(source, ident, limit=6)
            payload = detail.pop('source_payload') or {}
            detail['source_definitions'] = [str(x)[:800] for x in payload.get('definitions', [])[:2]]
            detail['source_definitions_total'] = len(payload.get('definitions', []))
            detail['source_definitions_truncated'] = len(payload.get('definitions', [])) > 2 or any(len(str(x)) > 800 for x in payload.get('definitions', []))
            full = detail['translations']; detail['translations'] = full[:4]
            detail['translations_total'] = len(full)
            detail['translations_truncated'] = len(full)>len(detail['translations'])
            for item in detail['translations']:
                item['text_truncated'] = any(len(item[k] or '') > 800 for k in ('original', 'translation_ko'))
                for k in ('original', 'translation_ko'):
                    item[k] = (item[k] or '')[:800]
            # Payloads remain available in the complete graph ledger by edge ID.
            for edge in detail['relations']:
                edge.pop('payload', None)
            selected.append(detail)
        return {'manifest_sha256': self.identity['manifest_sha256'], 'concepts': selected, 'concepts_total': len(nodes),
                'concepts_truncated': len(nodes) > len(selected),
                'concept_mappings': mappings[:8], 'concept_mappings_total': len(mappings),
                'concept_mappings_truncated':len(mappings)>8,
                'legal_relations': list(legal_edges.values())[:8], 'legal_relations_total': len(legal_edges),
                'legal_relations_truncated':len(legal_edges)>8,
                'official_relations': list(official_edges.values())[:8], 'official_relations_total':len(official_edges),
                'official_relations_truncated':len(official_edges)>8,
                'canonical_approval': False,
                'instruction': '원천 관계·번역·대응 후보를 구분한다. 한국어 표기 일치나 번역은 법률 의미 동일성/적용의 승인이 아니다. 보류·충돌을 유지하고 법적 판단은 문서 원문으로 검토한다.'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['build', 'check', 'lookup', 'inspect'])
    p.add_argument('--config', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--state', type=Path)
    p.add_argument('--term')
    p.add_argument('--source')
    p.add_argument('--node-id')
    p.add_argument('--limit', type=int, default=50)
    p.add_argument('--offset', type=int, default=0)
    args = p.parse_args(argv)
    if args.action == 'build':
        if not args.config or not args.output:
            p.error('build requires --config and --output')
        result = build(args.config, args.output)
    else:
        state = args.state or configured()
        if state is None:
            p.error('No knowledge bundle selected')
        if args.action == 'check':
            result = {'ok': True, **binding(state)}
        else:
            with closing(Knowledge(state)) as knowledge:
                if args.action == 'lookup':
                    if not args.term:
                        p.error('lookup requires --term')
                    result = knowledge.context(compact(args.term))
                else:
                    if not args.source or not args.node_id:
                        p.error('inspect requires --source and --node-id')
                    result = knowledge.node(args.source, args.node_id, limit=args.limit, offset=args.offset)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
