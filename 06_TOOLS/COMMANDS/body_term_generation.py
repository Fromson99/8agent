"""Derive a navigation generation where every official MOLEG term can reach our text.

본문용어 = a term label that occurs in our articles. Starting from a literal-match
generation (never modified), this keeps a (term, article) link when the label occurs
as either
  - a morpheme-aligned noun span (term_morph.aligned_spans), or
  - a phrase label (대통령령으로 정하는 경우) on word start + morpheme end
    (term_morph.phrase_spans),
and adds, from an official MOLEG collection snapshot:
  - every 법제처 법령용어목록 term not yet in the index, matched the same way;
  - every 법제처 일상용어목록 term that an official relation points to;
  - moleg_detail: 법령정의사전·법령한영사전·법령용어사전 records per term;
  - moleg_relation: every 지식용어→일상용어 relation collected so far;
  - occurrence_span: where each kept link sits in the article (up to 3 spans).

usage: body_term_generation.py --source GEN --collection DIR --output NEW_GEN [--report DIR]
"""
import argparse, collections, hashlib, json, multiprocessing as mp, os, shutil, sqlite3, sys, time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM/WORKSPACE.json').is_file())
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from semantic_runtime import term_morph  # noqa: E402

PHRASE_SOURCES = ('moleg:legal_terms:', 'moleg:knowledge_terms:', 'corpus-definition:', 'econedu:', 'nts:')
MAX_SPANS = 3
_KEYS = _PREFIXES = None


