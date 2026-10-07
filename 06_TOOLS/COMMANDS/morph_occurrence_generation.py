"""Derive a new navigation generation whose term-article links respect morphemes.

The source generation is never modified. The new generation hard-links the store and
glossary, copies navigation.sqlite, and keeps a (term, article) link only when one of
the term's labels occurs in that article as a morpheme-aligned noun span
(semantic_runtime.term_morph). Literal fragments such as 조의 (제3조의2), 하기
(하기 위하여) and 하나 (어느 하나에) lose their links; references, definitions and
every other table are carried over unchanged.

usage: morph_occurrence_generation.py --source GEN_DIR --output NEW_GEN_DIR [--report DIR]
"""
import argparse, collections, hashlib, json, multiprocessing as mp, os, shutil, sqlite3, sys, time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM/WORKSPACE.json').is_file())
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from semantic_runtime import term_morph  # noqa: E402

_KEYS = None


def sha(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def _init(keys):
    global _KEYS
    _KEYS = keys


def _scan(item):
    sid, text = item
    return sid, term_morph.aligned_keys(text or '') & _KEYS


def link_tree(src, dst):
    for dirpath, _, files in os.walk(src):
        target = dst / Path(dirpath).relative_to(src)
        target.mkdir(parents=True, exist_ok=True)
        for name in files:
            os.link(Path(dirpath) / name, target / name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
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
    print('copied', round(time.time() - t0), 's', flush=True)

    db = sqlite3.connect(nav_out / 'navigation.sqlite')
    term_keys = collections.defaultdict(set)
    labels = {}
    for tid, raw in db.execute('SELECT id,json FROM term'):
        label = json.loads(raw).get('label') or ''
        labels[tid] = label
        term_keys[tid].add(term_morph.fold(label))
    for tid, key, text in db.execute('SELECT term_id,key,text FROM term_surface'):
        term_keys[tid].update({term_morph.fold(key or ''), term_morph.fold(text or '')})
    all_keys = frozenset(k for ks in term_keys.values() for k in ks if len(k) >= 2)
    sources = db.execute("SELECT id,json_extract(json,'$.text') FROM source").fetchall()
    print('terms', len(term_keys), 'keys', len(all_keys), 'articles', len(sources), flush=True)

    aligned = {}
    with mp.get_context('fork').Pool(a.workers, initializer=_init, initargs=(all_keys,)) as pool:
        for n, (sid, keys) in enumerate(pool.imap_unordered(_scan, sources, chunksize=64), 1):
            aligned[sid] = keys
            if n % 5000 == 0:
                print('analysed', n, round(time.time() - t0), 's', flush=True)

    db.execute('CREATE TEMP TABLE rejected(term_id TEXT, source_id TEXT, PRIMARY KEY(term_id, source_id)) WITHOUT ROWID')
    kept = removed = 0
    removed_by_term = collections.Counter()
    batch = []
    for tid, sid in db.execute('SELECT term_id,source_id FROM occurrence'):
        if term_keys.get(tid, set()) & aligned.get(sid, set()):
            kept += 1
            continue
        removed += 1
        removed_by_term[tid] += 1
        batch.append((tid, sid))
        if len(batch) >= 200000:
            db.executemany('INSERT INTO rejected VALUES (?,?)', batch); batch = []
    if batch:
        db.executemany('INSERT INTO rejected VALUES (?,?)', batch)
    print('kept', kept, 'removed', removed, round(time.time() - t0), 's', flush=True)

    deleted = {}
    for table in ('occurrence', 'occurrence_origin', 'occurrence_evidence'):
        cur = db.execute('DELETE FROM ' + table + ' WHERE (term_id,source_id) IN (SELECT term_id,source_id FROM rejected)')
        deleted[table] = cur.rowcount
        print('deleted', table, cur.rowcount, round(time.time() - t0), 's', flush=True)
    db.execute('DROP TABLE term_stats')
    db.execute('CREATE TABLE term_stats AS SELECT term_id,count(*) AS n FROM occurrence GROUP BY term_id')
    db.execute('CREATE UNIQUE INDEX term_stats_id ON term_stats(term_id)')
    db.commit()
    linked_terms = db.execute('SELECT count(*) FROM term_stats').fetchone()[0]
    probe = {w: db.execute('SELECT coalesce(sum(s.n),0) FROM term t JOIN term_stats s ON s.term_id=t.id '
                           "WHERE json_extract(t.json,'$.label')=?", (w,)).fetchone()[0]
             for w in ('하나', '경우', '조의', '호의', '하기', '항의', '대주', '담보', '금지행위', '투자권유대행인')}
    db.close()

    nav_manifest = json.loads((src / nav_binding['path'] / 'manifest.json').read_text())
    before = nav_manifest['counts']['occurrence']
    nav_manifest['counts']['occurrence'] = kept
    nav_manifest['index_sha256'] = sha(nav_out / 'navigation.sqlite')
    nav_manifest['morph_filter'] = {
        'parent_index_sha256': json.loads((src / nav_binding['path'] / 'manifest.json').read_text())['index_sha256'],
        'parent_manifest_sha256': nav_binding['manifest_sha256'],
        'rule': 'keep (term, article) only if a term label is a morpheme-aligned noun span of the article',
        'term_morph_sha256': sha(term_morph.__file__),
        'pecab': term_morph.installed_version(),
        'top_n': term_morph.TOP_N, 'margin': term_morph.MARGIN,
        'occurrence_before': before, 'occurrence_after': kept, 'deleted': deleted,
        'linked_terms_after': linked_terms}
    (nav_out / 'manifest.json').write_text(json.dumps(nav_manifest, ensure_ascii=False, indent=2) + '\n')
    root_manifest['navigation'] = {'path': nav_binding['path'], 'manifest_sha256': sha(nav_out / 'manifest.json')}
    (out / 'manifest.json').write_text(json.dumps(root_manifest, ensure_ascii=False, indent=2) + '\n')

    report = {'source': str(src.relative_to(ROOT)), 'output': str(out.relative_to(ROOT)),
              'seconds': round(time.time() - t0), 'occurrence_before': before, 'occurrence_after': kept,
              'removed': removed, 'deleted': deleted, 'linked_terms_after': linked_terms, 'probe_links_after': probe,
              'most_removed': [(labels.get(t, t), n) for t, n in removed_by_term.most_common(80)],
              'navigation_manifest_sha256': root_manifest['navigation']['manifest_sha256']}
    if a.report:
        a.report.mkdir(parents=True, exist_ok=True)
        (a.report / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != 'most_removed'}, ensure_ascii=False, indent=1))
    print('most removed:', report['most_removed'][:40])


if __name__ == '__main__':
    main()
