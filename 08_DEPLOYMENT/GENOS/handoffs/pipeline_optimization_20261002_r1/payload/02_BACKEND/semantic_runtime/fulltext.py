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
import os
import uuid
from . import term_morph
from . import observability as obs

_SERVING_CACHE = {}
_SERVING_LOCK = threading.Lock()
_SEARCH_LOCK = threading.Lock()
_ACTIVE_SEARCHES = {}
DIAGNOSTIC_REVISION = 'fulltext-diagnostics-20260928-r1'

SCHEMA = 'semantic-fulltext-v2'
TAGS = ('NNG', 'NNP', 'NNB', 'NR', 'XR', 'SL', 'SH', 'SN', 'VV', 'VA')
HEADING_WEIGHT = 10.0
MAX_TERMS = 32
INDEX_CHUNK_CHARS = 256
INDEX_BATCH_SIZE = 128


def thread_snapshot():
    """Optional calling-thread counters; never equate read_bytes with NFS traffic.

    schedstat runqueue wait excludes blocked I/O and GIL/lock waits. Missing
    kernel counters remain absent, so unsupported measurements are not zero.
    """
    counters = {}
    for name in ('io', 'schedstat'):
        try:
            raw = (Path('/proc/thread-self') / name).read_text()
            if name == 'io':
                values = dict(line.split(':', 1) for line in raw.splitlines())
                for key in ('rchar', 'syscr', 'read_bytes'):
                    if key in values:
                        counters[key] = int(values[key])
            else:
                counters['scheduler_wait_ns'] = int(raw.split()[1])
        except (OSError, ValueError, IndexError):
            pass
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_THREAD)
        counters.update(minor_faults=usage.ru_minflt, major_faults=usage.ru_majflt,
                        voluntary_switches=usage.ru_nvcsw, involuntary_switches=usage.ru_nivcsw)
    except (ImportError, AttributeError, OSError, ValueError):
        pass
    return {'wall': time.perf_counter(), 'cpu': time.thread_time(), 'counters': counters}


def thread_delta(before, after):
    elapsed = (after['wall'] - before['wall']) * 1000
    cpu = (after['cpu'] - before['cpu']) * 1000
    result = {'elapsed_ms': round(elapsed, 3), 'thread_cpu_ms': round(cpu, 3),
              'thread_non_cpu_ms': round(max(0, elapsed - cpu), 3)}
    names = {'rchar': 'thread_read_chars_delta', 'syscr': 'thread_read_syscalls_delta',
             'read_bytes': 'thread_read_bytes_delta', 'scheduler_wait_ns': 'scheduler_wait_ms',
             'minor_faults': 'minor_faults_delta', 'major_faults': 'major_faults_delta',
             'voluntary_switches': 'voluntary_switches_delta',
             'involuntary_switches': 'involuntary_switches_delta'}
    for key, name in names.items():
        if key in before['counters'] and key in after['counters']:
            value = after['counters'][key] - before['counters'][key]
            if value >= 0:
                result[name] = round(value / 1000000, 3) if key == 'scheduler_wait_ns' else value
    return result


def _begin_search():
    ident = uuid.uuid4().hex
    state = {}
    with _SEARCH_LOCK:
        _ACTIVE_SEARCHES[ident] = state
        active = len(_ACTIVE_SEARCHES)
        for value in _ACTIVE_SEARCHES.values():
            value['active_searches_peak'] = max(value.get('active_searches_peak', 0), active)
    return ident, active, state


def _finish_search(ident, state):
    with _SEARCH_LOCK:
        _ACTIVE_SEARCHES.pop(ident, None)
        return {'active_searches_at_finish': len(_ACTIVE_SEARCHES), **state}


def _connection_facts(db, manifest):
    """Read settings and a bounded query plan, without scanning the corpus."""
    facts = {'sqlite_version': sqlite3.sqlite_version,
             'indexed_source_count': manifest.get('counts', {}).get('source')}
    for name in ('page_size', 'cache_size', 'mmap_size', 'temp_store'):
        try:
            cursor = db.execute('PRAGMA ' + name)
            try:
                row = cursor.fetchone()
                facts[name] = row[0] if row else None
            finally:
                cursor.close()
        except sqlite3.Error:
            facts[name] = None
    try:
        cursor = db.execute('EXPLAIN QUERY PLAN SELECT source_id,rank FROM source_fts '
                            'WHERE source_fts MATCH ? AND rank MATCH ? ORDER BY rank',
                            ('"diagnostic"', 'bm25(0,10.0,1.0)'))
        try:
            plan = [str(row[3])[:256] for row in cursor.fetchmany(8)]
        finally:
            cursor.close()
        facts.update(query_plan=plan, uses_temp_sort=any('TEMP B-TREE' in line for line in plan))
    except sqlite3.Error:
        facts.update(query_plan=None, uses_temp_sort=None)
    return facts


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