def sha(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def _init(keys, prefixes):
    global _KEYS, _PREFIXES
    _KEYS, _PREFIXES = keys, prefixes


def _scan(item):
    sid, text = item
    text = text or ''
    spans = term_morph.aligned_spans(text, _KEYS)
    for key, found in term_morph.phrase_spans(text, _PREFIXES).items():
        spans.setdefault(key, set()).update(found)
    return sid, {k: sorted(v)[:MAX_SPANS] for k, v in spans.items()}


def _phrase(item):
    return item[0], term_morph.phrase_label(item[1])


def link_tree(src, dst):
    for dirpath, _, files in os.walk(src):
        target = dst / Path(dirpath).relative_to(src)
        target.mkdir(parents=True, exist_ok=True)
        for name in files:
            os.link(Path(dirpath) / name, target / name)


def term_json(tid, label):
    return json.dumps({'id': tid, 'label': label, 'source': 'moleg', 'node_id': tid,
                       'status': 'SOURCE_TERM_NOT_CANONICAL_MEANING', 'canonical_approval': False},
                      ensure_ascii=False)


def official(collection, db, known):
    """Copy the collected official records into the index; add missing terms."""
    col = sqlite3.connect(collection / 'collection.sqlite')
    catalogue = {i: json.loads(p) for i, p in col.execute('SELECT id,payload FROM catalogue')}
    by_mst = {}
    for tid, row in catalogue.items():
        if row['entity_type'] == 'everyday_terms':
            by_mst[row['source_id']] = tid
    db.executescript('''
      CREATE TABLE moleg_detail(term_id TEXT,seq TEXT,kind TEXT,kind_name TEXT,label_key TEXT,
        text TEXT,fields TEXT,request_id TEXT,response_sha256 TEXT,PRIMARY KEY(term_id,seq,kind));
      CREATE INDEX moleg_detail_label ON moleg_detail(label_key);
      CREATE TABLE moleg_relation(source_id TEXT,target_id TEXT,code TEXT,label TEXT,request_id TEXT,
        PRIMARY KEY(source_id,target_id,code));
      CREATE INDEX moleg_relation_target ON moleg_relation(target_id);''')
    details, seq_terms = {}, collections.defaultdict(list)
    for tid, row in catalogue.items():
        if row['entity_type'] == 'legal_terms':
            for seq in row['source_id'].split(','):
                seq_terms[seq.strip()].append(tid)
    added = collections.Counter()
    for endpoint, raw, rid, digest in col.execute(
            "SELECT endpoint,records,id,response_sha256 FROM request WHERE status='complete'"):
        for rec in json.loads(raw or '[]'):
            f = rec.get('fields', {})
            if endpoint == 'legal_term_detail':
                seq = str(f.get('법령용어일련번호') or rec.get('source_id'))
                for tid in seq_terms.get(seq, []):
                    details[(tid, seq, f.get('법령용어코드', ''))] = (
                        f.get('법령용어코드명', ''), term_morph.fold(catalogue[tid]['label']),
                        rec.get('definition') or f.get('법령용어정의', ''),
                        json.dumps(f, ensure_ascii=False), rid, digest)
            elif endpoint == 'legal_term_relations':
                src = 'moleg:knowledge_terms:' + rec['_request']['MST']
                target = by_mst.get(str(rec.get('source_id')))
                if target is None:
                    added['relation_target_missing'] += 1
                    continue
                db.execute('INSERT OR IGNORE INTO moleg_relation VALUES (?,?,?,?,?)',
                           (src, target, f.get('용어관계코드', ''), f.get('용어관계', ''), rid))
    db.executemany('INSERT OR REPLACE INTO moleg_detail VALUES (?,?,?,?,?,?,?,?,?)',
                   [k + v for k, v in details.items()])
    targets = {r[0] for r in db.execute('SELECT DISTINCT target_id FROM moleg_relation')}
    new_terms = []
    for tid, row in catalogue.items():
        kind = row['entity_type']
        if tid in known or kind == 'knowledge_terms' or (kind == 'everyday_terms' and tid not in targets):
            continue
        if kind == 'legal_terms' and row['label'].isascii():
            added['legal_terms_english_headword_skipped'] += 1  # 법령한영사전 English headwords
            continue
        new_terms.append((tid, row['label']))
        added[kind] += 1
    db.executemany('INSERT INTO term(id,json) VALUES (?,?)', [(t, term_json(t, l)) for t, l in new_terms])
    db.executemany('INSERT OR IGNORE INTO term_surface VALUES (?,?,?,?)',
                   [(t, term_morph.fold(l), l, 'SOURCE_LABEL') for t, l in new_terms])
    added['moleg_detail'] = len(details)
    added['moleg_relation'] = db.execute('SELECT count(*) FROM moleg_relation').fetchone()[0]
    return [t for t, _ in new_terms if t.startswith('moleg:legal_terms:')], dict(added)


def collection_status(folder):
    col = sqlite3.connect(folder / 'collection.sqlite')
    return {e: dict(col.execute('SELECT status,count(*) FROM request WHERE endpoint=? GROUP BY 1', (e,)).fetchall())
            for e, in col.execute('SELECT DISTINCT endpoint FROM request')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--collection', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--report', type=Path)
    ap.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()
    src, out = a.source.resolve(), a.output.resolve()
    if out.exists():
        raise SystemExit('output generation already exists: ' + str(out))
    t0 = time.time()
    root_manifest = json.loads((src / 'manifest.json').read_text())
    nav_binding = root_manifest['navigation']
    if sha(src / nav_binding['path'] / 'manifest.json') != nav_binding['manifest_sha256']:
        raise SystemExit('source navigation manifest drift')
    out.mkdir(parents=True)
    os.link(src / 'store.sqlite', out / 'store.sqlite')
    link_tree(src / 'glossary', out / 'glossary')
    nav_out = out / nav_binding['path']
    nav_out.mkdir()
    shutil.copyfile(src / nav_binding['path'] / 'navigation.sqlite', nav_out / 'navigation.sqlite')
    db = sqlite3.connect(nav_out / 'navigation.sqlite')
    known = {r[0] for r in db.execute('SELECT id FROM term')}
    new_legal, added = official(a.collection.resolve(), db, known)
    db.commit()
    print('official', added, round(time.time() - t0), 's', flush=True)

    labels, term_keys = {}, collections.defaultdict(set)
    for tid, raw in db.execute('SELECT id,json FROM term'):
        labels[tid] = json.loads(raw).get('label') or ''
        term_keys[tid].add(term_morph.fold(labels[tid]))
    for tid, key, text in db.execute('SELECT term_id,key,text FROM term_surface'):
        term_keys[tid].update({term_morph.fold(key or ''), term_morph.fold(text or '')})
    candidates = sorted({(t, labels[t]) for t in labels if t.startswith(PHRASE_SOURCES)})
    with mp.get_context('fork').Pool(a.workers) as pool:
        phrase_terms = {t for t, ok in pool.imap_unordered(_phrase, candidates, chunksize=500) if ok}
    phrase_keys = {term_morph.fold(labels[t]) for t in phrase_terms}
    prefixes = collections.defaultdict(list)
    for key in phrase_keys:
        prefixes[key[:2]].append(key)
    all_keys = frozenset(k for ks in term_keys.values() for k in ks if len(k) >= 2)
    key_terms = collections.defaultdict(set)
    for tid in new_legal:
        for k in term_keys[tid]:
            key_terms[k].add(tid)
    print('phrase terms', len(phrase_terms), 'keys', len(all_keys), round(time.time() - t0), 's', flush=True)

    sources = db.execute("SELECT id,json_extract(json,'$.text') FROM source").fetchall()
    found = {}
    with mp.get_context('fork').Pool(a.workers, initializer=_init, initargs=(all_keys, dict(prefixes))) as pool:
        for n, (sid, spans) in enumerate(pool.imap_unordered(_scan, sources, chunksize=32), 1):
            found[sid] = spans
            if n % 5000 == 0:
                print('analysed', n, round(time.time() - t0), 's', flush=True)

    db.execute('CREATE TABLE occurrence_span(term_id TEXT,source_id TEXT,start INTEGER,end INTEGER,'
               'PRIMARY KEY(term_id,source_id,start,end)) WITHOUT ROWID')
    db.execute('CREATE TEMP TABLE rejected(term_id TEXT,source_id TEXT,PRIMARY KEY(term_id,source_id)) WITHOUT ROWID')
    kept = removed = phrase_kept = 0
    spans, batch = [], []

    def keep(tid, sid):
        hit = False
        for k in term_keys.get(tid, ()):
            for s, e in found.get(sid, {}).get(k, ()):
                spans.append((tid, sid, s, e))
                hit = True
        return hit

    for tid, sid in db.execute('SELECT term_id,source_id FROM occurrence').fetchall():
        if keep(tid, sid):
            kept += 1
            phrase_kept += tid in phrase_terms
        else:
            removed += 1
            batch.append((tid, sid))
    db.executemany('INSERT INTO rejected VALUES (?,?)', batch)
    new_pairs = set()
    for sid, keys in found.items():
        for k in keys:
            for tid in key_terms.get(k, ()):
                new_pairs.add((tid, sid))
    for tid, sid in new_pairs:
        keep(tid, sid)
    deleted = {}
    for table in ('occurrence', 'occurrence_origin', 'occurrence_evidence'):
        deleted[table] = db.execute('DELETE FROM ' + table + ' WHERE (term_id,source_id) IN '
                                    '(SELECT term_id,source_id FROM rejected)').rowcount
    db.executemany('INSERT OR IGNORE INTO occurrence VALUES (?,?)', sorted(new_pairs))
    db.executemany("INSERT OR IGNORE INTO occurrence_origin VALUES (?,?,'BODY_TERM_MATCH')", sorted(new_pairs))
    db.executemany('INSERT OR IGNORE INTO occurrence_span VALUES (?,?,?,?)', spans)
    db.execute('CREATE INDEX occurrence_span_source ON occurrence_span(source_id)')
    db.execute('DROP TABLE term_stats')
    db.execute('CREATE TABLE term_stats AS SELECT term_id,count(*) AS n FROM occurrence GROUP BY term_id')
    db.execute('CREATE UNIQUE INDEX term_stats_id ON term_stats(term_id)')
    db.commit()
    total = db.execute('SELECT count(*) FROM occurrence').fetchone()[0]
    linked_terms = db.execute('SELECT count(*) FROM term_stats').fetchone()[0]
    db.close()

    nav_manifest = json.loads((src / nav_binding['path'] / 'manifest.json').read_text())
    before, parent_sha = nav_manifest['counts']['occurrence'], nav_manifest.get('index_sha256')
    nav_manifest['counts']['occurrence'] = total
    nav_manifest['index_sha256'] = sha(nav_out / 'navigation.sqlite')
    nav_manifest['body_term_filter'] = {
        'parent_index_sha256': parent_sha,
        'parent_manifest_sha256': nav_binding['manifest_sha256'],
        'rule': 'keep (term, article) if a label is a morpheme-aligned noun span or a phrase label on '
                'word start + morpheme end; add unindexed MOLEG legal terms by the same rule',
        'term_morph_sha256': sha(term_morph.__file__), 'pecab': term_morph.installed_version(),
        # The collection may still be growing; its records are copied into this index.
        'collection': str(a.collection), 'collection_status': collection_status(a.collection),
        'official': added, 'occurrence_before': before, 'occurrence_after': total,
        'phrase_terms': len(phrase_terms), 'phrase_links_kept': phrase_kept,
        'new_legal_links': len(new_pairs), 'deleted': deleted, 'linked_terms_after': linked_terms}
    (nav_out / 'manifest.json').write_text(json.dumps(nav_manifest, ensure_ascii=False, indent=2) + '\n')
    root_manifest['navigation'] = {'path': nav_binding['path'], 'manifest_sha256': sha(nav_out / 'manifest.json')}
    (out / 'manifest.json').write_text(json.dumps(root_manifest, ensure_ascii=False, indent=2) + '\n')
    report = {'seconds': round(time.time() - t0), **nav_manifest['body_term_filter'], 'kept': kept, 'removed': removed}
    if a.report:
        a.report.mkdir(parents=True, exist_ok=True)
        (a.report / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
