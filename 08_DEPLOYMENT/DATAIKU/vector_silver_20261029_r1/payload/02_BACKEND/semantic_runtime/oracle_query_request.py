"""One request's pinned Oracle source, index, state, and shared SQL budget.

The caller is responsible for deriving document_ids from the authenticated
team/principal. A client-supplied list is never an authorization grant.
"""
from __future__ import annotations

from dataclasses import dataclass

from .oracle_dp_io import DPError, KEYS, digest
from .oracle_query import Snapshot
from .oracle_query_catalog import Records, select_release
from .oracle_query_state import State, StateSQL


@dataclass
class Request:
    sql: StateSQL
    release_id: str
    pointer_revision: int | None
    snapshot: Snapshot
    sources: object
    records: Records

    def state(self, scope_hash):
        return State(self.sql, scope_hash=scope_hash)

    def restrict(self, document_ids):
        allowed=frozenset(document_ids)
        if not allowed <= self.sources.allowed:
            raise DPError('QUERY_SCOPE: cannot widen a pinned request')
        return _request(self.sql, self.release_id, self.pointer_revision,
                        self.snapshot, self.records.manifest, allowed)


def open_request(client, *, connection_binding, document_ids, deadline,
                 release_id=None, channel=None, max_calls=1000):
    sql = StateSQL(client, binding=connection_binding, deadline=deadline, max_calls=max_calls)
    selected = select_release(sql, release_id=release_id, channel=channel)
    manifest = selected['manifest']
    snapshot = Snapshot.open(sql, manifest['source_release_id'])
    if (manifest['dataset_version'] != snapshot.dataset_version or
            manifest['source_manifest'] != snapshot.manifest or 'source.integrity' not in manifest['tables']):
        raise DPError('QUERY_SOURCE_BINDING: query release has no matching verified source projection')
    return _request(sql, selected['release_id'], selected['revision'], snapshot, manifest, document_ids)


def _request(sql, release_id, revision, snapshot, manifest, document_ids):
    def verify(kind, rows):
        if not rows:
            return
        expected = {}
        for row in rows:
            key = [row[c] for c in KEYS[kind]]
            lookup = digest([kind,key])
            expected[lookup] = {'source_kind': kind, 'source_key': key, 'source_sha256': digest(row)}
        result = records.page('source.integrity', lookup_ids=list(expected), limit=len(expected))
        actual = {digest([value['source_kind'],value['source_key']]): value for value in result['rows']}
        if len(actual) != len(result['rows']) or actual != expected:
            raise DPError('QUERY_SOURCE_HASH: requested Oracle source differs from published immutable rows')

    sources = snapshot.reader(sql, document_ids=document_ids, verify_rows=verify)
    records = Records(sql, release_id, manifest, document_ids=sources.allowed)
    return Request(sql, release_id, revision, snapshot, sources, records)
