"""Published Gold/G19 vector reader for Oracle-only serving.

Knowledge and publication metadata stay in Oracle. Query encoding uses the
authenticated host endpoint, bound explicitly to the ingestion profile hash.
"""
import math
import os
import re
import time

from .initial_vector import VectorError, VectorUnavailable, normalize
from .oracle_dp_io import canonical, digest


def unique_json(value):
    import json
    if hasattr(value, 'read'):
        value = value.read()
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise VectorError('VECTOR_PUBLICATION: duplicate JSON key')
            result[key] = item
        return result
    try:
        return json.loads(value, object_pairs_hook=pairs)
    except (TypeError, ValueError) as exc:
        raise VectorError('VECTOR_PUBLICATION: invalid JSON') from exc


class PublishedEncoder:
    """Same bounded HTTP protocol, with explicit cross-platform model binding."""
    def __init__(self, config, *, env=None, post=None, deadline=None):
        e = os.environ if env is None else env
        expected = e.get('GENOS_EMBED_PROFILE_SHA256', '').strip()
        if not re.fullmatch('[0-9a-f]{64}', expected) or expected != digest(config):
            raise VectorError('VECTOR_BINDING: GENOS_EMBED_PROFILE_SHA256 must match the Oracle publication')
        model = e.get('GENOS_EMBED_MODEL', '').strip()
        if not model:
            raise VectorError('VECTOR_CONFIG: GENOS_EMBED_MODEL required for published embeddings')
        # A different Mesh ID and GENOS serving name may represent the same
        # encoder. The host must attest their identity using the publication hash.
        from .genos import from_env
        self.profile = dict(config, model=model)
        try:
            self.target, _ = from_env('embed', environ=e)
        except (TypeError, ValueError) as exc:
            raise VectorError('VECTOR_CONFIG: invalid GENOS embedding endpoint settings') from exc
        if not e.get('GENOS_EMBED_KEY', '').strip():
            raise VectorError('VECTOR_CONFIG: GENOS_EMBED_KEY required')
        self.deadline = deadline or time.monotonic() + 10
        self.calls = 0
        self.post = post

    def encode(self, texts):
        if (not isinstance(texts, list) or not 1 <= len(texts) <= 16
                or any(not isinstance(t, str) or not t.strip() or len(t) > 16000 for t in texts)):
            raise VectorError('VECTOR_INPUT: bounded nonempty inputs required')
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise VectorUnavailable('VECTOR_TIMEOUT: request deadline')
        session = None
        send = self.post
        if send is None:
            import requests
            session = requests.Session()
            session.trust_env = False
            send = session.post
        self.calls += 1
        try:
            response = send(self.target.url('/embeddings'), headers=dict(self.target.headers),
                json={'model': self.profile['model'], 'input': texts},
                timeout=min(remaining, 10), allow_redirects=False)
            if response.status_code in (429, 500, 502, 503, 504):
                raise VectorUnavailable('VECTOR_TRANSPORT: ' + str(response.status_code))
            if response.status_code != 200:
                raise VectorError('VECTOR_HTTP: ' + str(response.status_code))
            body = response.json()
            rows = body.get('data') if isinstance(body, dict) else None
        except VectorError:
            raise
        except Exception as exc:
            raise VectorUnavailable('VECTOR_TRANSPORT: ' + type(exc).__name__) from None
        finally:
            if session is not None:
                session.close()
        if (not isinstance(rows, list) or len(rows) != len(texts)
                or any(not isinstance(r, dict) or type(r.get('index')) is not int for r in rows)
                or {r['index'] for r in rows} != set(range(len(texts)))):
            raise VectorError('VECTOR_RESPONSE: incomplete or duplicate indices')
        return [normalize(r.get('embedding'), self.profile['dimensions']) for r in sorted(rows, key=lambda r: r['index'])]


