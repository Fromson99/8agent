"""Complete a frozen glossary catalogue from official definitions and links.

The existing ``pipeline.py glossary`` owns this stage. A snapshot records every
request and response in SQLite; partial collection never publishes CURRENT.
No LLM, scheduler, GENOS connection, or inferred legal meaning is involved.
"""
from contextlib import closing, contextmanager
import fcntl
import gzip
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET

from lawrag.platform.paths import repository_root
from lawrag.sources.common import HttpClient, make_session
from lawrag.sources.moleg_knowledge import ENDPOINTS, MolegKnowledgeClient, parse_xml_page
from .collect_moleg_knowledge import _atomic_json, _digest, _hash_file, _publish

ENRICHMENTS = ('legal_term_detail', 'legal_term_relations',
               'everyday_term_relations', 'term_articles')
PROFILE = 'moleg-glossary-completion-v1'


def request_parameters(row, plan):
    """Single-source legacy packages and batched completed packages share consumers."""
    if plan.get('collection_mode') == 'catalogue-enrichment':
        parameters = row.get('_request')
        if not isinstance(parameters, dict) or not parameters:
            raise ValueError('enrichment row requires request provenance')
        return parameters
    return plan.get('parameters', {})


def source_ids(value):
    values = re.split(r'[,\s]+', value.strip())
    if not values or not all(re.fullmatch(r'\d+', v) for v in values):
        raise ValueError('official glossary source ID must contain numeric IDs')
    return sorted(set(values))


def linked_request(row, field, endpoint):
    value = row.get('fields', {}).get(field)
    if not value:
        return None
    url = urlsplit(value.replace('&amp;', '&'))
    if url.hostname and url.hostname not in {'law.go.kr', 'www.law.go.kr'}:
        raise ValueError('unexpected glossary source link host')
    values = parse_qs(url.query)
    if values.get('target') != [ENDPOINTS[endpoint].target]:
        raise ValueError('glossary source link target mismatch')
    ids = values.get('MST', [])
    if len(ids) != 1 or not re.fullmatch(r'\d+', ids[0]):
        raise ValueError('glossary source link requires one MST')
    # Never execute a URL returned by source data; use the fixed API endpoint.
    return {'MST': ids[0]}


def relation_target(row):
    """Resolve the namespace from official target links, including legal→daily."""
    targets = set()
    for field in ('용어간관계링크', '조문간관계링크'):
        link = row.get('fields', {}).get(field)
        if not link:
            continue
        target = parse_qs(urlsplit(link.replace('&amp;', '&')).query).get('target', [''])[0]
        endpoint, kind = {'lstrmRlt': ('legal_term_relations', 'knowledge_terms'),
                          'dlytrmRlt': ('everyday_term_relations', 'everyday_terms'),
                          'lstrmRltJo': ('term_articles', 'knowledge_terms')}.get(target, (None, None))
        if endpoint is None:
            raise ValueError('unsupported official relation target')
        parameters = linked_request(row, field, endpoint)
        if row.get('source_id') != parameters['MST']:
            raise ValueError('term ID/link mismatch')
        targets.add('moleg:' + kind + ':' + parameters['MST'])
    if len(targets) != 1:
        raise ValueError('official relation requires one unambiguous target')
    return targets.pop()


