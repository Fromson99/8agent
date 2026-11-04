"""Gold vectors published by the ZIP Flow, with an explicit host embedding port.

The host supplies encode(text)->vector and the exact publication profile. Packed
local releases retain their existing reader. No model is selected implicitly.
"""
import math


def install(runtime, embedding=None, embedding_profile=None):
    from semantic_runtime import initial_vector
    from semantic_runtime.initial_vector import VectorError, normalize
    from semantic_runtime.oracle_dp_io import canonical, digest
    from gold_connection import VectorReader
    packed = initial_vector.Retriever

    class Retriever:
        def __init__(self, request):
            self.request = request
            self.delegate = None
            self.pin = None
            self.cache = {}
            self.embedding_calls = 0
            if 'extension' in request.records.manifest:
                self.delegate = packed(request)

        def search(self, question, documents, source_ids=None):
            if self.delegate is not None:
                return self.delegate.search(question, documents, source_ids)
            req = self.request
            documents = set(documents)
            if not documents <= req.sources.allowed:
                raise VectorError('GOLD_VECTOR_SCOPE')
            if not documents or source_ids == []:
                return {'publication_id': None, 'revision': None, 'rows': [],
                        'embedding_calls': 0, 'truncated': False}
            if not callable(embedding) or embedding_profile is None:
                raise VectorError('GOLD_QUERY_EMBEDDING_PORT_REQUIRED')
            cfg = req.sql.gold_config
            reader = VectorReader(req, cfg)
            if self.pin is None:
                head = reader.active()
                if head is None:
                    raise VectorError('GOLD_VECTOR_DISABLED')
                envelope = reader.metadata(head['VCTR_POST_ID'])
                corpus = set(req.records.manifest['source_manifest']['scope']['document_version_ids'])
                profile = envelope['manifest']['profile']
                if (set(envelope['manifest']['documents']) != corpus or profile != embedding_profile
                        or profile['metric'] != 'COSINE' or profile['normalization'] != 'l2'
                        or type(profile['dimensions']) is not int or not 1 <= profile['dimensions'] <= 4096):
                    raise VectorError('GOLD_VECTOR_PROFILE')
                self.pin = (head, profile)
            head, profile = self.pin
            key = digest([question, sorted(documents), source_ids, head, req.release_id])
            if key in self.cache:
                return self.cache[key]
            if not isinstance(question, str) or not question.strip():
                raise VectorError('GOLD_EMBED_INPUT')
            vector = normalize(embedding(question), profile['dimensions'])
            self.embedding_calls += 1
            binds = [('pub', head['VCTR_POST_ID'], 'VARCHAR2'),
                     ('docs', canonical(sorted(documents)), 'CLOB'),
                     ('v', canonical(vector), 'CLOB')]
            where = "VCTR_POST_ID=:pub AND DOC_ID IN (SELECT j.did FROM JSON_TABLE(:docs,'$[*]' COLUMNS(did VARCHAR2(1000) PATH '$')) j)"
            if source_ids is not None:
                binds.append(('sources', canonical(sorted(source_ids)), 'CLOB'))
                where += " AND SRC_UNIT_ID IN (SELECT j.sid FROM JSON_TABLE(:sources,'$[*]' COLUMNS(sid VARCHAR2(1000) PATH '$')) j)"
            statement = ('SELECT DOC_ID,SRC_UNIT_ID AS SOURCE_ID,MIN(VECTOR_DISTANCE(EMBD_VCTR_VALU,TO_VECTOR(:v),COSINE)) AS DISTANCE FROM '
                         + cfg.table('VCTR_ITEM') + ' WHERE ' + where
                         + ' GROUP BY DOC_ID,SRC_UNIT_ID ORDER BY DISTANCE,DOC_ID,SRC_UNIT_ID FETCH FIRST 100 ROWS ONLY')
            rows = req.sql.query(statement, binds, limit=100)
            if any(r['DOC_ID'] not in documents or not math.isfinite(float(r['DISTANCE']))
                   or source_ids is not None and r['SOURCE_ID'] not in source_ids for r in rows):
                raise VectorError('GOLD_VECTOR_RESULT_SCOPE')
            value = {'publication_id': head['VCTR_POST_ID'], 'revision': head['CHAN_NO'],
                     'query_release_id': req.release_id, 'rows': rows, 'embedding_calls': 1,
                     'truncated': len(rows) == 100}
            self.cache[key] = value
            return value

    initial_vector.Retriever = Retriever