class Retriever:
    def __init__(self, request, *, mapping=None, encoder_factory=PublishedEncoder):
        self.request = request
        self.mapping = mapping or getattr(getattr(request.sql, 'client', None), 'schema_map', None)
        if not getattr(self.mapping, 'vector_contract', False):
            raise VectorError('VECTOR_MAPPING: published vector mapping required')
        self.encoder_factory = encoder_factory
        self.pin = None
        self.cache = {}

    def _table(self, key, columns):
        table = self.mapping.tables[key]
        return '(SELECT ' + ','.join(table['columns'][name]['name'] + ' AS ' + name
                                    for name in columns) + ' FROM ' + self.mapping.physical_table(key) + ')'

    def publication(self):
        req = self.request
        parent = req.records.manifest.get('extension', {}).get('base_query_id', req.release_id)
        rows = req.sql.query('SELECT VCTR_POST_ID,CHAN_NO FROM ' + self._table('VCTR_HEAD',
            ['RFRN_POST_HASH_VALU', 'VCTR_POST_ID', 'CHAN_NO']) + ' WHERE RFRN_POST_HASH_VALU=:q',
            [('q', parent, 'VARCHAR2')], limit=2)
        if not rows or len(rows) == 1 and rows[0]['VCTR_POST_ID'] is None:
            raise VectorUnavailable('VECTOR_NOT_PUBLISHED: selected Oracle query has no vector head')
        if len(rows) != 1 or type(rows[0]['CHAN_NO']) is not int or rows[0]['CHAN_NO'] < 1:
            raise VectorError('VECTOR_PUBLICATION: invalid head')
        head = rows[0]
        rows = req.sql.query('SELECT VCTR_POST_IFMN_CTNT FROM ' + self._table('VCTR_POST',
            ['VCTR_POST_ID', 'VCTR_POST_IFMN_CTNT']) + ' WHERE VCTR_POST_ID=:p',
            [('p', head['VCTR_POST_ID'], 'VARCHAR2')], limit=2)
        if len(rows) != 1:
            raise VectorError('VECTOR_PUBLICATION: missing or duplicate metadata')
        envelope = unique_json(rows[0]['VCTR_POST_IFMN_CTNT'])
        if not isinstance(envelope, dict) or set(envelope) != {'manifest', 'completion'}:
            raise VectorError('VECTOR_PUBLICATION: envelope')
        manifest, complete = envelope['manifest'], envelope['completion']
        if not isinstance(manifest, dict) or not isinstance(complete, dict):
            raise VectorError('VECTOR_PUBLICATION: metadata')
        config = manifest.get('profile', {})
        corpus = req.records.manifest['source_manifest']['scope']['document_version_ids']
        documents = manifest.get('documents')
        if (digest(manifest) != head['VCTR_POST_ID'] or manifest.get('query_id') != parent
                or manifest.get('source_release_id') != req.snapshot.release_id
                or manifest.get('dataset_version') != req.snapshot.dataset_version
                or not isinstance(documents, list) or any(not isinstance(d, str) or not d for d in documents)
                or len(set(documents)) != len(documents)
                or set(documents) != set(corpus) or complete.get('status') != 'READY'
                or type(complete.get('count')) is not int or complete['count'] < 1
                or complete.get('profile_sha256') != digest(config)):
            raise VectorError('VECTOR_PUBLICATION: source/profile/completion binding')
        if (not isinstance(config, dict) or config.get('metric') != 'COSINE'
                or config.get('normalization') != 'l2' or type(config.get('dimensions')) is not int
                or not 1 <= config['dimensions'] <= 4096
                or any(not isinstance(config.get(k), str) or not config[k].strip() for k in ('model', 'revision'))):
            raise VectorError('VECTOR_PROFILE: unsupported publication profile')
        return head, config

    def search(self, question, documents, source_ids=None):
        req = self.request
        documents = set(documents)
        if not documents <= req.sources.allowed:
            raise VectorError('VECTOR_SCOPE: cannot widen request')
        if not documents or source_ids == []:
            return {'publication_id': None, 'revision': None, 'rows': [], 'embedding_calls': 0, 'truncated': False}
        if not isinstance(question, str) or not question.strip():
            raise VectorError('VECTOR_INPUT: nonempty question required')
        if source_ids is not None and (not isinstance(source_ids, (list, tuple))
                or any(not isinstance(s, str) or not s for s in source_ids)):
            raise VectorError('VECTOR_SCOPE: invalid source IDs')
        if self.pin is None:
            self.pin = self.publication()
        head, config = self.pin
        key = digest([question, sorted(documents), source_ids, head, req.release_id])
        if key in self.cache:
            return self.cache[key]
        encoder = self.encoder_factory(config, deadline=req.sql.deadline)
        vector = normalize(encoder.encode([question])[0], config['dimensions'])
        binds = [('p', head['VCTR_POST_ID'], 'VARCHAR2'), ('v', canonical(vector), 'CLOB'),
                 ('docs', canonical(sorted(documents)), 'CLOB')]
        table = self._table('VCTR_ITEM', ['VCTR_POST_ID', 'DOC_ID', 'SRC_UNIT_ID', 'EMBD_VCTR_VALU'])
        where = "v.VCTR_POST_ID=:p AND v.DOC_ID IN (SELECT j.did FROM JSON_TABLE(:docs,'$[*]' COLUMNS(did VARCHAR2(1000) PATH '$')) j)"
        source = 'v.SRC_UNIT_ID'
        join = ''
        if 'extension' in req.records.manifest:
            # The older packed corpus stores structure unit IDs. Resolve those
            # through the selected, immutable native.vector_source projection.
            names = req.sql.gold_config.names('query_row', only_kind='native.vector_source')
            join = (' JOIN ' + names.table + ' m ON m.DOCUMENT_ID=v.DOC_ID AND m.OWNER_ID=v.SRC_UNIT_ID'
                    " AND m.KIND='native.vector_source' AND m.RELEASE_ID=:q")
            binds.append(('q', req.release_id, 'VARCHAR2'))
            source = 'm.TARGET_ID'
        if source_ids is not None:
            where += ' AND ' + source + " IN (SELECT j.sid FROM JSON_TABLE(:sources,'$[*]' COLUMNS(sid VARCHAR2(1000) PATH '$')) j)"
            binds.append(('sources', canonical(sorted(set(source_ids))), 'CLOB'))
        statement = ('SELECT v.DOC_ID,' + source + ' AS SOURCE_ID,MIN(VECTOR_DISTANCE(v.EMBD_VCTR_VALU,TO_VECTOR(:v),COSINE)) AS DISTANCE FROM '
                     + table + ' v' + join + ' WHERE ' + where + ' GROUP BY v.DOC_ID,' + source
                     + ' ORDER BY DISTANCE,DOC_ID,SOURCE_ID FETCH FIRST 100 ROWS ONLY')
        rows = req.sql.query(statement, binds, limit=100)
        if any(r['DOC_ID'] not in documents or not isinstance(r['SOURCE_ID'], str)
               or not math.isfinite(float(r['DISTANCE']))
               or source_ids is not None and r['SOURCE_ID'] not in source_ids for r in rows):
            raise VectorError('VECTOR_SCOPE: invalid result')
        result = {'publication_id': head['VCTR_POST_ID'], 'revision': head['CHAN_NO'], 'rows': rows,
                  'embedding_calls': encoder.calls, 'truncated': len(rows) == 100}
        self.cache[key] = result
        return result
