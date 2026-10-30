"""Small immutable review records and CAS heads; never a source/shortcut mirror.

The connection is an injected transactional port. Only the Oracle adapter is
provided for production. Tests supply their own ephemeral SQL connection.
"""
from ..contracts import canonical, digest, require

TABLES = ('lk_record', 'lk_head', 'lk_lookup')


class Repository:
    def __init__(self, db): self.db = db
    def transaction(self): return self.db.transaction()

    def read(self, namespace, key, revision=None):
        if revision is None:
            head = self.db.execute('SELECT revision FROM lk_head WHERE namespace=? AND object_id=?', (namespace, key)).fetchone()
            if head is None: return None
            revision = head['revision']
        row = self.db.execute('SELECT payload,content_hash FROM lk_record WHERE namespace=? AND object_id=? AND revision=?',
                              (namespace, key, revision)).fetchone()
        if row is None: return None
        import json
        try: value = json.loads(row['payload'])
        except (ValueError, TypeError): value = None
        require(isinstance(value, dict) and digest(value) == row['content_hash'] and value.get('id') == key
                and value.get('revision') == revision and value.get('namespace') == namespace,
                'KNOWLEDGE_INTEGRITY', '저장 항목의 무결성을 확인할 수 없습니다.', 409)
        return {**value, 'content_hash': row['content_hash']}

    def append(self, namespace, key, value, expected_revision):
        current = self.read(namespace, key)
        require((current['revision'] if current else 0) == expected_revision,
                'KNOWLEDGE_REVISION', '다른 변경이 있습니다. 최신 버전을 확인해 주세요.', 409)
        revision = expected_revision + 1
        record = {**value, 'namespace': namespace, 'id': key, 'revision': revision}
        self.db.execute('INSERT INTO lk_record(namespace,object_id,revision,tenant_id,team_id,payload,content_hash) VALUES(?,?,?,?,?,?,?)',
                        (namespace, key, revision, record['tenant_id'], record['team_id'], canonical(record), digest(record)))
        if current:
            changed = self.db.execute('UPDATE lk_head SET revision=? WHERE namespace=? AND object_id=? AND revision=?',
                                      (revision, namespace, key, expected_revision))
            require(changed.rowcount == 1, 'KNOWLEDGE_REVISION', '동시 변경 충돌입니다.', 409)
        else:
            self.db.execute('INSERT INTO lk_head(namespace,object_id,revision,tenant_id,team_id) VALUES(?,?,?,?,?)',
                            (namespace, key, revision, record['tenant_id'], record['team_id']))
        return {**record, 'content_hash': digest(record)}

    def page(self, namespace, who, after='', limit=24):
        rows = self.db.execute('SELECT object_id FROM lk_head WHERE namespace=? AND tenant_id=? AND team_id=? AND object_id>? '
                               'ORDER BY object_id FETCH FIRST '+str(limit)+' ROWS ONLY',
                               (namespace, who['tenant_id'], who['team_id'], after))
        return [self.read(namespace, r['object_id']) for r in rows]

    def index(self, release_id, records):
        for record in records:
            for term in sorted(set(t.casefold() for t in record['definition']['lookup_terms'])):
                self.db.execute('INSERT INTO lk_lookup(release_id,term,object_id,revision) VALUES(?,?,?,?)',
                                (release_id, term, record['id'], record['revision']))

    def candidates(self, release_id, query, limit=6):
        # Publication-time bounded terms; query stays a bind, never SQL syntax.
        rows = self.db.execute('SELECT object_id,revision FROM lk_lookup WHERE release_id=? '
                               'AND INSTR(?,term)>0 GROUP BY object_id,revision ORDER BY object_id '
                               'FETCH FIRST '+str(limit)+' ROWS ONLY', (release_id, query.casefold()[:6000]))
        return [self.read('definition', r['object_id'], r['revision']) for r in rows]
