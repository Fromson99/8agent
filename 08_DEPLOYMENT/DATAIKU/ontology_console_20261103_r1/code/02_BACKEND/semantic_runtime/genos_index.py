"""Generation-local GENOS SQLite vector index; no external VDB or NumPy required."""
from dataclasses import replace
from contextlib import contextmanager
import hashlib
import heapq
import json
import sqlite3

from .contracts import sha
from .genos_backend import unit_vector

FORMAT = 'genos-sqlite-v1'


class SQLiteVectors:
    def __init__(self, store, descriptor, *, provider=None):
        self.store, self.descriptor, self.provider = store, descriptor, provider
        self.path = (store.path / descriptor['path']).resolve()
        self.path.relative_to(store.path)
        if descriptor.get('format') != FORMAT or sha(self.path) != descriptor['sha256']:
            raise ValueError('GENOS vector format/hash mismatch')
        if descriptor['source_store_sha256'] != store.manifest['source_store_sha256']:
            raise ValueError('GENOS vector/source provenance mismatch')
        with self.connect() as db:
            identity = json.loads(db.execute('SELECT value FROM meta WHERE key="identity"').fetchone()[0])
            if any(descriptor[k] != v for k, v in identity.items()):
                raise ValueError('GENOS vector identity mismatch')
            count, covered = 0, {}
            for did, bid, start, end, text, text_hash, vector in db.execute('SELECT document_id,block_id,start,end,text,text_sha256,vector FROM chunk ORDER BY document_id,block_id,start'):
                source = store.source(did, bid)['text']
                if (not 0 <= start < end <= len(source) or source[start:end] != text
                        or hashlib.sha256(source.encode()).hexdigest() != text_hash):
                    raise ValueError('GENOS chunk/source coordinate mismatch')
                if len(unit_vector(json.loads(vector))) != descriptor['dimensions']:
                    raise ValueError('GENOS index dimension mismatch')
                if covered.get((did, bid), 0) != start:
                    raise ValueError('GENOS chunk coverage gap/overlap')
                covered[did, bid] = end
                count += 1
            if not count or count != descriptor['rows']:
                raise ValueError('GENOS vector count mismatch')
            expected = {(d, b): len(t) for d, b, t in store.db.execute('SELECT document_id,block_id,text FROM source_block') if t.strip()}
            if covered != expected:
                raise ValueError('GENOS index omits source blocks or text')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)
        try:
            yield db
        finally:
            db.close()

    def embed_query(self, question):
        if self.provider is not None:
            if (self.provider.models['embed'] != self.descriptor['model']
                    or self.provider.targets['embed'].root != self.descriptor['endpoint']):
                raise ValueError('query/document embedding endpoint/model mismatch')
            vectors, _ = self.provider.embed([question], 'query-embedding')
            return unit_vector(vectors[0])
        from . import genos
        target, configured = genos.from_env('embed')
        if target.root != self.descriptor['endpoint']:
            raise ValueError('query/document embedding endpoint mismatch')
        target = replace(target, max_retries=1)
        if genos.advertised_model(target, configured) != self.descriptor['model']:
            raise ValueError('query/document embedding model mismatch')
        raw = genos.request_json(target, '/embeddings', {'model': self.descriptor['model'], 'input': [question]})
        if len(raw.get('data', [])) != 1 or raw['data'][0].get('index') != 0:
            raise ValueError('query embedding count/index mismatch')
        return unit_vector(raw['data'][0]['embedding'])

    def search(self, question, allowed, limit):
        if limit < 1 or not allowed:
            return []
        query = self.embed_query(question)
        if len(query) != self.descriptor['dimensions']:
            raise ValueError('query/document embedding dimension mismatch')
        # At most one best score per original block; memory is O(blocks), not O(vectors*dimensions).
        scores = {}
        with self.connect() as db:
            for did, bid, raw in db.execute('SELECT document_id,block_id,vector FROM chunk'):
                if did not in allowed:
                    continue
                score = sum(a*b for a, b in zip(query, json.loads(raw)))
                scores[did, bid] = max(scores.get((did, bid), -2), score)
        return [{**self.store.source(*key), 'vector_score': score}
                for key, score in heapq.nlargest(limit, scores.items(), key=lambda x: (x[1], x[0]))]
