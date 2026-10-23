"""Offline real-source structural audit, never imported by product execution.

Full native compilation supplies an independent canonical projection. The local
delta database demonstrates immutable reuse, dependency invalidation and CAS.
This is NOT an Oracle publisher or a production incremental reference compiler.
"""
import copy
from dataclasses import asdict
import difflib
import hashlib
import json
from pathlib import Path
import resource
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from lawrag.platform.paths import root_path
from lawrag.core.structure import lawxml, viewer
from semantic_runtime.term_index import compile_index
from semantic_runtime.term_references import ARTICLE

ADR = root_path('experiments', 'ADR', 'ADR-1038-law-version-incremental-audit')
OUT = ADR / 'artifacts/run-001'

def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError('immutable output exists: ' + str(path))
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def article_projection(root):
    tree, _ = lawxml.law_tree(root)
    result = {}
    def walk(items, context):
        for u in items:
            if u.kind == '조':
                if u.surface in result:
                    raise ValueError('duplicate article')
                result[u.surface] = {'context': context, 'tree': asdict(u)}
            else:
                walk(u.children, context + [u.heading])
    walk(tree, [])
    return result

def build_native(item, empty):
    raw_path = ROOT / item['path']
    if sha(raw_path) != item['sha256']:
        raise ValueError('raw input drift')
    version = item['params']['MST'] + '-' + item['params']['efYd']
    folder = OUT / version
    folder.mkdir()
    raw = raw_path.read_bytes()
    root = ET.fromstring(raw)
    title = item['metadata']['name']
    # Exact existing XML parser and viewer: no invented hierarchy or text.
    result, blocks, pdf, info = lawxml.build(raw.decode('utf-8'), title)
    data = viewer.payload(result, blocks)
    viewer.annotate_coordinate_scopes(data['nodes'], 'law')
    data['doc'] = title
    save(folder / 'structure.json', data)
    del result, blocks, pdf
    did = 'law:012338:' + version
    db = sqlite3.connect(folder / 'source.sqlite')
    db.row_factory = sqlite3.Row
    db.executescript('''
      CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
      CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT,PRIMARY KEY(document_id,unit_id));
      CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT,PRIMARY KEY(document_id,block_id));
    ''')
    db.execute('INSERT INTO document VALUES(?,?,?,?)', (did, title, item['sha256'], encode(data)))
    for n in data['nodes']:
        db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',
                   (did, str(n['id']), str(n['parent']) if n.get('parent') is not None else None, encode(n)))
    for b in data['blocks']:
        db.execute('INSERT INTO source_block VALUES(?,?,?,?,?,?)',
                   (did, str(b['idx']), str(b['node']) if b.get('node') is not None else None,
                    b.get('text') or '', item['sha256'], encode(b)))
    db.commit()
    source_manifest = {'generation_id': version, 'store_sha256': sha(folder / 'source.sqlite')}
    store = SimpleNamespace(db=db, manifest=source_manifest)
    nav = compile_index(store, empty, empty, folder / 'navigation', reference_scope_v2=True)
    db.close()
    units = {str(n['id']): n for n in data['nodes']}
    def unit_key(uid):
        path, seen = [], set()
        while uid is not None and str(uid) in units:
            uid = str(uid)
            if uid in seen:
                raise ValueError('cycle')
            seen.add(uid)
            n = units[uid]
            path.append([n.get('family'), n.get('ordinal'), n.get('surface')])
            uid = n.get('parent')
        return list(reversed(path))
    refs, excluded = [], 0
    with sqlite3.connect(folder / 'navigation/navigation.sqlite') as index:
        sources = {sid: json.loads(value) for sid, value in index.execute('SELECT id,json FROM source')}
        article_of = {sid: (ARTICLE.match(s['heading']).group().replace(' ', '')
                            if ARTICLE.match(s['heading']) else None) for sid, s in sources.items()}
        for value, in index.execute('SELECT json FROM reference ORDER BY id'):
            r = json.loads(value)
            source = article_of[r['source_id']]
            if not source:
                excluded += 1
                continue
            # Physical IDs/offsets in XML order are version-specific. Compare
            # their legal paths, exact witness and target scope instead.
            target = []
            for t in r.get('targets', []):
                target.append({'article': article_of[t['source_id']],
                               'path': unit_key(t.get('unit_id')), 'level': t.get('target_level'),
                               'texts': [b['text'] for b in sources[t['source_id']]['blocks']
                                         if b['block_id'] in t.get('block_ids', [])]})
            refs.append({'source_article': source, 'source_path': unit_key(r.get('source_unit_id')),
                         **{k: r.get(k) for k in ('source_text', 'mention_text', 'mention_start', 'mention_end',
                              'document_name_hint', 'document_hint_basis', 'locator', 'resolution',
                              'resolution_state', 'reason', 'reference_role', 'coordinate_status', 'unresolved_paths')},
                         'targets': target, 'origins': r.get('origins', [])})
    refs.sort(key=encode)
    articles = article_projection(root)
    supplementary = {tag: hashlib.sha256(ET.tostring(root.find(tag), encoding='utf-8')).hexdigest()
                     if root.find(tag) is not None else None for tag in ('부칙', '별표')}
    value = {'version': version, 'raw_sha256': item['sha256'], 'articles': articles, 'references': refs,
             'supplementary_xml_hashes': supplementary, 'counts': {'articles': len(articles),
             'nodes': len(data['nodes']), 'blocks': len(data['blocks']), 'body_references': len(refs),
             'body_unresolved': sum(r['resolution']=='UNRESOLVED' for r in refs),
             'excluded_supplementary_references': excluded}, 'navigation_manifest': nav}
    save(folder / 'canonical.json', value)
    return value

