"""Morpheme full-text ranking over the articles of one navigation generation.

Reverse matching (navigation_match) says *which* articles relate to a question and how;
this index only says *which to read first*, and gives the controller a path when no
registered surface matched. Articles and questions are cut into PeCab content morphemes
(nouns, roots, foreign/hanja/number tokens, verb and adjective stems); a question is an
OR of its morphemes ranked by BM25 with the heading weighted over the body.

The index is a separate build product next to navigation.sqlite, bound to the source
store and the PeCab version, so serving refuses a stale or foreign file.
"""
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
from multiprocessing import get_context
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
import unicodedata
from . import term_morph
from . import observability as obs

_SERVING_CACHE = {}
_SERVING_LOCK = threading.Lock()

SCHEMA = 'semantic-fulltext-v2'
TAGS = ('NNG', 'NNP', 'NNB', 'NR', 'XR', 'SL', 'SH', 'SN', 'VV', 'VA')
HEADING_WEIGHT = 10.0
MAX_TERMS = 32
INDEX_CHUNK_CHARS = 256
INDEX_BATCH_SIZE = 128


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def tokenizer_version():
    return term_morph.installed_version()


def forms(tokens):
    return [t.form for t in tokens if t.tag in TAGS]


def question_terms(text):
    """Distinct content morphemes of a question or model query, in order of appearance."""
    tokens = term_morph.tokenize(unicodedata.normalize('NFKC', text))
    return list(dict.fromkeys(forms(tokens)))[:MAX_TERMS]


def _index_chunks(text):
    """Keep PeCab inputs bounded without splitting ordinary words."""
    start = 0
    while start < len(text):
        end = min(start + INDEX_CHUNK_CHARS, len(text))
        if end < len(text):
            breaks = (text.rfind(' ', start, end), text.rfind('\n', start, end),
                      text.rfind('\t', start, end))
            boundary = max(breaks)
            if boundary >= start + INDEX_CHUNK_CHARS // 2:
                end = boundary + 1
        yield text[start:end]
        start = end


def _search_forms(text):
    return ' '.join(form for chunk in _index_chunks(text)
                    for form in forms(term_morph.tokenize(chunk)))


def expression(terms):
    return ' OR '.join('"'+t.replace('"', '')+'"' for t in terms)