def package_rows(path):
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def requests_for(row):
    kind = row['entity_type']
    if kind == 'legal_terms':
        for ident in source_ids(row['source_id']):
            yield 'legal_term_detail', {'trmSeqs': ident}
    elif kind == 'knowledge_terms':
        for field, endpoint in [('용어간관계링크', 'legal_term_relations'),
                                ('조문간관계링크', 'term_articles')]:
            parameters = linked_request(row, field, endpoint)
            if parameters:
                yield endpoint, parameters
    elif kind == 'everyday_terms':
        parameters = linked_request(row, '용어간관계링크', 'everyday_term_relations')
        if parameters:
            yield 'everyday_term_relations', parameters
    else:
        raise ValueError('unsupported glossary catalogue')


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS catalogue(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS request(
        id TEXT PRIMARY KEY,endpoint TEXT NOT NULL,parameters TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
        response BLOB,response_sha256 TEXT,records TEXT,error TEXT);
      CREATE INDEX IF NOT EXISTS request_pending ON request(status,endpoint,id);
      CREATE TABLE IF NOT EXISTS request_term(
        request_id TEXT REFERENCES request(id),term_id TEXT REFERENCES catalogue(id),
        PRIMARY KEY(request_id,term_id));
      CREATE INDEX IF NOT EXISTS request_term_term ON request_term(term_id);
    ''')
    return db


@contextmanager
def locked(state, snapshot):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', snapshot):
        raise ValueError('snapshot must contain only letters, digits, underscores or hyphens')
    folder = Path(state) / 'completion' / snapshot
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / '.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield folder


def prepare(source, target, scope=None, endpoints=None):
    """Freeze source records and deduplicated requests in one atomic transaction."""
    if not source.is_file():
        raise ValueError('collect/import the complete glossary catalogues first')
    if endpoints is not None:
        endpoints = sorted(set(endpoints))
        if not endpoints or not set(endpoints).issubset(ENRICHMENTS):
            raise ValueError('choose supported completion endpoints')
        if not scope:
            raise ValueError('endpoint-only collection requires a corpus scope')
    selected = None
    if scope:
        from .glossary_scope import seed_terms
        selected = seed_terms(scope)
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as src:
        src.execute("BEGIN")
        fingerprint = hashlib.sha256()
        for ident, content in src.execute('SELECT id,fingerprint FROM terms ORDER BY id'):
            fingerprint.update(json.dumps([ident, content], separators=(',', ':')).encode())
        identity = {'catalogue_sha256': fingerprint.hexdigest(), 'profile': PROFILE,
                    'planner_sha256': _hash_file(Path(__file__)),
                    'parser_sha256': _hash_file(Path(__file__).parents[1] / 'sources/moleg_knowledge.py'),
                    'scope': scope}
        if endpoints is not None:
            identity['request_endpoints'] = endpoints
        with closing(connect(target)) as db:
            previous = db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()
            if previous:
                if json.loads(previous[0]) != identity:
                    raise ValueError('catalogue or implementation changed: use a new completion snapshot')
                return
            with db:
                count = 0
                kinds = set()
                for ident, payload in src.execute('SELECT id,payload FROM terms ORDER BY id'):
                    row = json.loads(payload)
                    kinds.add(row['entity_type'])
                    db.execute('INSERT INTO catalogue VALUES (?,?)', (ident, payload))
                    for endpoint, parameters in (requests_for(row) if selected is None or ident in selected else ()):
                        if endpoints is not None and endpoint not in endpoints:
                            continue
                        rid = _digest([endpoint, parameters])
                        db.execute('INSERT OR IGNORE INTO request(id,endpoint,parameters) VALUES (?,?,?)',
                                   (rid, endpoint, json.dumps(parameters, sort_keys=True)))
                        db.execute('INSERT OR IGNORE INTO request_term VALUES (?,?)', (rid, ident))
                    count += 1
                if not count or kinds != {'legal_terms', 'knowledge_terms', 'everyday_terms'}:
                    raise ValueError('completion requires all three imported catalogues')
                db.execute('INSERT INTO meta VALUES (?,?)', ('identity', json.dumps(identity, sort_keys=True)))


def status(db):
    identity = json.loads(db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0])
    scope = identity.get('scope')
    catalogue_count = db.execute('SELECT count(*) FROM catalogue').fetchone()[0]
    linked_count = db.execute('SELECT count(DISTINCT term_id) FROM request_term').fetchone()[0]
    groups = [dict(row) for row in db.execute(
        'SELECT endpoint,status,count(*) AS count FROM request GROUP BY endpoint,status ORDER BY endpoint,status')]
    pending = sum(r['count'] for r in groups if r['status'] != 'complete')
    return {'schema_version': PROFILE, 'requests': groups,
            'request_endpoints': identity.get('request_endpoints', list(ENRICHMENTS)),
            'collection_only': 'request_endpoints' in identity,
            'total_requests': sum(r['count'] for r in groups), 'remaining_requests': pending,
            'collection_complete': bool(groups) and pending == 0,
            'scope': scope,
            'reused_responses': int((db.execute("SELECT value FROM meta WHERE key='reused_responses'").fetchone() or [0])[0]),
            'catalogue_terms': catalogue_count,
            'unqueried_catalogue_terms': catalogue_count - linked_count,
            'terms_without_source_requests': (scope['counts']['seed_terms'] if scope else catalogue_count) - linked_count,
            'empty_responses': [dict(r) for r in db.execute("SELECT endpoint,count(*) AS count FROM request WHERE status='complete' AND records='[]' GROUP BY endpoint")],
            'definition_records': db.execute("SELECT coalesce(sum(json_array_length(records)),0) FROM request WHERE endpoint='legal_term_detail' AND status='complete'").fetchone()[0]}


def validate_response(endpoint, parameters, xml, records):
    root = ET.fromstring(xml)
    tag = root.tag.rsplit('}', 1)[-1]
    expected = {'legal_term_detail': 'LsTrmService', 'legal_term_relations': 'lstrmRltService',
                'everyday_term_relations': 'dlytrmRltService', 'term_articles': 'lstrmRltJoService'}
    if endpoint == 'legal_term_detail' and tag == 'Law' and not records and ''.join(root.itertext()).strip() == '일치하는 법령용어가 없습니다.  법령용어명을 확인하여 주십시오.':
        return  # Officially unavailable ID: retain the response and report the gap.
    if endpoint == 'legal_term_relations' and tag == 'Law' and not records and ''.join(root.itertext()).strip() == '일치하는 법령용어가 없습니다. 검색조건을 확인하여 주십시오.':
        return  # A missing official relation source is a recorded gap, not an API outage.
    if tag != expected[endpoint]:
        raise ValueError('unexpected official response envelope')
    if endpoint == 'legal_term_detail':
        requested = set(source_ids(parameters['trmSeqs']))
        for row in records:
            if row['source_id'] not in requested or not row['label']:
                raise ValueError('definition response identity mismatch')
    for row in records:
        if not row.get('label'):
            raise ValueError('official glossary response lacks label')


def collect(db, client, max_requests=0, emit=print):
    if max_requests < 0:
        raise ValueError('max-requests must be nonnegative')
    done = 0
    while not max_requests or done < max_requests:
        job = None
        for endpoint in ENRICHMENTS:
            for pending_status in ('failed', 'pending'):
                job = db.execute('SELECT * FROM request WHERE status=? AND endpoint=? ORDER BY id LIMIT 1',
                                 (pending_status, endpoint)).fetchone()
                if job is not None:
                    break
            if job is not None:
                break
        if job is None:
            break
        parameters = json.loads(job['parameters'])
        raw = None
        try:
            xml, parsed = client.fetch(job['endpoint'], parameters)
            raw = xml.encode('utf-8')
            validate_response(job['endpoint'], parameters, xml, parsed.records)
            records = [dict(row, _request=parameters, _request_id=job['id']) for row in parsed.records]
            raw = xml.encode('utf-8')
            with db:
                db.execute("UPDATE request SET status='complete',attempts=attempts+1,response=?,response_sha256=?,records=?,error=NULL WHERE id=?",
                           (gzip.compress(raw, mtime=0), hashlib.sha256(raw).hexdigest(),
                            json.dumps(records, ensure_ascii=False), job['id']))
        except Exception as exc:
            # Do not persist exceptions/URLs containing credentials or retry a failed
            # request endlessly. A later explicit resume retries the retained task.
            with db:
                db.execute("UPDATE request SET status='failed',attempts=attempts+1,error=?,response=?,response_sha256=? WHERE id=?",
                           (type(exc).__name__, gzip.compress(raw, mtime=0) if raw is not None else None,
                            hashlib.sha256(raw).hexdigest() if raw is not None else None, job['id']))
            emit(f"collection stopped: {job['endpoint']} {job['id']} ({type(exc).__name__})", flush=True)
            raise RuntimeError('official glossary collection stopped; completed responses are resumable') from None
        done += 1
        if done == 1 or done % 100 == 0:
            emit(f'glossary completion: {done} responses collected in this run', flush=True)
    return status(db)


def publish(db, folder, root):
    report = status(db)
    if not report['collection_complete']:
        raise ValueError('cannot publish incomplete glossary collection')
    packages = []
    scope = report.get('scope')
    allowed = None
    if scope:
        from .glossary_scope import article_scope
        allowed = article_scope(scope)
    # Reuse the explicitly frozen catalogue manifests, never glob for the latest.
    manifests = {json.loads(r[0])['package_manifest'] for r in db.execute('SELECT payload FROM catalogue')}
    from lawrag.datasets.catalog import load_package
    for name in sorted(manifests):
        load_package(name, verify_files=True)
        packages.append(Path(name))
    for endpoint in ENRICHMENTS:
        work = folder / 'packages' / endpoint
        (work / 'raw').mkdir(parents=True, exist_ok=True)
        records_path = work / 'records.jsonl'
        request_path = work / 'request-plan.json'
        if scope and endpoint == 'legal_term_detail':
            import shutil
            shutil.copyfile(scope['path'], work / 'scope.sqlite')
        raw_path = work / 'raw' / 'responses.xml.gz'
        request_count = record_count = excluded_count = 0
        # A compressed XML archive avoids hundreds of thousands of ZIP members.
        with raw_path.open('wb') as compressed, gzip.GzipFile(filename='', fileobj=compressed, mode='wb', mtime=0) as raw, records_path.open('w', encoding='utf-8') as out:
            raw.write(b'<Responses>')
            for row in db.execute('SELECT * FROM request WHERE endpoint=? ORDER BY id', (endpoint,)):
                xml = gzip.decompress(row['response'])
                if hashlib.sha256(xml).hexdigest() != row['response_sha256']:
                    raise ValueError('stored official response hash mismatch')
                raw.write(('<Response request_id="' + row['id'] + '">').encode())
                raw.write(ET.tostring(ET.fromstring(xml), encoding='utf-8'))
                raw.write(b'</Response>')
                for record in json.loads(row['records']):
                    if endpoint == 'term_articles' and allowed is not None:
                        from .glossary_scope import include_article
                        if not include_article(record, allowed):
                            excluded_count += 1
                            continue
                    out.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
                    record_count += 1
                request_count += 1
            raw.write(b'</Responses>')
        _atomic_json(request_path, {'schema_version': PROFILE, 'endpoint': endpoint,
            'collection_mode': 'catalogue-enrichment', 'parameters': {},
            'document_scope': scope, 'excluded_by_scope': excluded_count,
            'catalogue_identity': json.loads(db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0]),
            'checkpoint': {'completed': True, 'request_count': request_count,
                           'record_count': record_count, 'total_count': record_count,
                           'empty_response_count': db.execute("SELECT count(*) FROM request WHERE endpoint=? AND records='[]'", (endpoint,)).fetchone()[0]}})
        packages.append(_publish(root, endpoint, work, request_path, records_path))
    return packages, report


def run(state, snapshot, *, plan_only=False, max_requests=0, client=None, emit=print,
        corpus_generation=None, reuse_snapshot=None, endpoints=None):
    if endpoints is not None and not corpus_generation:
        raise ValueError('endpoint-only collection requires a corpus scope')
    state = Path(state)
    with locked(state, snapshot) as folder:
        scope = None
        if corpus_generation:
            from .glossary_scope import build_scope
            scope = build_scope(state / 'alignment.sqlite', corpus_generation, folder, emit)
        prepare(state / 'alignment.sqlite', folder / 'collection.sqlite', scope, endpoints)
        with closing(connect(folder / 'collection.sqlite')) as db:
            if reuse_snapshot:
                reuse_responses(db, Path(reuse_snapshot))
            report = status(db)
            if plan_only:
                _atomic_json(folder / 'status.json', report)
                return report
            if not report['collection_complete']:
                if client is None:
                    from dotenv import dotenv_values
                    oc = os.environ.get('LAW_OC') or dotenv_values(repository_root() / '.env').get('LAW_OC')
                    if not oc:
                        raise ValueError('LAW_OC is required for official glossary collection')
                    logger = logging.getLogger('glossary-completion')
                    logger.addHandler(logging.NullHandler())
                    client = MolegKnowledgeClient(HttpClient(make_session(), logger), oc)
                try:
                    report = collect(db, client, max_requests, emit)
                finally:
                    _atomic_json(folder / 'status.json', status(db))
            if report['collection_only']:
                # A selected endpoint is a resumable source collection, not a full dictionary.
                return report
            if report['collection_complete']:
                from .knowledge_transfer import dictionary, pack
                receipt_file = folder / 'completed.json'
                if receipt_file.exists():
                    receipt = json.loads(receipt_file.read_text())
                    if _hash_file(Path(receipt['dictionary'])) != receipt['dictionary_sha256'] or _hash_file(Path(receipt['zip'])) != receipt['zip_sha256']:
                        raise ValueError('completed glossary artifacts changed')
                    return receipt
                packages, report = publish(db, folder, repository_root())
                output = folder / 'dictionary.sqlite'
                compiled = dictionary(packages, output)
                archive = folder / 'glossary.zip'
                if archive.exists():
                    # Interrupted publication must validate exact package selection.
                    from .knowledge_transfer import unpack
                    _, existing = unpack(archive, folder / 'verify-transfer')
                    if sorted(_hash_file(p) for p in existing) != sorted(_hash_file(p) for p in packages):
                        raise ValueError('existing glossary ZIP contains different packages')
                    packed = {'sha256': _hash_file(archive)}
                else:
                    packed = pack(packages, archive)
                report.update(dictionary=str(output.resolve()), dictionary_sha256=compiled['sha256'],
                              coverage=compiled.get('coverage', {}), packages=[str(p) for p in packages],
                              zip=str(archive.resolve()), zip_sha256=packed['sha256'])
                _atomic_json(receipt_file, report)
                _atomic_json(state / 'COMPLETED.json', report)
            return report


def compile_enrichment(db, packages):
    """Preserve source-scoped senses and all official relations for consumers.

    Label matches are candidates only. A shared spelling never merges source IDs
    or grants a legal definition to a knowledge/everyday catalogue entry.
    """
    from .knowledge_transfer import inspect_package
    db.executescript('''
      CREATE TABLE sense(id TEXT PRIMARY KEY,source_id TEXT NOT NULL,label TEXT NOT NULL,
        label_key TEXT NOT NULL,definition TEXT NOT NULL,source TEXT NOT NULL,
        dictionary_kind TEXT NOT NULL,payload TEXT NOT NULL,provenance TEXT NOT NULL);
      CREATE TABLE scope_document(id TEXT PRIMARY KEY,name TEXT,source_sha256 TEXT);
      CREATE TABLE scope_definition(document_id TEXT,block_id TEXT,term TEXT,source_text TEXT,PRIMARY KEY(document_id,block_id,term));
      CREATE TABLE scope_occurrence(term_id TEXT,document_id TEXT,block_id TEXT,start INTEGER,end INTEGER,surface TEXT,is_definition INTEGER,PRIMARY KEY(term_id,document_id));
      CREATE INDEX sense_label ON sense(label_key);
      CREATE INDEX sense_source ON sense(source_id);
      CREATE TABLE term_sense(term_id TEXT REFERENCES term(id),sense_id TEXT REFERENCES sense(id),
        match_kind TEXT NOT NULL,PRIMARY KEY(term_id,sense_id));
      CREATE TABLE official_relation(id TEXT PRIMARY KEY,source_id TEXT NOT NULL,
        target_id TEXT NOT NULL,relation_code TEXT NOT NULL,payload TEXT NOT NULL,provenance TEXT NOT NULL);
      CREATE INDEX official_relation_source ON official_relation(source_id);
      CREATE TABLE official_article(id TEXT PRIMARY KEY,term_id TEXT NOT NULL,
        law_id TEXT NOT NULL,article TEXT NOT NULL,payload TEXT NOT NULL,provenance TEXT NOT NULL);
      CREATE INDEX official_article_term ON official_article(term_id);
    ''')
    selected = {}
    for path in packages:
        _, kind, artifacts, plan = inspect_package(path)
        if kind not in ENRICHMENTS:
            continue
        provenance = _hash_file(Path(path))
        if 'scope.sqlite' in artifacts:
            from .glossary_scope import compile_scope
            compile_scope(db, artifacts['scope.sqlite'].resolved_path(), plan['document_scope'])
        count = 0
        with artifacts['records.jsonl'].resolved_path().open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                if row.get('entity_type') != kind:
                    raise ValueError('enrichment endpoint/row mismatch')
                params = request_parameters(row, plan)
                MolegKnowledgeClient(None, 'validation').params(kind, params)
                payload = json.dumps(row, ensure_ascii=False, sort_keys=True)
                scope = (kind, json.dumps(params, sort_keys=True))
                if scope in selected and selected[scope] != provenance:
                    raise ValueError('choose one completed generation per enrichment request')
                selected[scope] = provenance
                if kind == 'legal_term_detail':
                    if row['source_id'] not in source_ids(params['trmSeqs']):
                        raise ValueError('definition source ID does not match request')
                    ident = 'moleg:definition:' + row['source_id']
                    values = (ident, row['source_id'], row['label'], ''.join(row['label'].split()),
                              row.get('definition', ''), row.get('source', ''), row.get('dictionary_kind', ''), payload, provenance)
                    old = db.execute('SELECT payload FROM sense WHERE id=?', (ident,)).fetchone()
                    if old and old[0] != payload:
                        raise ValueError('conflicting definitions for one official source ID')
                    db.execute('INSERT OR IGNORE INTO sense VALUES (?,?,?,?,?,?,?,?,?)', values)
                elif kind == 'term_articles':
                    fields = row.get('fields', {})
                    link = parse_qs(urlsplit(fields.get('조문연계용어링크', '').replace('&amp;', '&')).query)
                    lawid = link.get('ID', [''])[0]
                    article = link.get('JO', [''])[0]
                    if not re.fullmatch(r'\d{6}', lawid) or not re.fullmatch(r'\d{6}', article):
                        raise ValueError('official article needs exact law and article coordinates')
                    source = 'moleg:knowledge_terms:' + params['MST']
                    db.execute('INSERT OR IGNORE INTO official_article VALUES (?,?,?,?,?,?)',
                               (_digest([source, lawid, article, payload]), source, lawid, article, payload, provenance))
                else:
                    fields = row.get('fields', {})
                    source_kind = 'everyday_terms' if kind == 'everyday_term_relations' else 'knowledge_terms'
                    source = 'moleg:' + source_kind + ':' + params['MST']
                    target = relation_target(row)
                    # Preserve the namespace proved by the source link.
                    db.execute('INSERT OR IGNORE INTO official_relation VALUES (?,?,?,?,?,?)',
                               (_digest([source, payload]), source, target,
                                fields.get('용어관계코드', ''), payload, provenance))
                count += 1
        if count != plan['checkpoint']['record_count']:
            raise ValueError('enrichment record count mismatch')
    for ident, kind, label, payload in db.execute('SELECT id,kind,label,payload FROM term'):
        if kind == 'legal_terms':
            for source in source_ids(json.loads(payload)['source_id']):
                db.execute('''INSERT OR IGNORE INTO term_sense SELECT ?,id,'SOURCE_ID'
                              FROM sense WHERE source_id=?''', (ident, source))
        else:
            db.execute('''INSERT OR IGNORE INTO term_sense SELECT ?,id,'LABEL_CANDIDATE'
                          FROM sense WHERE label_key=?''', (ident, ''.join(label.split())))
    return {
        'scoped_documents': db.execute('SELECT count(*) FROM scope_document').fetchone()[0],
        'local_definition_evidence': db.execute('SELECT count(*) FROM scope_definition').fetchone()[0],
        'definition_records': db.execute('SELECT count(*) FROM sense').fetchone()[0],
        'definitions_with_text': db.execute("SELECT count(*) FROM sense WHERE trim(definition)!=''").fetchone()[0],
        'definitions_with_source': db.execute("SELECT count(*) FROM sense WHERE trim(source)!=''").fetchone()[0],
        'terms_with_source_definition': db.execute("SELECT count(DISTINCT t.term_id) FROM term_sense t JOIN sense s ON s.id=t.sense_id WHERE t.match_kind='SOURCE_ID' AND trim(s.definition)!=''").fetchone()[0],
        'terms_with_label_candidates': db.execute("SELECT count(DISTINCT term_id) FROM term_sense WHERE match_kind='LABEL_CANDIDATE'").fetchone()[0],
        'official_relations': db.execute('SELECT count(*) FROM official_relation').fetchone()[0],
        'official_article_links': db.execute('SELECT count(*) FROM official_article').fetchone()[0],
        'canonical_approval': False,
    }


def definition_hints(db, term_id, limit=3):
    rows = db.execute('''SELECT s.id,s.label,s.definition,s.source,s.dictionary_kind,t.match_kind
        FROM term_sense t JOIN sense s ON s.id=t.sense_id
        WHERE t.term_id=? AND trim(s.definition)!='' ORDER BY s.id''', (term_id,)).fetchall()
    keys = ('id', 'term', 'definition', 'source', 'dictionary_kind', 'match_kind')
    return {'candidates': [dict(zip(keys, r)) for r in rows[:limit]],
            'total': len(rows), 'truncated': len(rows) > limit, 'canonical_approval': False}



def reuse_responses(db, source):
    """Reuse only selected, successfully collected raw responses, then reparse them."""
    if not source.is_file():
        raise ValueError('reuse snapshot must name an existing collection.sqlite')
    old = db.execute("SELECT value FROM meta WHERE key='reuse_source'").fetchone()
    if old:
        if json.loads(old[0])['path'] != str(source.resolve()):
            raise ValueError('reuse source differs from the frozen selection')
        return
    from .collect_moleg_knowledge import _hash_file
    source_hash = _hash_file(source)
    reused = 0
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as cache:
        cache.row_factory = sqlite3.Row
        cache.execute('BEGIN')
        with db:
            for task in db.execute("SELECT id,endpoint,parameters FROM request WHERE status='pending'").fetchall():
                cached = cache.execute("SELECT * FROM request WHERE id=? AND status='complete'", (task['id'],)).fetchone()
                if not cached:
                    continue
                if cached['endpoint'] != task['endpoint'] or json.loads(cached['parameters']) != json.loads(task['parameters']):
                    raise ValueError('cached request identity mismatch')
                raw = gzip.decompress(cached['response'])
                if hashlib.sha256(raw).hexdigest() != cached['response_sha256']:
                    raise ValueError('cached response hash mismatch')
                parsed = parse_xml_page(raw.decode('utf-8'), ENDPOINTS[task['endpoint']])
                parameters = json.loads(task['parameters'])
                validate_response(task['endpoint'], parameters, raw.decode('utf-8'), parsed.records)
                records = [dict(r, _request=parameters, _request_id=task['id']) for r in parsed.records]
                db.execute("UPDATE request SET status='complete',response=?,response_sha256=?,records=? WHERE id=?",
                           (cached['response'], cached['response_sha256'], json.dumps(records, ensure_ascii=False), task['id']))
                reused += 1
            if _hash_file(source) != source_hash:
                raise ValueError('reuse source changed; stop its collector before importing')
            db.execute('INSERT INTO meta VALUES (?,?)', ('reuse_source', json.dumps({'path': str(source.resolve()), 'sha256': source_hash})))
            db.execute('INSERT INTO meta VALUES (?,?)', ('reused_responses', str(reused)))