def plan(old, new):
    a, b = old['articles'], new['articles']
    common = a.keys() & b.keys()
    same = {k for k in common if a[k] == b[k]}
    changed = common - same
    added, removed = b.keys() - a.keys(), a.keys() - b.keys()
    incoming = []
    for r in old['references']:
        hit = sorted({t['article'] for t in r['targets']} & (changed | removed))
        if hit:
            incoming.append({'source_article': r['source_article'], 'mention': r['mention_text'],
                             'targets': hit, 'source_changed': r['source_article'] in changed,
                             'status': 'REVIEW_NEEDED', 'old_reference_sha256': digest(r)})
    rebuild = changed | added | removed | {r['source_article'] for r in incoming}
    # New targets can resolve old DATA_GAP references; conservative scope.
    if added:
        rebuild |= {r['source_article'] for r in old['references'] if r['resolution']=='UNRESOLVED'}
    # Document-wide alias changes cannot be handled as a purely local edit.
    from semantic_runtime.term_references import declared_aliases
    old_aliases = declared_aliases([{'text': r['source_text']} for r in old['references']])
    new_aliases = declared_aliases([{'text': r['source_text']} for r in new['references']])
    aliases_changed = old_aliases != new_aliases
    if aliases_changed:
        rebuild |= set(a) | set(b)
    reused = [r for r in old['references'] if r['source_article'] not in rebuild]
    rebuilt = [r for r in new['references'] if r['source_article'] in rebuild]
    delta_refs = sorted(reused + rebuilt, key=encode)
    # This uses full native output for affected reference sources. It proves
    # delta selection/application equivalence, not incremental compiler speed.
    result = {'old': old['version'], 'new': new['version'], 'old_hash': digest(a), 'new_hash': digest(b),
              'unchanged': sorted(same), 'changed': sorted(changed), 'added': sorted(added), 'removed': sorted(removed),
              'incoming_review': incoming, 'reference_rebuild_sources': sorted(rebuild),
              'reference_rows_reused': len(reused), 'reference_rows_rebuilt': len(rebuilt),
              'reference_projection_equal': delta_refs == new['references'],
              'aliases_changed': aliases_changed,
              'supplementary_changed': [k for k in old['supplementary_xml_hashes']
                  if old['supplementary_xml_hashes'][k] != new['supplementary_xml_hashes'][k]],
              'reference_delta_method': 'Full native new compilation then affected-source projection; compiler optimization NOT tested'}
    return result, delta_refs

def populate(db, value):
    version = value['version']
    for coord, payload in value['articles'].items():
        h = digest(payload)
        db.execute('INSERT OR IGNORE INTO payload VALUES(?,?)', (h, encode(payload)))
        db.execute('INSERT INTO article VALUES(?,?,?)', (version, coord, h))
    for i, r in enumerate(value['references']):
        db.execute('INSERT INTO ref VALUES(?,?,?)', (version, i, encode(r)))

def snapshot(db, version):
    return {c: json.loads(p) for c, p in db.execute('SELECT a.coordinate,p.json FROM article a JOIN payload p USING(hash) WHERE a.version=?', (version,))}

def apply_delta(db, old, new, change, refs, *, expected, fail_after=None):
    key = digest(change)
    receipt = db.execute('SELECT json FROM receipt WHERE id=?', (key,)).fetchone()
    if receipt:
        # Idempotent receipt is valid only while the committed output matches.
        if snapshot(db, new['version']) != new['articles']:
            raise ValueError('completed result drift')
        return {'reused_receipt': True, **json.loads(receipt[0])}
    head = db.execute('SELECT version FROM selected').fetchone()[0]
    if head != expected or digest(snapshot(db, old['version'])) != change['old_hash']:
        raise ValueError('stale selection or source hash')
    with db:
        for i, coord in enumerate(change['unchanged']):
            db.execute('INSERT INTO article SELECT ?,coordinate,hash FROM article WHERE version=? AND coordinate=?',
                       (new['version'], old['version'], coord))
            if fail_after is not None and i >= fail_after:
                raise RuntimeError('injected storage failure')
        for coord in change['changed'] + change['added']:
            payload = new['articles'][coord]
            h = digest(payload)
            db.execute('INSERT OR IGNORE INTO payload VALUES(?,?)', (h, encode(payload)))
            db.execute('INSERT INTO article VALUES(?,?,?)', (new['version'], coord, h))
        for i, r in enumerate(refs):
            db.execute('INSERT INTO ref VALUES(?,?,?)', (new['version'], i, encode(r)))
        if snapshot(db, new['version']) != new['articles'] or refs != new['references']:
            raise ValueError('canonical delta mismatch')
        receipt = {'id': key, 'old': old['version'], 'new': new['version'],
                   'articles_equal': True, 'references_equal': True}
        db.execute('INSERT INTO receipt VALUES(?,?)', (key, encode(receipt)))
        db.execute('UPDATE selected SET version=? WHERE version=?', (new['version'], expected))
    return receipt

