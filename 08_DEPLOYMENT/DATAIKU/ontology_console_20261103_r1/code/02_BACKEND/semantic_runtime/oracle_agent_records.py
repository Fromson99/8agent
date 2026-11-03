"""Oracle-authoritative Agent records, immutable bodies and fenced transactions.

No filesystem IO, schema creation, source mirror or automatic write retry.
Only maintained SQL is accepted. Values, identities and payloads are binds.
The existing STATE hash/revision contract remains unchanged.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import re
import time
import uuid
import zlib

from .oracle_dp_io import SQL, DPError, BudgetPause, canonical, digest
from .oracle_query_state import StateSQL, StateConflict
from . import oracle_progress_body as progress

OWNER = 'SIDDA'
BODY = OWNER + '.LGL_AGT_BODY_A'
RECORD = OWNER + '.LGL_AGT_REC_A'
RUN = OWNER + '.LGL_AGT_RUN_A'
STATE = OWNER + '.LGL_EXEC_ST_A'
CHUNK_BYTES = 2048  # ASCII part envelope remains below Oracle VARCHAR2(4000 BYTE).
LAYOUT = 3
ACTIVE_LEASES = ContextVar('oracle_agent_leases', default=())
UTC_SECONDS = "((CAST(SYSTIMESTAMP AT TIME ZONE 'UTC' AS DATE)-DATE '1970-01-01')*86400)"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise DPError('AGENT_HASH: expected lowercase SHA256')
    return value


class RecordSQL(StateSQL):
    def mutate(self, statement, binds):
        if not statement.startswith(('DECLARE ', 'BEGIN ')) or not any(t in statement for t in (BODY, RECORD, STATE)):
            raise DPError('AGENT_SQL: maintained Agent transaction required')
        value = SQL.request(self, statement, binds, write=True, limit=1)
        if time.monotonic() >= self.deadline:
            raise BudgetPause('AGENT_WRITE_UNCONFIRMED: reconcile operation before continuing')
        return value


class AgentRecords:
    def __init__(self, sql, *, namespace='genos-rag'):
        if not isinstance(namespace, str) or not namespace or len(namespace.encode()) > 128:
            raise DPError('AGENT_NAMESPACE: nonempty bounded operator namespace required')
        self.sql = sql
        self.scope = digest({'format': 'oracle-agent-namespace-v1', 'namespace': namespace})
        self.verified_bodies = {}

    def _query(self, text, binds=(), *, limit=100):
        return self.sql.query(text, [('scope', self.scope, 'VARCHAR2'), *binds], limit=limit)

    def _mutate(self, text, binds=()):
        return self.sql.mutate(text, [('scope', self.scope, 'VARCHAR2'), *binds])

    def preflight(self):
        h='VARCHAR2:64';n='NUMBER:18';t='TIMESTAMP WITH TIME ZONE'
        expected={
            BODY:{'SCOPE_HASH_VAL':h,'BODY_HASH_VAL':h,'PART_SEQ_NO':n,'PART_JSON_CN':'CLOB'},
            RECORD:{'SCOPE_HASH_VAL':h,'OWNER_KEY_HASH_VAL':h,'REC_KIND_CD':'VARCHAR2:64','REC_KEY_HASH_VAL':h,
                    'REC_REV_NO':n,'ORD_SEQ_NO':n,'LOOKUP_HASH_VAL':h,'BODY_HASH_VAL':h},
            RUN:{'SCOPE_HASH_VAL':h,'RUN_KEY_HASH_VAL':h,'SESS_KEY_HASH_VAL':h,'REQ_KEY_HASH_VAL':h,'PRNT_RUN_KEY_HASH_VAL':h,
                 'ST_CD':'VARCHAR2:32','STRT_DTTM':t,'CHG_DTTM':t,'BODY_HASH_VAL':h},
            STATE:{'SCOPE_HASH_VAL':h,'ST_KEY_ID':'VARCHAR2:128','CHG_SEQ_NO':n,'ST_HASH_VAL':h,'ST_JSON_CN':'CLOB'}}
        nullable={'SESS_KEY_HASH_VAL','PRNT_RUN_KEY_HASH_VAL','LOOKUP_HASH_VAL'}
        pks={BODY:['SCOPE_HASH_VAL','BODY_HASH_VAL','PART_SEQ_NO'],
             RECORD:['SCOPE_HASH_VAL','OWNER_KEY_HASH_VAL','REC_KIND_CD','REC_KEY_HASH_VAL','REC_REV_NO'],
             RUN:['SCOPE_HASH_VAL','RUN_KEY_HASH_VAL'],STATE:['SCOPE_HASH_VAL','ST_KEY_ID']}
        for table, columns in expected.items():
            name = table.split('.')[1]
            found = self.sql.query('SELECT COLUMN_NAME,DATA_TYPE,DATA_LENGTH,DATA_PRECISION,DATA_SCALE,CHAR_USED,NULLABLE '
                                   'FROM ALL_TAB_COLUMNS WHERE OWNER=:owner AND TABLE_NAME=:name ORDER BY COLUMN_ID',
                                   [('owner', OWNER, 'VARCHAR2'), ('name', name, 'VARCHAR2')], limit=100)
            if {r['COLUMN_NAME'] for r in found} != set(columns):
                raise DPError('AGENT_SCHEMA: create/verify ' + table + ' using the Dataiku SQL package')
            for r in found:
                want=columns[r['COLUMN_NAME']];typ=r['DATA_TYPE']
                if want.startswith('VARCHAR2:'):
                    ok=typ=='VARCHAR2' and r['DATA_LENGTH']==int(want.split(':')[1]) and r['CHAR_USED']=='B'
                elif want.startswith('NUMBER:'):
                    ok=typ=='NUMBER' and r['DATA_PRECISION']==18 and r['DATA_SCALE']==0
                elif want==t:ok=typ in (t,'TIMESTAMP(6) WITH TIME ZONE') and r['DATA_SCALE']==6
                else:ok=typ==want
                if not ok or r['NULLABLE']!=('Y' if r['COLUMN_NAME'] in nullable else 'N'):
                    raise DPError('AGENT_SCHEMA_TYPE: '+table+'.'+r['COLUMN_NAME'])
            keys=self.sql.query('SELECT K.COLUMN_NAME FROM ALL_CONSTRAINTS C JOIN ALL_CONS_COLUMNS K '
                'ON C.OWNER=K.OWNER AND C.CONSTRAINT_NAME=K.CONSTRAINT_NAME '
                "WHERE C.OWNER=:owner AND C.TABLE_NAME=:name AND C.CONSTRAINT_TYPE='P' AND C.STATUS='ENABLED' ORDER BY K.POSITION",
                [('owner',OWNER,'VARCHAR2'),('name',name,'VARCHAR2')],limit=100)
            if [r['COLUMN_NAME'] for r in keys]!=pks[table]:raise DPError('AGENT_SCHEMA_PK: '+table)
        return {'owner': OWNER, 'tables': 4, 'user_columns': 26, 'state_storage': 'oracle', 'persistent_sqlite': False}

    def state(self, key):
        found = self._query(f'SELECT CHG_SEQ_NO,ST_HASH_VAL,DBMS_LOB.SUBSTR(ST_JSON_CN,4000,1) AS VALUE '
                            f'FROM {STATE} WHERE SCOPE_HASH_VAL=:scope AND ST_KEY_ID=:key', [('key', key, 'VARCHAR2')], limit=1)
        if not found:
            return None
        row = found[0]
        value = json.loads(row['VALUE'])
        revision = row['CHG_SEQ_NO']
        expected = digest({'scope_hash': self.scope, 'key': key, 'revision': revision, 'value': value})
        if expected != row['ST_HASH_VAL'] or type(revision) is not int or revision < 1:
            raise DPError('AGENT_STATE_HASH: stored state binding differs')
        return {'revision': revision, 'sha256': expected, 'value': value}

    def _state_value(self, key, revision, value):
        text = canonical(value)
        if len(text.encode()) > 3500:
            raise DPError('AGENT_STATE_SIZE: keep only small pointers in STATE')
        return {'key': key, 'revision': revision, 'hash': digest({'scope_hash': self.scope, 'key': key, 'revision': revision, 'value': value}), 'json': text}

    def rows(self, owner, *, kind=None):
        pin(owner); after_kind = ''; after_key = ''; result = []
        while True:
            where = ' AND REC_KIND_CD=:kind' if kind else ''
            binds = [('owner', owner, 'VARCHAR2'), ('after_kind', after_kind, 'VARCHAR2'), ('after_key', after_key, 'VARCHAR2')]
            # Oracle treats empty VARCHAR2 as NULL; use the explicit first-page flag.
            binds.append(('first_page', int(not result), 'NUMBER'))
            if kind:
                binds.append(('kind', kind, 'VARCHAR2'))
            page = self._query(f'SELECT * FROM (SELECT REC_KIND_CD,REC_KEY_HASH_VAL,REC_REV_NO,ORD_SEQ_NO,LOOKUP_HASH_VAL,BODY_HASH_VAL '
                f'FROM {RECORD} WHERE SCOPE_HASH_VAL=:scope AND OWNER_KEY_HASH_VAL=:owner AND REC_REV_NO=0' + where +
                ' AND (:first_page=1 OR REC_KIND_CD>:after_kind OR (REC_KIND_CD=:after_kind AND REC_KEY_HASH_VAL>:after_key)) '
                'ORDER BY REC_KIND_CD,REC_KEY_HASH_VAL) WHERE ROWNUM<=100', binds)
            result.extend(page)
            if len(page) < 100:
                return result
            after_kind, after_key = page[-1]['REC_KIND_CD'], page[-1]['REC_KEY_HASH_VAL']

    def exact(self, owner, kind, key, *, revision=0):
        found = self._query(f'SELECT BODY_HASH_VAL,ORD_SEQ_NO,LOOKUP_HASH_VAL FROM {RECORD} '
            'WHERE SCOPE_HASH_VAL=:scope AND OWNER_KEY_HASH_VAL=:owner AND REC_KIND_CD=:kind '
            'AND REC_KEY_HASH_VAL=:key AND REC_REV_NO=:revision',
            [('owner', pin(owner), 'VARCHAR2'), ('kind', kind, 'VARCHAR2'), ('key', pin(key), 'VARCHAR2'), ('revision', revision, 'NUMBER')], limit=1)
        return found[0] if found else None

    def _parts(self, hashes):
        gathered = {h: {} for h in hashes}
        ordered = sorted(hashes)
        for offset in range(0, len(ordered), 50):
            group = ordered[offset:offset + 50]; after_hash = ''; after_part = -1; first = True
            while True:
                page = self._query(f'SELECT * FROM (SELECT B.BODY_HASH_VAL,B.PART_SEQ_NO,DBMS_LOB.SUBSTR(B.PART_JSON_CN,4000,1) AS PART '
                    f"FROM {BODY} B JOIN JSON_TABLE(:hashes,'$[*]' COLUMNS(HASH VARCHAR2(64) PATH '$')) J ON J.HASH=B.BODY_HASH_VAL "
                    'WHERE B.SCOPE_HASH_VAL=:scope AND (:first_page=1 OR B.BODY_HASH_VAL>:after_hash OR '
                    '(B.BODY_HASH_VAL=:after_hash AND B.PART_SEQ_NO>:after_part)) ORDER BY B.BODY_HASH_VAL,B.PART_SEQ_NO) WHERE ROWNUM<=100',
                    [('hashes', canonical(group), 'CLOB'), ('first_page', int(first), 'NUMBER'),
                     ('after_hash', after_hash, 'VARCHAR2'), ('after_part', after_part, 'NUMBER')])
                for row in page:
                    text = row['PART']
                    if not isinstance(text, str) or len(text.encode()) > 4000:
                        raise DPError('AGENT_BODY_PART: incomplete envelope')
                    gathered[row['BODY_HASH_VAL']][row['PART_SEQ_NO']] = json.loads(text)
                if len(page) < 100: break
                after_hash, after_part = page[-1]['BODY_HASH_VAL'], page[-1]['PART_SEQ_NO']; first = False
        return gathered

    @staticmethod
    def _stored_body(key, parts):
        manifest = parts.get(0)
        if not isinstance(manifest, dict) or manifest.get('layout_version') not in (2, 3, 4) or manifest.get('body_sha256') != key:
            raise DPError('AGENT_BODY_INCOMPLETE: complete matching manifest required')
        count = manifest.get('part_count')
        if type(count) is not int or count < 1 or set(parts) != set(range(count + 1)):
            raise DPError('AGENT_BODY_INCOMPLETE: missing or extra parts')
        raw = bytearray()
        for i in range(1, count + 1):
            item = parts[i]; packed = base64.b64decode(item['data_base64'], validate=True)
            if sha(packed) != item['stored_sha256']:
                raise DPError('AGENT_BODY_HASH: stored part differs')
            if manifest['layout_version'] in (3, 4):
                raw.extend(packed); continue
            codec = item['codec']
            if codec not in ('RAW_BASE64', 'ZLIB_BASE64'):
                raise DPError('AGENT_BODY_CODEC: unsupported codec')
            decoded = zlib.decompress(packed) if codec == 'ZLIB_BASE64' else packed
            if len(decoded) != item['raw_bytes'] or sha(decoded) != item['raw_sha256']:
                raise DPError('AGENT_BODY_HASH: decoded part differs')
            raw.extend(decoded)
        if manifest['layout_version'] in (3, 4):
            if len(raw) != manifest['stored_bytes'] or sha(raw) != manifest['stored_sha256']:
                raise DPError('AGENT_BODY_HASH: complete stored bytes differ')
            codec = manifest['codec']
            if codec == 'ZLIB_BASE64':
                unpack = zlib.decompressobj()
                limit = manifest.get('recipe_bytes') if manifest['layout_version'] == 4 else manifest['total_bytes']
                if type(limit) is not int or limit < 0 or (manifest['layout_version'] == 4 and limit > progress.MAX_REFS * 68 + 2):
                    raise DPError('AGENT_BODY_SIZE: bounded progress recipe required')
                result = unpack.decompress(raw, limit + 1)
                if not unpack.eof or unpack.unused_data or unpack.unconsumed_tail:
                    raise DPError('AGENT_BODY_HASH: incomplete or oversized compressed body')
                raw = result
            elif codec != 'RAW_BASE64':
                raise DPError('AGENT_BODY_CODEC: unsupported codec')
        if manifest['layout_version'] != 4 and (len(raw) != manifest['total_bytes'] or sha(raw) != key):
            raise DPError('AGENT_BODY_HASH: complete bytes differ')
        return manifest, bytes(raw)

    @staticmethod
    def _decode_body(key, parts, resolve=None):
        manifest, raw = AgentRecords._stored_body(key, parts)
        return progress.restore(key, manifest, raw, resolve) if manifest['layout_version'] == 4 else raw

    def bodies(self, hashes):
        wanted = set(map(pin, hashes)); attempted = set(); graph = {}
        pending = wanted - self.verified_bodies.keys()
        while pending:
            attempted.update(pending)
            if len(attempted) > progress.MAX_REFS:
                raise DPError('AGENT_PROGRESS_REFS: checkpoint graph exceeds bound')
            needed = set()
            for key, parts in self._parts(pending).items():
                if not parts: continue
                manifest, raw = self._stored_body(key, parts)
                if manifest['layout_version'] == 4:
                    refs = progress.references(manifest, raw); graph[key] = (manifest, raw)
                    needed.update(refs)
                else: self.verified_bodies[key] = raw
            pending = needed - self.verified_bodies.keys() - attempted
        def resolve(key, ancestors=()):
            if key in ancestors or len(ancestors) >= 64:
                raise DPError('AGENT_PROGRESS_REFS: cyclic or oversized checkpoint graph')
            if key not in self.verified_bodies:
                if key not in graph: raise DPError('AGENT_BODY_MISSING: referenced checkpoint leaf unavailable')
                manifest, raw = graph[key]
                value = progress.restore(key, manifest, raw, lambda h: resolve(h, (*ancestors, key)))
                self.verified_bodies[key] = value
            return self.verified_bodies[key]
        for key in wanted & graph.keys(): resolve(key)
        return {key: self.verified_bodies[key] for key in wanted if key in self.verified_bodies}

    def body(self, key):
        found = self.bodies([key])
        if key not in found:
            raise DPError('AGENT_BODY_MISSING: exact referenced body is unavailable')
        return found[key]

    @staticmethod
    def _encode_body(raw, *, layout=LAYOUT):
        key = sha(raw); envelopes = []
        if layout == 3:
            compressed = zlib.compress(raw, 6)
            codec, packed = ('ZLIB_BASE64', compressed) if len(compressed) < len(raw) else ('RAW_BASE64', raw)
            chunks = [packed[i:i + CHUNK_BYTES] for i in range(0, len(packed), CHUNK_BYTES)] or [b'']
            for i, chunk in enumerate(chunks, 1):
                envelopes.append({'hash': key, 'seq': i, 'json': {'stored_sha256': sha(chunk), 'data_base64': base64.b64encode(chunk).decode()}})
            manifest = {'layout_version': 3, 'body_sha256': key, 'total_bytes': len(raw), 'part_count': len(chunks),
                        'codec': codec, 'stored_bytes': len(packed), 'stored_sha256': sha(packed)}
        else:
            # Finish an interrupted legacy v2 upload without replacing old parts.
            chunks = [raw[i:i + CHUNK_BYTES] for i in range(0, len(raw), CHUNK_BYTES)] or [b'']
            for i, chunk in enumerate(chunks, 1):
                compressed = zlib.compress(chunk, 6)
                codec, packed = ('ZLIB_BASE64', compressed) if len(compressed) < len(chunk) else ('RAW_BASE64', chunk)
                envelopes.append({'hash': key, 'seq': i, 'json': {'codec': codec, 'raw_bytes': len(chunk), 'raw_sha256': sha(chunk),
                    'stored_sha256': sha(packed), 'data_base64': base64.b64encode(packed).decode()}})
            manifest = {'layout_version': 2, 'body_sha256': key, 'total_bytes': len(raw), 'part_count': len(chunks)}
        if any(len(canonical(row['json']).encode()) > 4000 for row in envelopes):
            raise DPError('AGENT_BODY_SIZE: part envelope exceeds bounded SQL projection')
        return envelopes, {'hash': key, 'seq': 0, 'json': manifest}

    def put_bodies(self, values):
        requested = {sha(raw): raw for raw in values if sha(raw) not in self.verified_bodies}
        if not requested: return
        expanded, recipes = progress.plan(requested)
        pending = {h: raw for h, raw in expanded.items() if h not in self.verified_bodies}
        prior = self._parts(pending)
        complete = [h for h, parts in prior.items() if 0 in parts]
        for key, restored in self.bodies(complete).items():
            if restored != pending[key]: raise DPError('AGENT_BODY_COLLISION: existing body differs')
        # A data-first upload without a manifest keeps its original representation.
        for key in list(recipes):
            parts = prior.get(key, {})
            if key in self.verified_bodies or (parts and not any(p.get('layout_version') == 4 for p in parts.values())):
                recipes.pop(key)
        needed = set(requested)
        for recipe in recipes.values(): needed.update(json.loads(recipe))
        pending = {h: raw for h, raw in pending.items() if h in needed and h not in self.verified_bodies}
        if not pending: return
        envelopes = []; manifests = []
        for key, raw in pending.items():
            existing = prior.get(key, {})
            is_progress = key in recipes
            if any(p.get('layout_version') == 4 for p in existing.values()) and not is_progress:
                raise DPError('AGENT_BODY_INCOMPLETE: original progress recipe required to finish upload')
            layout = 2 if any('raw_bytes' in p for p in existing.values()) else 3
            parts, manifest = self._encode_body(recipes[key] if is_progress else raw, layout=layout)
            if is_progress:
                for part in parts:
                    part['hash'] = key; part['json']['layout_version'] = 4
                manifest['hash'] = key
                manifest['json'].update(layout_version=4, body_sha256=key, total_bytes=len(raw),
                    recipe_bytes=len(recipes[key]), recipe_sha256=sha(recipes[key]))
            envelopes.extend(parts); manifests.append(manifest)
        # Complete leaf manifests before publishing any root; interrupted roots
        # can never appear complete while their dependencies are uncommitted.
        manifests.sort(key=lambda m: (m['hash'] in recipes, m['hash']))
        statement = ("DECLARE v_old CLOB; v_same NUMBER; BEGIN FOR r IN (SELECT h,n,j FROM JSON_TABLE(:parts,'$[*]' "
            "COLUMNS(h VARCHAR2(64) PATH '$.hash',n NUMBER PATH '$.seq',j CLOB FORMAT JSON PATH '$.json'))) LOOP "
            f'BEGIN INSERT INTO {BODY}(SCOPE_HASH_VAL,BODY_HASH_VAL,PART_SEQ_NO,PART_JSON_CN) VALUES(:scope,r.h,r.n,r.j); '
            f'EXCEPTION WHEN DUP_VAL_ON_INDEX THEN SELECT PART_JSON_CN INTO v_old FROM {BODY} '
            'WHERE SCOPE_HASH_VAL=:scope AND BODY_HASH_VAL=r.h AND PART_SEQ_NO=r.n; '
            "SELECT CASE WHEN JSON_EQUAL(v_old,r.j) THEN 1 ELSE 0 END INTO v_same FROM DUAL; "
            "IF v_same<>1 THEN RAISE_APPLICATION_ERROR(-20041,'AGENT_BODY_COLLISION'); END IF; END; END LOOP; "
            'COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
        for batch in (envelopes, [m for m in manifests if m['hash'] not in recipes],
                      [m for m in manifests if m['hash'] in recipes]):
            for offset in range(0, len(batch), 100):
                self._mutate(statement, [('parts', canonical(batch[offset:offset + 100]), 'CLOB')])
        checked = self.bodies(pending)
        if checked != pending:
            raise DPError('AGENT_BODY_WRITE_UNCONFIRMED: exact bytes not reconciled')

    def operation(self, owner, key):
        return self.exact(owner, 'OPERATION', key, revision=1)

    def commit(self, owner, expected, value, changes, *, run=None, bodies=()):
        """Immutable row versions/current projections/head/receipt in one commit."""
        pin(owner)
        head_key = 'a1:head:' + owner
        revision = expected + 1
        operation = digest({'owner': owner, 'expected': expected, 'value': value, 'changes': changes, 'run': run})
        receipt = canonical({'operation': operation, 'owner': owner, 'revision': revision, 'head': value}).encode()
        self.put_bodies([*bodies, receipt])
        state = self._state_value(head_key, revision, value)
        payload = {'owner': owner, 'expected': expected, 'head': state, 'rows': changes, 'operation': operation,
                   'receipt_hash': sha(receipt), 'leases': list(ACTIVE_LEASES.get()), 'run': run}
        statement = ('DECLARE v_revision NUMBER; v_token VARCHAR2(64); v_expiry NUMBER; v_exists NUMBER; v_run_id VARCHAR2(64); BEGIN '
            f'SELECT COUNT(*) INTO v_exists FROM {RECORD} WHERE SCOPE_HASH_VAL=:scope AND OWNER_KEY_HASH_VAL=:owner '
            "AND REC_KIND_CD='OPERATION' AND REC_KEY_HASH_VAL=:operation AND REC_REV_NO=1; "
            'IF v_exists=0 THEN '
            f'IF :expected=0 THEN BEGIN INSERT INTO {STATE}(SCOPE_HASH_VAL,ST_KEY_ID,CHG_SEQ_NO,ST_HASH_VAL,ST_JSON_CN) '
            'VALUES(:scope,:head_key,:revision,:head_hash,:head_json); EXCEPTION WHEN DUP_VAL_ON_INDEX THEN '
            "RAISE_APPLICATION_ERROR(-20042,'AGENT_HEAD_CONFLICT'); END; ELSE "
            f'SELECT CHG_SEQ_NO INTO v_revision FROM {STATE} WHERE SCOPE_HASH_VAL=:scope AND ST_KEY_ID=:head_key FOR UPDATE; '
            "IF v_revision<>:expected THEN RAISE_APPLICATION_ERROR(-20042,'AGENT_HEAD_CONFLICT'); END IF; "
            f'UPDATE {STATE} SET CHG_SEQ_NO=:revision,ST_HASH_VAL=:head_hash,ST_JSON_CN=:head_json '
            'WHERE SCOPE_HASH_VAL=:scope AND ST_KEY_ID=:head_key; END IF; '
            'FOR l IN (SELECT k,t FROM JSON_TABLE(:payload,\'$.leases[*]\' COLUMNS(k VARCHAR2(128) PATH \'$.key\',t VARCHAR2(64) PATH \'$.token\'))) LOOP '
            f'SELECT JSON_VALUE(ST_JSON_CN,\'$.token\'),JSON_VALUE(ST_JSON_CN,\'$.expires\' RETURNING NUMBER) INTO v_token,v_expiry '
            f'FROM {STATE} WHERE SCOPE_HASH_VAL=:scope AND ST_KEY_ID=l.k FOR UPDATE; '
            f"IF v_token<>l.t OR v_expiry<={UTC_SECONDS} THEN RAISE_APPLICATION_ERROR(-20043,'AGENT_LEASE_LOST'); END IF; END LOOP; "
            'FOR r IN (SELECT k,t,o,l,b,d,w FROM JSON_TABLE(:payload,\'$.rows[*]\' COLUMNS(k VARCHAR2(64) PATH \'$.key\', '
            't VARCHAR2(64) PATH \'$.kind\',o NUMBER PATH \'$.order\',l VARCHAR2(64) PATH \'$.lookup\', '
            'b VARCHAR2(64) PATH \'$.body\',d NUMBER PATH \'$.deleted\',w VARCHAR2(64) PATH \'$.owner\'))) LOOP '
            f'INSERT INTO {RECORD}(SCOPE_HASH_VAL,OWNER_KEY_HASH_VAL,REC_KIND_CD,REC_KEY_HASH_VAL,REC_REV_NO,ORD_SEQ_NO,LOOKUP_HASH_VAL,BODY_HASH_VAL) '
            'VALUES(:scope,NVL(r.w,:owner),r.t,r.k,:revision,r.o,r.l,r.b); '
            f'DELETE FROM {RECORD} WHERE SCOPE_HASH_VAL=:scope AND OWNER_KEY_HASH_VAL=NVL(r.w,:owner) AND REC_KIND_CD=r.t AND REC_KEY_HASH_VAL=r.k AND REC_REV_NO=0; '
            f'IF r.d=0 THEN INSERT INTO {RECORD}(SCOPE_HASH_VAL,OWNER_KEY_HASH_VAL,REC_KIND_CD,REC_KEY_HASH_VAL,REC_REV_NO,ORD_SEQ_NO,LOOKUP_HASH_VAL,BODY_HASH_VAL) '
            'VALUES(:scope,NVL(r.w,:owner),r.t,r.k,0,r.o,r.l,r.b); END IF; END LOOP; '
            f'INSERT INTO {RECORD}(SCOPE_HASH_VAL,OWNER_KEY_HASH_VAL,REC_KIND_CD,REC_KEY_HASH_VAL,REC_REV_NO,ORD_SEQ_NO,BODY_HASH_VAL) '
            "VALUES(:scope,:owner,'OPERATION',:operation,1,:revision,:receipt_hash); "
            "SELECT JSON_VALUE(:payload,'$.run.id') INTO v_run_id FROM DUAL; IF v_run_id IS NOT NULL THEN "
            f'SELECT COUNT(*) INTO v_exists FROM {RUN} WHERE SCOPE_HASH_VAL=:scope AND RUN_KEY_HASH_VAL=JSON_VALUE(:payload,\'$.run.id\'); '
            "IF :expected=0 AND v_exists>0 THEN RAISE_APPLICATION_ERROR(-20044,'AGENT_RUN_ID_COLLISION'); END IF; "
            f'MERGE INTO {RUN} d USING (SELECT :scope s,JSON_VALUE(:payload,\'$.run.id\') r FROM DUAL) j '
            'ON (d.SCOPE_HASH_VAL=j.s AND d.RUN_KEY_HASH_VAL=j.r) WHEN MATCHED THEN UPDATE SET '
            'd.ST_CD=JSON_VALUE(:payload,\'$.run.status\'),d.CHG_DTTM=SYSTIMESTAMP,d.BODY_HASH_VAL=:receipt_hash '
            'WHEN NOT MATCHED THEN INSERT(SCOPE_HASH_VAL,RUN_KEY_HASH_VAL,SESS_KEY_HASH_VAL,REQ_KEY_HASH_VAL,PRNT_RUN_KEY_HASH_VAL,ST_CD,STRT_DTTM,CHG_DTTM,BODY_HASH_VAL) '
            "VALUES(j.s,j.r,JSON_VALUE(:payload,'$.run.session'),JSON_VALUE(:payload,'$.run.request'),JSON_VALUE(:payload,'$.run.parent'),"
            "JSON_VALUE(:payload,'$.run.status'),TO_TIMESTAMP_TZ(JSON_VALUE(:payload,'$.run.started'),'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'),SYSTIMESTAMP,:receipt_hash); END IF; "
            'END IF; COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
        binds = [('owner', owner, 'VARCHAR2'), ('operation', operation, 'VARCHAR2'), ('expected', expected, 'NUMBER'),
                 ('head_key', head_key, 'VARCHAR2'), ('revision', revision, 'NUMBER'), ('head_hash', state['hash'], 'VARCHAR2'),
                 ('head_json', state['json'], 'CLOB'), ('payload', canonical(payload), 'CLOB'), ('receipt_hash', sha(receipt), 'VARCHAR2')]
        try:
            self._mutate(statement, binds)
        except BaseException:
            # One reconciliation read; never redispatch the write or external model.
            reconciled = self.operation(owner, operation)
            if reconciled is None or reconciled['BODY_HASH_VAL'] != sha(receipt):
                raise
        saved = self.operation(owner, operation)
        if saved is None or saved['BODY_HASH_VAL'] != sha(receipt):
            raise DPError('AGENT_COMMIT_UNCONFIRMED: operation receipt missing')
        return revision

    @contextmanager
    def lease(self, identity, *, wait=0, ttl=None, key=None, ephemeral=False, track=True):
        key = key or 'a1:lease:' + digest(identity); token = uuid.uuid4().hex
        ttl = max(60, int(self.sql.deadline-time.monotonic()) + 120) if ttl is None else ttl
        until = min(self.sql.deadline, time.monotonic() + wait)
        while True:
            clock = self.sql.query('SELECT ' + UTC_SECONDS + ' AS SECONDS FROM DUAL', limit=1)[0]['SECONDS']
            old = self.state(key)
            if old and old['value']['expires'] > clock and old['value'].get('token'):
                if time.monotonic() >= until:
                    raise BlockingIOError('Oracle record owner is active')
                time.sleep(min(.05, max(0, until - time.monotonic()))); continue
            expected = old['revision'] if old else 0
            value = {'token': token, 'expires': int(clock) + ttl, 'fence': expected + 1}
            state = self._state_value(key, expected + 1, value)
            statement = ('BEGIN '
                f'IF :expected=0 THEN INSERT INTO {STATE}(SCOPE_HASH_VAL,ST_KEY_ID,CHG_SEQ_NO,ST_HASH_VAL,ST_JSON_CN) '
                'VALUES(:scope,:key,:revision,:hash,:value); ELSE '
                f'UPDATE {STATE} SET CHG_SEQ_NO=:revision,ST_HASH_VAL=:hash,ST_JSON_CN=:value '
                'WHERE SCOPE_HASH_VAL=:scope AND ST_KEY_ID=:key AND CHG_SEQ_NO=:expected; '
                "IF SQL%ROWCOUNT<>1 THEN RAISE_APPLICATION_ERROR(-20045,'AGENT_LEASE_CONFLICT'); END IF; END IF; "
                'COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
            try:
                self._mutate(statement, [('expected', expected, 'NUMBER'), ('key', key, 'VARCHAR2'), ('revision', expected + 1, 'NUMBER'),
                    ('hash', state['hash'], 'VARCHAR2'), ('value', state['json'], 'CLOB')])
            except Exception:
                found = self.state(key)
                if not found or found['value'] != value:
                    if time.monotonic() < until:
                        time.sleep(.05); continue
                    raise BlockingIOError('Oracle record lease conflict') from None
            break
        active = ACTIVE_LEASES.set((*ACTIVE_LEASES.get(), {'key': key, 'token': token})) if track else None
        try:
            yield value
        finally:
            if active is not None: ACTIVE_LEASES.reset(active)
            released = {**value, 'expires': 0, 'token': None}
            state = self._state_value(key, expected + 2, released)
            statement = (f'BEGIN UPDATE {STATE} SET CHG_SEQ_NO=:revision,ST_HASH_VAL=:hash,ST_JSON_CN=:value '
                "WHERE SCOPE_HASH_VAL=:scope AND ST_KEY_ID=:key AND JSON_VALUE(ST_JSON_CN,'$.token')=:token; "
                'COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
            self._mutate(statement, [('key', key, 'VARCHAR2'), ('token', token, 'VARCHAR2'), ('revision', expected + 2, 'NUMBER'),
                                    ('hash', state['hash'], 'VARCHAR2'), ('value', state['json'], 'CLOB')])
            if ephemeral:
                self._mutate(f'BEGIN DELETE FROM {STATE} WHERE SCOPE_HASH_VAL=:scope AND ST_KEY_ID=:key AND CHG_SEQ_NO=:revision '
                    "AND JSON_VALUE(ST_JSON_CN,'$.token') IS NULL; COMMIT; END;",
                    [('key', key, 'VARCHAR2'), ('revision', expected + 2, 'NUMBER')])

    @contextmanager
    def shared_lease(self, identity, *, exclusive=False, wait=30):
        group = digest(identity); prefix = 'a1:reader:' + group[:40] + ':'
        writer_key = 'a1:lease:' + digest(['rw-writer', group])
        until = min(self.sql.deadline, time.monotonic() + wait)
        held = None
        while held is None:
            with self.lease(['rw-gate', group], wait=wait):
                clock = self.sql.query('SELECT ' + UTC_SECONDS + ' AS SECONDS FROM DUAL', limit=1)[0]['SECONDS']
                writer = self.state(writer_key)
                writer_active = bool(writer and writer['value'].get('token') and writer['value']['expires'] > clock)
                readers = self._query(f'SELECT COUNT(*) AS N FROM {STATE} WHERE SCOPE_HASH_VAL=:scope AND ST_KEY_ID LIKE :prefix '
                    f"AND JSON_VALUE(ST_JSON_CN,'$.token') IS NOT NULL AND JSON_VALUE(ST_JSON_CN,'$.expires' RETURNING NUMBER)>{UTC_SECONDS}",
                    [('prefix', prefix + '%', 'VARCHAR2')], limit=1)[0]['N'] if exclusive else 0
                if not writer_active and not readers:
                    held_key = writer_key if exclusive else prefix + uuid.uuid4().hex
                    held = self.lease(['rw-writer', group], key=held_key, track=False) if exclusive else self.lease(
                        ['rw-reader', group], key=held_key, ephemeral=True, track=False)
                    value = held.__enter__()
            if held is None:
                if time.monotonic() >= until:
                    raise BlockingIOError('Oracle store generation is being changed')
                time.sleep(.05)
        active = ACTIVE_LEASES.set((*ACTIVE_LEASES.get(), {'key': held_key, 'token': value['token']}))
        try:
            yield
        finally:
            ACTIVE_LEASES.reset(active)
            held.__exit__(None, None, None)

    def allocated_bytes(self):
        row = self._query(f'SELECT NVL(SUM(DBMS_LOB.GETLENGTH(PART_JSON_CN)),0) AS N FROM {BODY} WHERE SCOPE_HASH_VAL=:scope', limit=1)
        return row[0]['N']
