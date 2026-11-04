"""External Oracle request state with optimistic revisions and no local spool.

This port stores small request/session objects; it must not be used to persist
a whole source database. Consumers own their state schema and budget policy.
An ambiguous write is never retried automatically or reported as success.
"""
from __future__ import annotations

import json
import re
import time

from .oracle_dp_assets import clob_text
from .oracle_dp_io import DPError, BudgetPause, SQL, digest, canonical
from .oracle_query import QuerySQL, MAX_RESPONSE_BYTES
from .oracle_query_catalog import STATE, pin, json_body
from .physical_mapping import names


class StateConflict(DPError):
    pass


class StateSQL(QuerySQL):
    """Request-budgeted writes used only by the state port below."""
    def request(self, statement, binds=(), *, write=False, limit=100):
        if not write:
            return super().request(statement, binds, limit=limit)
        # Restrict this transport to our state table and transaction forms.
        # Query text is maintained code; no LLM/user SQL is accepted by the API.
        table=names(self,'query_state',STATE).table
        if table not in statement or not statement.startswith(('DECLARE ', 'BEGIN ')):
            raise DPError('STATE_SQL: only maintained state transactions are accepted')
        result = SQL.request(self, statement, binds, write=True, limit=limit)
        if time.monotonic() >= self.deadline:
            raise BudgetPause('STATE_WRITE_UNCONFIRMED: deadline passed; reconcile persisted revision')
        if len(canonical(result).encode()) > MAX_RESPONSE_BYTES:
            raise DPError('STATE_WRITE_UNCONFIRMED: oversized acknowledgement; reconcile persisted revision')
        return result


class State:
    def __init__(self, sql, *, scope_hash):
        self.sql, self.scope_hash = sql, pin(scope_hash)

    def _binds(self, key):
        if not isinstance(key, str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}', key):
            raise DPError('STATE_KEY: invalid state key')
        return [('scope', self.scope_hash, 'VARCHAR2'), ('key', key, 'VARCHAR2')]

    def read(self, key):
        binds = self._binds(key)
        n=names(self.sql,'query_state',STATE)
        where = n.c('SCOPE_HASH')+'=:scope AND '+n.c('STATE_KEY')+'=:key'
        rows = self.sql.query(f"SELECT {n.select('REVISION','VALUE_SHA256')},TO_CLOB({n.c('VALUE_JSON')}) AS VALUE,DBMS_LOB.GETLENGTH({n.c('VALUE_JSON')}) AS N "
                              f'FROM {n.table} WHERE '+where, binds, limit=1)
        if not rows:
            return None
        row = rows[0]
        if type(row['REVISION']) is not int or row['REVISION'] < 1:
            raise DPError('STATE_REVISION: invalid stored revision')
        body = row['VALUE']
        if not isinstance(body, str) or len(body.encode('utf-16-le'))//2 != row['N']:
            # Include revision/hash in every CLOB chunk lookup. A concurrent
            # commit cannot splice old metadata with a new object's body.
            body = clob_text(self.sql, n.table, n.c('VALUE_JSON'), where+' AND '+n.c('REVISION')+'=:revision AND '+n.c('VALUE_SHA256')+'=:hash',
                             [*binds,('revision',row['REVISION'],'NUMBER'),('hash',row['VALUE_SHA256'],'VARCHAR2')])
        if body is None:
            raise StateConflict('STATE_READ_CONFLICT: revision changed during read')
        value = json.loads(body)
        expected = digest({'scope_hash': self.scope_hash, 'key': key, 'revision': row['REVISION'], 'value': value})
        if pin(row['VALUE_SHA256']) != expected:
            raise DPError('STATE_HASH: stored scope/key/revision/value binding differs')
        return {'revision': row['REVISION'], 'sha256': expected, 'value': value}

    def put(self, key, value, *, expected_revision):
        """Create/update one object atomically, or reconcile this exact update."""
        binds = self._binds(key)
        if type(expected_revision) is not int or expected_revision < 0:
            raise DPError('STATE_REVISION: nonnegative expected revision required')
        body = json_body(value)
        revision = expected_revision + 1
        sha = digest({'scope_hash': self.scope_hash, 'key': key, 'revision': revision, 'value': value})
        target = {'revision': revision, 'sha256': sha, 'value': value}
        current = self.read(key)
        if current == target:
            return {**target, 'reconciled': True}
        if (current is None and expected_revision != 0) or (current is not None and current['revision'] != expected_revision):
            raise StateConflict('STATE_CONFLICT: retain current state and reload its revision')
        binds += [('revision', revision, 'NUMBER'), ('hash', sha, 'VARCHAR2'), ('body', body, 'CLOB')]
        n=names(self.sql,'query_state',STATE)
        if current is None:
            operation = (f"INSERT INTO {n.table}({','.join(n.c(c) for c in ('SCOPE_HASH','STATE_KEY','REVISION','VALUE_SHA256','VALUE_JSON'))}) "
                         'VALUES(:scope,:key,:revision,:hash,:body);')
        else:
            binds += [('previous', expected_revision, 'NUMBER'), ('previous_hash', current['sha256'], 'VARCHAR2')]
            operation = (f"UPDATE {n.table} SET {n.c('REVISION')}=:revision,{n.c('VALUE_SHA256')}=:hash,{n.c('VALUE_JSON')}=:body "
                         f"WHERE {n.c('SCOPE_HASH')}=:scope AND {n.c('STATE_KEY')}=:key AND {n.c('REVISION')}=:previous AND {n.c('VALUE_SHA256')}=:previous_hash; "
                         "IF SQL%ROWCOUNT<>1 THEN RAISE_APPLICATION_ERROR(-20033,'STATE_CONFLICT'); END IF;")
        self.sql.request('BEGIN '+operation+' COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;', binds, write=True)
        if self.read(key) != target:
            raise StateConflict('STATE_WRITE_UNCONFIRMED: read back the current revision before resuming')
        return {**target, 'reconciled': False}


def assert_resume(previous, proposed):
    """Immutable request binding/deadline; cumulative budget can only increase."""
    if not isinstance(previous, dict) or not isinstance(proposed, dict):
        raise DPError('STATE_CONTRACT: request state must be an object')
    for field in ('request_id', 'binding_hash', 'deadline_at'):
        if field not in previous or proposed.get(field) != previous[field]:
            raise StateConflict('STATE_BINDING: resume changed '+field)
    before, after = previous.get('usage'), proposed.get('usage')
    if not isinstance(before, dict) or not isinstance(after, dict) or set(before) != set(after):
        raise DPError('STATE_BUDGET: cumulative usage keys differ')
    for key in before:
        if type(before[key]) is not int or type(after[key]) is not int or not 0 <= before[key] <= after[key]:
            raise DPError('STATE_BUDGET: cumulative usage cannot decrease')
