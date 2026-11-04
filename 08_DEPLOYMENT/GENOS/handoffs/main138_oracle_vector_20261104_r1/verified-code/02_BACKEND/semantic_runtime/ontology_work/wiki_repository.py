"""Workspace SQL transactions reuse WORK/EVT/HEAD, including mapped Oracle ports."""
import json

from ..contracts import digest
from ..legal_agent.errors import ContractError


def workspace_bundle(bid):
    return isinstance(bid, str) and bid.startswith('cb-kb-ws-')


def bundle_scope(bid):
    return bid[len('cb-kb-ws-'):].split('-', 1)[0] if workspace_bundle(bid) else None


class WorkspaceTransactions:
    def _workspace_lock(self, c, bid):
        if self.lock(c, bid) is None:
            self.execute(c, f"INSERT INTO {self.tables['head']} VALUES (:1,NULL,0)", (bid,))

    def _workspace_expected(self, c, expected):
        for bid, pin in sorted(expected.items()):
            row = self.latest(bid, c)
            actual = {'revision': row['revision'], 'work_hash': row['work_hash']} if row else {'revision': 0, 'work_hash': None}
            if actual != pin:
                raise ContractError('stale workspace revision: ' + bid)

    def commit_workspace_change(self, *, catalog_id, operation_id, request_hash,
                                expected, writes, actor, withdraw=()):
        """All object hashes already exist in the content store; no S3 I/O here."""
        with self.session(True) as c:
            self._workspace_lock(c, catalog_id)
            old = self.latest(operation_id, c)
            if old:
                row = self.execute(c, f"SELECT EVT_JSON_CN FROM {self.tables['event']} WHERE EVT_ID=:1",
                                   (digest(['wiki-commit', operation_id]),)).fetchone()
                raw = row[0].read() if row and hasattr(row[0], 'read') else row[0] if row else None
                event = raw if isinstance(raw, dict) else json.loads(raw) if raw else None
                if not event or event['request_hash'] != request_hash or event.get('result_hash') != digest(event['result']):
                    raise ContractError('workspace operation ID reused with different input')
                return {**event['result'], 'reused': True}
            self._workspace_expected(c, expected)
            if set(writes) - expected.keys():
                raise ContractError('workspace write lacks expected revision')
            for bid in sorted(writes):
                if bid != catalog_id:
                    self._workspace_lock(c, bid)
                rev = expected[bid]['revision'] + 1
                self.execute(c, f"INSERT INTO {self.tables['work']} VALUES (:1,:2,:3,'DRAFT',NULL,NULL)",
                             (bid, rev, writes[bid]))
                self.event(c, bid, rev, 'WORKSPACE_CHANGED', actor, operation_id=operation_id, work_hash=writes[bid])
            for bid, pid in sorted(withdraw):
                head = self.lock(c, bid)
                if head and head[0] == pid:
                    self.execute(c, f"UPDATE {self.tables['head']} SET PUB_ID=NULL,CHG_SEQ_NO=CHG_SEQ_NO+1 WHERE BNDL_ID=:1", (bid,))
                    self.event(c, bid, 0, 'WORKSPACE_WITHDRAWN', actor, operation_id=operation_id, publication_id=pid)
            result = {'operation_id': operation_id, 'request_hash': request_hash,
                      'objects': {bid: {'revision': expected[bid]['revision'] + 1, 'work_hash': key}
                                  for bid, key in writes.items()}, 'reused': False}
            from .schema import now
            event = {'action': 'WORKSPACE_COMMIT', 'actor': actor, 'at': now(),
                     'request_hash': request_hash, 'result': result, 'result_hash': digest(result)}
            self.execute(c, f"INSERT INTO {self.tables['event']} VALUES (:1,:2,1,:3)",
                         (digest(['wiki-commit', operation_id]), operation_id, json.dumps(event, ensure_ascii=False)))
            return result

    def activate_workspace(self, *, catalog_id, expected, writes, bid, pid,
                           expected_sequence, receipt_id, binding, actor, rollback=False):
        with self.session(True) as c:
            self._workspace_lock(c, catalog_id)
            self._workspace_expected(c, expected)
            result = self._activate_staged(c, bid, pid, expected_sequence, receipt_id, binding, actor, rollback=rollback)
            for key in sorted(writes):
                if key not in expected:
                    raise ContractError('workspace activation CAS missing')
                self._workspace_lock(c, key)
                rev = expected[key]['revision'] + 1
                self.execute(c, f"INSERT INTO {self.tables['work']} VALUES (:1,:2,:3,'DRAFT',NULL,NULL)", (key, rev, writes[key]))
                self.event(c, key, rev, 'WORKSPACE_PUBLICATION_DEPENDENCIES', actor, publication_id=pid, work_hash=writes[key])
            return result

    def workspace_visible(self, bid):
        return not workspace_bundle(bid) or bundle_scope(bid) in getattr(self, 'workspace_scopes', frozenset())

    def current_publications(self, references, allowed_documents):
        """Current authority is SQL, never a cached request package or draft index."""
        if len(references) > 8:
            raise ContractError('workspace publication bound')
        result = {ref['publication_id']:False for ref in references}
        visible=[ref for ref in references if self.workspace_visible(ref['bundle_id'])]
        if not visible:return result
        with self.session() as c:
            # One current-authority read; no cache survives revocation.
            binds=[];conditions=[]
            for ref in visible:
                n=len(binds)+1;conditions.append(f'(p.PUB_ID=:{n} AND p.BNDL_ID=:{n+1})')
                binds.extend((ref['publication_id'],ref['bundle_id']))
            rows=self.execute(c,f"SELECT p.PUB_ID,p.BNDL_ID,p.PKG_HASH_VAL,a.DOC_ID FROM {self.tables['publication']} p JOIN {self.tables['head']} h ON h.PUB_ID=p.PUB_ID AND h.BNDL_ID=p.BNDL_ID JOIN {self.tables['anchor']} a ON a.PUB_ID=p.PUB_ID WHERE "+' OR '.join(conditions),tuple(binds)).fetchmany(1025)
            if len(rows)>1024:raise ContractError('workspace publication anchor bound')
            grouped={}
            for pid,bid,sha,did in rows:grouped.setdefault((pid,bid),[]).append((sha,did))
            for ref in visible:
                items=grouped.get((ref['publication_id'],ref['bundle_id']),[])
                result[ref['publication_id']]=bool(items and len(items)<=128
                    and all(sha==ref['package_sha256'] for sha,did in items)
                    and {did for sha,did in items}<=set(allowed_documents))
        return result