def build(navigation, output, workers=2, *, document_ids=None):
    """navigation/ (manifest.json + navigation.sqlite) -> output/ (manifest.json + fulltext.sqlite)."""
    if workers < 1:
        raise ValueError('workers must be positive')
    navigation, output = Path(navigation), Path(output)
    nav_manifest = json.loads((navigation/'manifest.json').read_text())
    started = time.monotonic()
    src = sqlite3.connect('file:'+str(navigation/'navigation.sqlite')+'?mode=ro', uri=True)
    scope = None if document_ids is None else sorted(set(document_ids))
    if scope is not None:
        known = {r[0] for r in src.execute('SELECT DISTINCT document_id FROM source')}
        if not scope or set(scope)-known:
            src.close()
            raise ValueError('fulltext build scope must contain known document IDs')
    output.mkdir(parents=True, exist_ok=False)
    db = sqlite3.connect(output/'fulltext.sqlite')
    count = 0
    try:
        db.execute('CREATE VIRTUAL TABLE source_fts USING fts5(source_id UNINDEXED,heading,body,tokenize="unicode61")')
        cursor = src.execute('SELECT id,json FROM source ORDER BY id' if scope is None else
                             'SELECT id,json FROM source WHERE document_id IN ('+','.join('?' for _ in scope)+') ORDER BY id',
                             () if scope is None else scope)
        with (ProcessPoolExecutor(max_workers=workers, mp_context=get_context('spawn'))
              if workers > 1 else nullcontext()) as pool:
            while batch := cursor.fetchmany(INDEX_BATCH_SIZE):
                part = []
                for sid, raw in batch:
                    record = json.loads(raw)
                    part.append((sid, unicodedata.normalize('NFKC', record.get('heading') or ''),
                                 unicodedata.normalize('NFKC', record.get('text') or '')))
                def mapper(function, values):
                    return pool.map(function, values, chunksize=8) if pool else map(function, values)
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
    if scope is not None:
        manifest['scope'] = {'document_version_ids': scope, 'complete_navigation_corpus': False}
    (output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return manifest


class FulltextIndex:
    """Read-only ranked search; verified once against the serving navigation index."""
    indexed_scope_ids = None
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
        self.indexed_scope_ids = None
        if m.get('scope') is not None:
            scope = m['scope']
            if (not isinstance(scope, dict) or scope.get('complete_navigation_corpus') is not False or
                    not isinstance(scope.get('document_version_ids'), list) or not scope['document_version_ids']):
                raise ValueError('invalid partial fulltext scope')
            with sqlite3.connect('file:'+str(path/'fulltext.sqlite')+'?mode=ro', uri=True) as scoped:
                self.indexed_scope_ids = frozenset(r[0] for r in scoped.execute('SELECT source_id FROM source_fts'))
        try:
            self.diagnostic_file_bytes = (path/'fulltext.sqlite').stat().st_size
        except OSError:
            self.diagnostic_file_bytes = None

    def connect(self):
        started = time.perf_counter()
        db = sqlite3.connect('file:'+str(self.path/'fulltext.sqlite')+'?mode=ro', uri=True, check_same_thread=False)
        connect_ms = (time.perf_counter()-started)*1000
        try:
            started = time.perf_counter()
            facts = _connection_facts(db, self.manifest)
            obs.event(obs.get_logger('fulltext'), 'fulltext.connection.facts',
                      diagnostic_revision=DIAGNOSTIC_REVISION, process_id=os.getpid(),
                      index_bytes=getattr(self, 'diagnostic_file_bytes', None),
                      connect_ms=round(connect_ms, 3), facts_ms=round((time.perf_counter()-started)*1000, 3),
                      **facts)
            return db
        except BaseException:
            db.close()
            raise

    def rank(self, db, terms, allowed=None, limit=None):
        """Source IDs by BM25 over the OR of terms; `allowed` filters to the request scope."""
        if not terms or allowed is not None and not allowed:
            return []
        if self.indexed_scope_ids is not None and allowed is not None and set(allowed)-self.indexed_scope_ids:
            raise ValueError('requested search scope includes documents outside the rebuilt fulltext scope')
        weights = self.manifest['ranking']['bm25_weights']
        # FTS5 can produce rows in rank order without the temporary sort used
        # by ORDER BY bm25(...). Keep the previous source_id tie break below.
        rank = f"bm25(0,{float(weights['heading'])},{float(weights['body'])})"
        sql = ('SELECT source_id,rank FROM source_fts WHERE source_fts MATCH ? '
               'AND rank MATCH ? ORDER BY rank')
        out = []
        tied = []
        previous_score = None
        metrics={'sql_execute_ms':0.0,'sql_execute_cpu_ms':0.0,
                 'sql_first_row_ms':0.0,'sql_first_row_cpu_ms':0.0,
                 'sql_fetch_ms':0.0,'sql_fetch_cpu_ms':0.0,
                 'sql_fetch_batch_count':0,'sql_fetch_max_batch_ms':0.0,
                 'scope_filter_ms':0.0,'fetched_count':0,'selected_count':0}
        cpu_before=obs.cpu_pressure();before=thread_snapshot();cursor=None
        ident,active,state=_begin_search();slow_batches=[];completed=False;error_type=None
        progress_count=0;progress_at=time.perf_counter()
        def record_read(phase, operation):
            t=time.perf_counter();cpu=time.thread_time()
            try:return operation()
            finally:
                metrics[phase+'_ms']+=(time.perf_counter()-t)*1000
                metrics[phase+'_cpu_ms']+=(time.thread_time()-cpu)*1000
        def rows():
            nonlocal progress_at,progress_count
            first=record_read('sql_first_row',cursor.fetchone)
            if first is not None:
                metrics['fetched_count']+=1;yield first
            while True:
                prior_ms=metrics['sql_fetch_ms'];prior_cpu=metrics['sql_fetch_cpu_ms']
                row_start=metrics['fetched_count']
                batch=record_read('sql_fetch',lambda:cursor.fetchmany(256))
                wall_ms=metrics['sql_fetch_ms']-prior_ms
                cpu_ms=metrics['sql_fetch_cpu_ms']-prior_cpu
                metrics['sql_fetch_batch_count']+=1
                metrics['sql_fetch_max_batch_ms']=max(metrics['sql_fetch_max_batch_ms'],wall_ms)
                entry={'batch':metrics['sql_fetch_batch_count'],'row_start':row_start,
                       'rows':len(batch),'wall_ms':round(wall_ms,3),'cpu_ms':round(cpu_ms,3)}
                slow_batches.append(entry)
                slow_batches.sort(key=lambda b:b['wall_ms'],reverse=True)
                del slow_batches[5:]
                metrics['fetched_count']+=len(batch)
                now=time.perf_counter()
                if now-progress_at>=15 and progress_count<4:
                    obs.event(obs.get_logger('fulltext'),'fulltext.sql.progress',
                              diagnostic_revision=DIAGNOSTIC_REVISION,search_id=ident,
                              fetched_count=metrics['fetched_count'],batch=entry,
                              elapsed_ms=round((now-before['wall'])*1000,3))
                    progress_count+=1;progress_at=time.perf_counter()
                if not batch:return
                yield from batch
        try:
            obs.event(obs.get_logger('fulltext'),'fulltext.sql.started',
                      diagnostic_revision=DIAGNOSTIC_REVISION,search_id=ident,
                      process_id=os.getpid(),thread_id=threading.get_native_id(),
                      active_searches_at_start=active,concurrency_scope='process',
                      term_count=len(terms),allowed_count=len(allowed) if allowed is not None else None,
                      limit=limit,indexed_source_count=self.manifest.get('counts',{}).get('source'))
            cursor=record_read('sql_execute',lambda:db.execute(sql,(expression(terms),rank)))
            for sid,score in rows():
                if tied and score!=previous_score:
                    t=time.perf_counter()
                    out.extend(s for s in sorted(tied) if allowed is None or s in allowed)
                    metrics['scope_filter_ms']+=(time.perf_counter()-t)*1000
                    if limit and len(out)>=limit:
                        completed=True
                        return out[:limit]
                    tied=[]
                tied.append(sid);previous_score=score
            t=time.perf_counter()
            out.extend(s for s in sorted(tied) if allowed is None or s in allowed)
            metrics['scope_filter_ms']+=(time.perf_counter()-t)*1000
            completed=True
            return out[:limit] if limit else out
        except BaseException as exc:
            error_type=type(exc).__name__
            raise
        finally:
            concurrency=_finish_search(ident,state)
            if cursor is not None:cursor.close()
            metrics['selected_count']=min(len(out),limit) if limit else len(out)
            cpu_after=obs.cpu_pressure()
            delta={k:cpu_after[k]-v for k,v in cpu_before.items() if k in cpu_after}
            obs.event(obs.get_logger('fulltext'),'fulltext.sql.timings',
                      **{k:round(v,3) if isinstance(v,float) else v for k,v in metrics.items()},
                      diagnostic_revision=DIAGNOSTIC_REVISION,search_id=ident,
                      sql_status='completed' if completed else 'failed',error_type=error_type,
                      slowest_batches=slow_batches,progress_event_count=progress_count,
                      scope_rejected_count=metrics['fetched_count']-len(out) if completed and not limit else None,
                      concurrency_scope='process',**concurrency,**thread_delta(before,thread_snapshot()),
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
