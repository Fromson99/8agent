"""Bounded Dataiku SQL batches over the shared six-column publisher."""
import json
from lawrag.pipeline.oracle_query_dataiku import render
from semantic_runtime.initial_vector import VectorError, vector_sql, LEASE, STATUS
from semantic_runtime.vector_publish import Publisher as BasePublisher

class Publisher(BasePublisher):
    sql_bytes = 60000

    def insert_many(self, missing, vectors):
        statements, binds = [], []
        def flush():
            if statements:
                self.execute(' '.join(statements), binds)
                statements.clear()
                binds.clear()
        for i, (item, vector) in enumerate(zip(missing, vectors, strict=True)):
            names = {k: k + str(i) for k in ('p','id','meta','lease')}
            m = item['meta']
            values = [self.pub, item['id'], json.dumps(m), self.lease]
            additions = [(names[k], v, 'CLOB' if k == 'meta' else 'VARCHAR2')
                         for k, v in zip(names, values)]
            n = {k: ':' + v for k, v in names.items()}
            expr = vector_sql(vector, self.profile['dimensions'])
            statement = (
                f'INSERT INTO {self.repo.s}(PUB_ID,SEG_ID,META_JSON,EMBEDDING) '
                f'SELECT {n["p"]},{n["id"]},{n["meta"]},{expr} '
                f'FROM {self.repo.r} WHERE PUB_ID={n["p"]} AND {LEASE}={n["lease"]} AND {STATUS}=\'BUILDING\'; '
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