def build(navigation, output, workers=2):
    """navigation/ (manifest.json + navigation.sqlite) -> output/ (manifest.json + fulltext.sqlite)."""
    if workers < 1:
        raise ValueError('workers must be positive')
    navigation, output = Path(navigation), Path(output)
    nav_manifest = json.loads((navigation/'manifest.json').read_text())
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    src = sqlite3.connect('file:'+str(navigation/'navigation.sqlite')+'?mode=ro', uri=True)
    db = sqlite3.connect(output/'fulltext.sqlite')
    count = 0
    try:
        db.execute('CREATE VIRTUAL TABLE source_fts USING fts5(source_id UNINDEXED,heading,body,tokenize="unicode61")')
        cursor = src.execute('SELECT id,json FROM source ORDER BY id')
        with (ProcessPoolExecutor(max_workers=workers, mp_context=get_context('spawn'))
              if workers > 1 else nullcontext()) as pool:
            while batch := cursor.fetchmany(INDEX_BATCH_SIZE):
                part = []
                for sid, raw in batch:
                    record = json.loads(raw)
                    part.append((sid, unicodedata.normalize('NFKC', record.get('heading') or ''),
                                 unicodedata.normalize('NFKC', record.get('text') or '')))
                mapper = pool.map if pool else map
                heads = mapper(_search_forms, (h for _, h, _ in part))
                bodies = mapper(_search_forms, (b for _, _, b in part))
                db.executemany('INSERT INTO source_fts VALUES(?,?,?)',
                               ((sid, h, b) for (sid, _, _), h, b in zip(part, heads, bodies)))
                count += len(part)
                db.commit()
                print(f'FULLTEXT build indexed_sources={count} elapsed={time.monotonic()-started:.1f}s', flush=True)
        db.execute("INSERT INTO source_fts(source_fts) VALUES('optimize')")
        db.commit()
    finally:
        db.close()
        src.close()
    manifest = {'schema_version': SCHEMA, 'generation_id': nav_manifest['generation_id'],
                'source_store_sha256': nav_manifest['source_store_sha256'],
                'navigation_index_sha256': nav_manifest['index_sha256'],
                'tokenizer': {'name': 'pecab', 'version': tokenizer_version(), 'tags': list(TAGS),
                              'fts5': 'unicode61 over space-joined morphemes'},
                'ranking': {'bm25_weights': {'heading': HEADING_WEIGHT, 'body': 1.0}, 'query': 'OR of question morphemes'},
                'counts': {'source': count}, 'fulltext_sha256': sha(output/'fulltext.sqlite'),
                'builder_sha256': sha(__file__), 'build_seconds': round(time.monotonic()-started, 1)}
    (output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return manifest


class FulltextIndex:
    """Read-only ranked search; verified once against the serving navigation index."""
    def __init__(self, path, navigation_manifest):
        path = Path(path)
        self.manifest = m = json.loads((path/'manifest.json').read_text())
        if m.get('schema_version') != SCHEMA:
            raise ValueError('unsupported fulltext index schema')
        if (m['source_store_sha256'] != navigation_manifest['source_store_sha256']
                or m['navigation_index_sha256'] != navigation_manifest['index_sha256']):
            raise ValueError('fulltext index generation mismatch')
        if (m['tokenizer'].get('name') != 'pecab' or
                m['tokenizer'].get('version') != tokenizer_version() or
                m['tokenizer'].get('tags') != list(TAGS)):
            raise ValueError('fulltext tokenizer mismatch')
        if m['fulltext_sha256'] != sha(path/'fulltext.sqlite'):
            raise ValueError('fulltext index hash mismatch')
        self.path = path

    def connect(self):
        return sqlite3.connect('file:'+str(self.path/'fulltext.sqlite')+'?mode=ro', uri=True, check_same_thread=False)

    def rank(self, db, terms, allowed=None, limit=None):
        """Source IDs by BM25 over the OR of terms; `allowed` filters to the request scope."""
        if not terms or allowed is not None and not allowed:
            return []
        weights = self.manifest['ranking']['bm25_weights']
        # FTS5 can produce rows in rank order without the temporary sort used
        # by ORDER BY bm25(...). Keep the previous source_id tie break below.
        rank = f"bm25(0,{float(weights['heading'])},{float(weights['body'])})"
        sql = ('SELECT source_id,rank FROM source_fts WHERE source_fts MATCH ? '
               'AND rank MATCH ? ORDER BY rank')
        out = []
        tied = []
        previous_score = None
        metrics={'sql_execute_ms':0.0,'sql_first_row_ms':0.0,'sql_fetch_ms':0.0,
                 'scope_filter_ms':0.0,'fetched_count':0,'selected_count':0}
        cpu_before=obs.cpu_pressure();cursor=None
        def rows():
            t=time.perf_counter();first=cursor.fetchone()
            metrics['sql_first_row_ms']+=(time.perf_counter()-t)*1000
            if first is not None:
                metrics['fetched_count']+=1;yield first
            while True:
                t=time.perf_counter();batch=cursor.fetchmany(256)
                metrics['sql_fetch_ms']+=(time.perf_counter()-t)*1000
                metrics['fetched_count']+=len(batch)
                if not batch:return
                yield from batch
        try:
            t=time.perf_counter();cursor=db.execute(sql,(expression(terms),rank))
            metrics['sql_execute_ms']=(time.perf_counter()-t)*1000
            for sid,score in rows():
                if tied and score!=previous_score:
                    t=time.perf_counter()
                    out.extend(s for s in sorted(tied) if allowed is None or s in allowed)
                    metrics['scope_filter_ms']+=(time.perf_counter()-t)*1000
                    if limit and len(out)>=limit:return out[:limit]
                    tied=[]
                tied.append(sid);previous_score=score
            t=time.perf_counter()
            out.extend(s for s in sorted(tied) if allowed is None or s in allowed)
            metrics['scope_filter_ms']+=(time.perf_counter()-t)*1000
            return out[:limit] if limit else out
        finally:
            if cursor is not None:cursor.close()
            metrics['selected_count']=min(len(out),limit) if limit else len(out)
            cpu_after=obs.cpu_pressure()
            delta={k:cpu_after[k]-v for k,v in cpu_before.items() if k in cpu_after}
            obs.event(obs.get_logger('fulltext'),'fulltext.sql.timings',
                      **{k:round(v,3) if isinstance(v,float) else v for k,v in metrics.items()},
                      cpu_throttled_usec_delta=delta.get('throttled_usec'),
                      cpu_nr_throttled_delta=delta.get('nr_throttled'))


def open_bound(generation, binding, navigation_manifest):
    """Config binding {path, manifest_sha256} relative to the generation directory."""
    root = Path(generation).resolve()
    path = (root/binding['path']).resolve()
    path.relative_to(root)
    if sha(path/'manifest.json') != binding['manifest_sha256']:
        raise ValueError('fulltext manifest mismatch')
    return FulltextIndex(path, navigation_manifest)


def cached_open_bound(generation, binding, navigation_manifest):
    """Reuse verified immutable metadata; never share request SQLite connections.

    FulltextIndex/open_bound remain uncached for deployment integrity gates.
    Path, file state, expected pins and tokenizer version all bind a cache entry.
    """
    root = Path(generation).resolve()
    path = (root / binding['path']).resolve()
    path.relative_to(root)

    def signature():
        result = []
        for name in ('manifest.json', 'fulltext.sqlite'):
            file = path / name
            if file.is_symlink() or Path(str(file) + '-wal').exists():
                raise ValueError('unbound fulltext file')
            stat = file.stat()
            result.append((stat.st_dev, stat.st_ino, stat.st_size,
                           stat.st_mtime_ns, stat.st_ctime_ns))
        return tuple(result)

    before = signature()
    key = (str(path), before, binding['manifest_sha256'],
           navigation_manifest['index_sha256'], navigation_manifest['source_store_sha256'],
           tokenizer_version(), tuple(TAGS), SCHEMA)
    with _SERVING_LOCK:
        cached = _SERVING_CACHE.get(key)
        if cached is not None:
            obs.event(obs.get_logger('fulltext'), 'fulltext.cached')
            return cached
        with obs.step(obs.get_logger('fulltext'), 'fulltext.verify'):
            cached = open_bound(root, binding, navigation_manifest)
        if signature() != before:
            raise ValueError('fulltext changed during verification')
        _SERVING_CACHE.clear()
        _SERVING_CACHE[key] = cached
        return cached
