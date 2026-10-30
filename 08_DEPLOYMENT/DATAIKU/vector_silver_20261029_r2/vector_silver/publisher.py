"""Bounded SQL batches; same publication/profile/segment contract as MAIN116."""
import json

from lawrag.pipeline.oracle_query_dataiku import render
from semantic_runtime.initial_vector import VectorError, decode, vector_sql
from semantic_runtime.oracle_dp_io import digest
from semantic_runtime.vector_publish import Publisher as BasePublisher, segments


class Publisher(BasePublisher):
    sql_bytes = 60000

    def existing(self, batch):
        binds = [('p', self.pub, 'VARCHAR2')]
        names = []
        for i, item in enumerate(batch):
            names.append(':s' + str(i))
            binds.append(('s' + str(i), item['id'], 'VARCHAR2'))
        rows = self.sql.query(
            f'SELECT SEG_ID,DOC_ID,SOURCE_ID,META_JSON, '
            f'VECTOR_DIMENSION_COUNT(EMBEDDING) AS DIM, '
            f'VECTOR_DIMENSION_FORMAT(EMBEDDING) AS FMT FROM {self.repo.s} '
            'WHERE PUB_ID=:p AND SEG_ID IN (' + ','.join(names) + ')', binds, limit=len(batch))
        actual = {row['SEG_ID']: row for row in rows}
        expected = {item['id']: item for item in batch}
        if len(actual) != len(rows) or len(expected) != len(batch) or not set(actual) <= set(expected):
            raise VectorError('VECTOR_BUILD: duplicate/unexpected segment')
        for sid, row in actual.items():
            meta = expected[sid]['meta']
            if (decode(row['META_JSON']) != meta
                    or row['DOC_ID'] != meta['document_id'] or row['SOURCE_ID'] != meta['source_id']
                    or int(row['DIM']) != self.profile['dimensions'] or row['FMT'] != 'FLOAT32'):
                raise VectorError('VECTOR_BUILD: existing row metadata/dimension mismatch')
        return actual

    def insert_many(self, missing, vectors):
        statements, binds = [], []
        def flush():
            if statements:
                self.execute(' '.join(statements), binds)
                statements.clear()
                binds.clear()
        for i, (item, vector) in enumerate(zip(missing, vectors, strict=True)):
            names = {k: k + str(i) for k in ('p','id','doc','sid','meta','lease')}
            m = item['meta']
            values = [self.pub, item['id'], m['document_id'], m['source_id'],
                      json.dumps(m), self.lease]
            additions = [(names[k], v, 'CLOB' if k == 'meta' else 'VARCHAR2')
                         for k, v in zip(names, values)]
            n = {k: ':' + v for k, v in names.items()}
            expr = vector_sql(vector, self.profile['dimensions'])
            statement = (
                f'INSERT INTO {self.repo.s}(PUB_ID,SEG_ID,DOC_ID,SOURCE_ID,META_JSON,EMBEDDING) '
                f'SELECT {n["p"]},{n["id"]},{n["doc"]},{n["sid"]},{n["meta"]},{expr} '
                f'FROM {self.repo.r} WHERE PUB_ID={n["p"]} AND LEASE_ID={n["lease"]} AND STATUS=\'BUILDING\'; '
                "IF SQL%ROWCOUNT<>1 THEN RAISE_APPLICATION_ERROR(-20002,'VECTOR_LEASE_LOST'); END IF;")
            def size(stmts, bs):
                body = 'BEGIN ' + ' '.join(stmts) + ' COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;'
                return len(render(body, bs, write=True).encode())
            if size([statement], additions) > self.sql_bytes:
                raise VectorError('VECTOR_SQL_SIZE: one row exceeds 60000 UTF-8 bytes')
            if statements and size(statements + [statement], binds + additions) > self.sql_bytes:
                flush()
            statements.append(statement)
            binds.extend(additions)
        flush()

    def build(self, *, activate=True, items=None):
        r, a, pub, q = self.repo.r, self.repo.a, self.pub, self.request.release_id
        head = self.repo.active(q)
        expected = head['REVISION'] if head else 0
        self.execute(f"BEGIN INSERT INTO {r}(PUB_ID,QUERY_ID,MANIFEST_JSON,STATUS) "
                     "VALUES(:p,:q,:manifest,'BUILDING'); EXCEPTION WHEN DUP_VAL_ON_INDEX THEN NULL; END;",
                     [('p',pub,'VARCHAR2'),('q',q,'VARCHAR2'),
                      ('manifest',json.dumps(self.manifest),'CLOB')])
        row = self.repo.read(pub)
        if row['MANIFEST_JSON'] != self.manifest:
            raise VectorError('VECTOR_BUILD: conflicting manifest')
        ready = row['STATUS'] == 'READY'
        if not ready:
            self.execute(f"UPDATE {r} SET LEASE_ID=:lease WHERE PUB_ID=:p AND LEASE_ID IS NULL AND STATUS='BUILDING'; "
                         "IF SQL%ROWCOUNT<>1 THEN RAISE_APPLICATION_ERROR(-20001,'VECTOR_BUILD_BUSY'); END IF;",
                         [('p',pub,'VARCHAR2'),('lease',self.lease,'VARCHAR2')])
        count, reused, chain, batch = 0, 0, '0'*64, []
        try:
            def flush():
                nonlocal reused
                if not batch:
                    return
                old = self.existing(batch)
                reused += len(old)
                missing = [item for item in batch if item['id'] not in old]
                if ready and missing:
                    raise VectorError('VECTOR_BUILD: READY publication incomplete')
                if missing:
                    vectors = self.encoder.encode([item['text'] for item in missing])
                    self.insert_many(missing, vectors)
                    if len(self.existing(missing)) != len(missing):
                        raise VectorError('VECTOR_BUILD: committed rows missing')
                batch.clear()
                self.save({'status':'BUILDING','publication_id':pub,'seen':count,'reused':reused,
                           'embedding_calls':self.encoder.calls})
            for item in segments(self.request) if items is None else items:
                count += 1
                chain = digest([chain,item['id'],item['meta']])
                batch.append(item)
                if len(batch) == 16:
                    flush()
            flush()
            actual = int(self.sql.query(f'SELECT COUNT(*) AS N FROM {self.repo.s} WHERE PUB_ID=:p',
                                       [('p',pub,'VARCHAR2')],limit=1)[0]['N'])
            if actual != count or not count:
                raise VectorError('VECTOR_BUILD: incomplete/empty corpus')
            if not ready:
                self.execute(f"UPDATE {r} SET STATUS='READY',LEASE_ID=NULL "
                             "WHERE PUB_ID=:p AND LEASE_ID=:lease AND STATUS='BUILDING'; "
                             "IF SQL%ROWCOUNT<>1 THEN RAISE_APPLICATION_ERROR(-20002,'VECTOR_LEASE_LOST'); END IF;",
                             [('p',pub,'VARCHAR2'),('lease',self.lease,'VARCHAR2')])
            if activate:
                if expected:
                    if head['PUB_ID'] != pub:
                        self.execute(f'UPDATE {a} SET PUB_ID=:p,REVISION=REVISION+1 WHERE QUERY_ID=:q AND REVISION=:expected; '
                                     "IF SQL%ROWCOUNT<>1 THEN RAISE_APPLICATION_ERROR(-20003,'VECTOR_ACTIVE_CONFLICT'); END IF;",
                                     [('p',pub,'VARCHAR2'),('q',q,'VARCHAR2'),('expected',expected,'NUMBER')])
                else:
                    self.execute(f'INSERT INTO {a}(QUERY_ID,PUB_ID,REVISION) VALUES(:q,:p,1);',
                                 [('p',pub,'VARCHAR2'),('q',q,'VARCHAR2')])
            result = {'status':'READY','publication_id':pub,'query_release_id':q,'count':count,'chain':chain,
                      'reused':reused,'embedding_calls':self.encoder.calls,'active':activate,'previous':head}
            self.save(result)
            return result
        except BaseException as exc:
            self.save({'status':'FAILED','publication_id':pub,'seen':count,'reused':reused,
                       'embedding_calls':self.encoder.calls,'error_type':type(exc).__name__})
            raise
        finally:
            if not ready:
                self.execute(f'UPDATE {r} SET LEASE_ID=NULL WHERE PUB_ID=:p AND LEASE_ID=:lease;',
                             [('p',pub,'VARCHAR2'),('lease',self.lease,'VARCHAR2')])