def main():
    started = time.monotonic()
    if OUT.exists():
        raise ValueError('run already exists; inspect receipt or use separate documented attempt')
    OUT.mkdir(parents=True)
    dataset = json.loads((ADR / 'artifacts/dataset.json').read_text())
    empty = OUT / 'empty-terminology.sqlite'
    with sqlite3.connect(empty) as db:
        db.executescript('CREATE TABLE entry(id TEXT,label TEXT); CREATE TABLE corpus_definition(document_id TEXT);')
    versions = [build_native(item, empty) for item in dataset['versions']]
    db = sqlite3.connect(OUT / 'delta-demo.sqlite')
    db.executescript('''CREATE TABLE payload(hash TEXT PRIMARY KEY,json TEXT);
      CREATE TABLE article(version TEXT,coordinate TEXT,hash TEXT,PRIMARY KEY(version,coordinate));
      CREATE TABLE ref(version TEXT,ordinal INTEGER,json TEXT,PRIMARY KEY(version,ordinal));
      CREATE TABLE selected(version TEXT);
      CREATE TABLE receipt(id TEXT PRIMARY KEY,json TEXT);''')
    populate(db, versions[0])
    db.execute('INSERT INTO selected VALUES(?)', (versions[0]['version'],))
    db.commit()
    reports = []
    for old, new in zip(versions, versions[1:]):
        change, refs = plan(old, new)
        save(OUT / f'delta-{old["version"]}--{new["version"]}.json', change)
        checks = {}
        try:
            apply_delta(db, old, new, change, refs, expected='stale-version')
        except ValueError:
            checks['stale_rejected'] = True
        try:
            apply_delta(db, old, new, change, refs, expected=old['version'], fail_after=0)
        except RuntimeError:
            checks['transaction_rollback'] = (snapshot(db, new['version']) == {} and
                db.execute('SELECT version FROM selected').fetchone()[0] == old['version'])
        receipt = apply_delta(db, old, new, change, refs, expected=old['version'])
        checks['exact_reconstruction'] = snapshot(db, new['version']) == new['articles']
        checks['reference_reconstruction'] = refs == new['references']
        checks['idempotent_replay'] = apply_delta(db, old, new, change, refs, expected=old['version'])['reused_receipt']
        checks['old_snapshot_preserved'] = snapshot(db, old['version']) == old['articles']
        # Rollback changes selection, never deletes history; then return to new.
        with db:
            db.execute('UPDATE selected SET version=?', (old['version'],))
        checks['rollback_read'] = snapshot(db, old['version']) == old['articles']
        with db:
            db.execute('UPDATE selected SET version=?', (new['version'],))
        examples = []
        for coord in change['changed']:
            def lines(v):
                def flatten(t):
                    return [t['heading'], *t['content'], *(x for c in t['children'] for x in flatten(c))]
                return flatten(v['articles'][coord]['tree'])
            examples.append({'article': coord, 'diff': list(difflib.unified_diff(lines(old), lines(new),
                fromfile=old['version'], tofile=new['version'], lineterm=''))})
        save(OUT / f'text-changes-{old["version"]}--{new["version"]}.json', examples)
        reports.append({'change': change, 'checks': checks, 'receipt': receipt})
    checks = [ok for report in reports for ok in report['checks'].values()]
    summary = {'status': 'PASS' if all(checks) else 'FAIL', 'checks_passed': sum(checks), 'checks_total': len(checks),
        'versions': [{'version': v['version'], **v['counts']} for v in versions], 'transitions': reports,
        'payloads_stored': db.execute('SELECT count(*) FROM payload').fetchone()[0],
        'version_article_bindings': db.execute('SELECT count(*) FROM article').fetchone()[0],
        'seconds': round(time.monotonic()-started,3),
        'max_rss_mib': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2),
        'limitations': ['Single public law, two real transitions; not a corpus quality test.',
            'Native XML structure and explicit body references only. Empty terminology catalogue; glossary/meaning/Wiki reuse not certified.',
            'Supplementary clauses and annex XML hash changes separately recorded. External annex binaries not fetched.',
            'Affected reference rows taken from full native rebuild; no incremental compiler performance claim.',
            'Physical source IDs and span IDs stay version-specific. Canonical equality does not permit copying old physical IDs.',
            'SQLite here is an isolated batch demonstration. Oracle/Dataiku/GENOS deployment not performed.'],
        'llm_calls': 0, 'active_main_modified': False}
    db.close()
    save(OUT / 'result.json', summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='transitions'},ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
