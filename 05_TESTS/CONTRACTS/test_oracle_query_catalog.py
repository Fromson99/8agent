"""Oracle catalogue/state contracts on a deterministic ORDS boundary double."""
import copy
import json
from json import loads
import re
import sqlite3
import time

import pytest

from semantic_runtime import oracle_query_catalog as q
from semantic_runtime.oracle_dp_io import DPError, SQL, digest
from semantic_runtime.oracle_query import QuerySQL
from semantic_runtime.oracle_query_state import State, StateSQL, StateConflict, assert_resume
from lawrag.pipeline.oracle_query_publish import asset_rows, _verify_batch
from test_oracle_dp_runtime import published
from test_compact_v2_rag import structured_generation


class Oracle:
    SQL_PATH = '/sql'
    def __init__(self):
        self.rows, self.releases, self.active, self.states = {}, {}, {}, {}
        self.calls, self.writes, self.fail_after_write = [], 0, False

    def request(self, method, path, json):
        assert (method, path) == ('POST', self.SQL_PATH)
        self.calls.append(json)
        statement = json['statementText']
        b = {x['name']: x['value'] for x in json.get('binds', [])}
        if statement.startswith(('BEGIN ', 'DECLARE ')):
            self.writes += 1
            assert statement.endswith('COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
            if q.STATE in statement:
                key = (b['scope'], b['key'])
                prior = self.states.get(key)
                if statement.startswith('BEGIN INSERT'):
                    if prior is not None:
                        return {'items': [{'errorCode': 1}]}
                elif prior is None or (prior['revision'], prior['hash']) != (b['previous'], b['previous_hash']):
                    return {'items': [{'errorCode': 20033}]}
                else:
                    assert 'REVISION=:previous AND VALUE_SHA256=:previous_hash' in statement
                self.states[key] = copy.deepcopy(b)
            elif q.ACTIVE in statement:
                prior = self.active.get(b['channel'])
                if statement.startswith('BEGIN INSERT'):
                    if prior:
                        return {'items': [{'errorCode': 1}]}
                    revision = 1
                else:
                    assert 'REVISION=:revision AND RELEASE_ID=:previous' in statement
                    if prior != {'RELEASE_ID': b['previous'], 'REVISION': b['revision']}:
                        return {'items': [{'errorCode': 20031}]}
                    revision = b['revision']+1
                self.active[b['channel']] = {'RELEASE_ID': b['release'], 'REVISION': revision}
            elif q.ROW in statement:
                candidate = copy.deepcopy(self.rows)
                for name in b:
                    if not re.fullmatch('kind[0-9]+', name):
                        continue
                    n = name[4:]
                    key = (b['release'], b['kind'+n], b['id'+n])
                    value = {'RELEASE_ID': key[0], 'KIND': key[1], 'ROW_ID': key[2],
                             **{column: b[field+n] for column,field in [('DOCUMENT_ID','doc'),('LOOKUP_ID','lookup'),
                                ('OWNER_ID','owner'),('TARGET_ID','target'),('ROW_SHA256','hash'),('VALUE','body')]}}
                    value['N'] = len(value['VALUE'])
                    if key in candidate and candidate[key] != value:
                        return {'items': [{'errorCode': 20032}]}
                    candidate[key] = value
                self.rows = candidate
            else:
                assert q.RELEASE in statement
                self.releases.setdefault(b['release'], b['body'])
            if self.fail_after_write:
                self.fail_after_write = False
                raise TimeoutError('simulated lost acknowledgement')
            return {'items': [{'result': 0}]}
        assert statement.startswith('SELECT ')
        if q.STATE in statement:
            state = self.states.get((b['scope'], b['key']))
            rows = [] if state is None else [{'REVISION': state['revision'], 'VALUE_SHA256': state['hash'],
                                             'VALUE': state['body'], 'N': len(state['body'])}]
        elif q.ACTIVE in statement:
            value = self.active.get(b['channel'])
            rows = [] if value is None else [value]
        elif q.RELEASE in statement:
            value = self.releases.get(b['release'])
            rows = [] if value is None else [{'VALUE': value, 'N': len(value)}]
        else:
            assert q.ROW in statement
            candidates = [v for k,v in self.rows.items() if k[0] == b['release']]
            if 'kind' in b:
                candidates = [r for r in candidates if r['KIND'] == b['kind']]
            if 'authorized_documents' in b:
                allowed = loads(b['authorized_documents'])
                candidates = [r for r in candidates if r['DOCUMENT_ID'] is None or r['DOCUMENT_ID'] in allowed]
            if 'id' in b:
                candidates = [r for r in candidates if r['ROW_ID'] == b['id']]
            if 'kind0' in b:
                keys = {(b[k],b['id'+k[4:]]) for k in b if re.fullmatch('kind[0-9]+',k)}
                candidates = [r for r in candidates if (r['KIND'],r['ROW_ID']) in keys]
            for col in ('DOCUMENT_ID','LOOKUP_ID','OWNER_ID','TARGET_ID'):
                if col.lower() in b:
                    candidates = [r for r in candidates if r[col] == b[col.lower()]]
            lookups = {v for k,v in b.items() if re.fullmatch('lookup[0-9]+', k)}
            if lookups:
                candidates = [r for r in candidates if r['LOOKUP_ID'] in lookups]
            if 'after' in b:
                candidates = [r for r in candidates if r['ROW_ID'] > b['after']]
            rows = sorted(candidates,key=lambda r:r['ROW_ID'])[:json['limit']]
            if 'COUNT(*) AS N' in statement:
                rows = [{'N': len(candidates)}]
            elif 'SELECT VALUE_JSON AS VALUE' in statement:
                rows = [{k:r[k] for k in ('VALUE','N')} for r in rows]
        return {'items': [{'resultSet': {'items': copy.deepcopy(rows), 'offset': 0, 'hasMore': False}}]}


@pytest.fixture
def setup(tmp_path):
    remote = Oracle()
    sql = SQL(remote, journal=tmp_path/'dataiku.jsonl', binding='dataiku')
    rows = [q.record('nav.source', {'id': str(i), 'document_id': 'doc'}, key=str(i), document_id='doc', lookup_id=str(i)) for i in range(7)]
    value = {'schema_version': q.SCHEMA, 'status': 'COMPLETE', 'source_release_id': 'a'*64,
             'dataset_version': 'b'*64, 'tables': {'nav.source': {'rows': len(rows)}}}
    release_id = digest(value)
    remote.releases[release_id] = q.json_body(value)
    q.insert_records(sql, release_id, rows)
    return remote, sql, release_id, value, rows


def test_bounded_pages_cursor_binding_and_single_roundtrip_per_page(setup):
    remote, _, release_id, value, rows = setup
    sql = QuerySQL(remote, binding='test', deadline=time.monotonic()+10)
    records = q.Records(sql, release_id, value)
    first = records.page('nav.source', document_id='doc', limit=4)
    second = records.page('nav.source', document_id='doc', after=first['next'], limit=4)
    assert len(first['rows']+second['rows']) == len(rows) and second['next'] is None
    assert sql.calls == 2
    with pytest.raises(DPError, match='QUERY_CURSOR'):
        records.page('nav.source', document_id='other', after=first['next'])
    assert sql.calls == 2


def test_request_record_scope_and_cursor_are_not_reusable_by_other_team(setup):
    remote, _, release_id, value, _ = setup
    sql = QuerySQL(remote,binding='test',deadline=time.monotonic()+10)
    own = q.Records(sql,release_id,value,document_ids=['doc'])
    other = q.Records(sql,release_id,value,document_ids=[])
    page = own.page('nav.source',limit=3)
    assert len(page['rows'])==3
    assert not other.page('nav.source')['rows']
    with pytest.raises(DPError,match='QUERY_CURSOR'):
        other.page('nav.source',after=page['next'])
    with pytest.raises(DPError,match='QUERY_SCOPE'):
        other.page('nav.source',document_id='doc')
    assert sql.calls == 2


def test_row_body_and_indexed_identity_are_both_bound(setup):
    remote, sql, release_id, value, rows = setup
    _verify_batch(sql, release_id, rows)
    target = next(iter(remote.rows.values()))
    target['VALUE'] = '{}'; target['N'] = 2
    with pytest.raises(DPError, match='QUERY_ROW_HASH'):
        q.Records(sql, release_id, value).page('nav.source')
    with pytest.raises(DPError, match='QUERY_READBACK'):
        _verify_batch(sql, release_id, rows)
    with pytest.raises(DPError, match='WRITE_UNCONFIRMED'):
        q.insert_records(sql, release_id, rows)


def test_activation_cas_loss_reconcile_old_pinned_request_and_rollback(setup):
    remote, sql, release_id, value, _ = setup
    remote.fail_after_write = True
    with pytest.raises(DPError, match='WRITE_UNCONFIRMED'):
        q.activate(sql, 'legal', release_id, expected_revision=0)
    writes = remote.writes
    assert q.activate(sql, 'legal', release_id, expected_revision=0)['reconciled']
    assert remote.writes == writes
    old_request = q.select_release(sql, channel='legal')
    next_value = {**value, 'dataset_version': 'c'*64}
    next_id = digest(next_value)
    remote.releases[next_id] = q.json_body(next_value)
    assert q.activate(sql, 'legal', next_id, expected_revision=1, expected_release_id=release_id)['revision'] == 2
    assert old_request['release_id'] == release_id
    assert q.select_release(sql, channel='legal')['release_id'] == next_id
    with pytest.raises(DPError, match='QUERY_ACTIVE_CONFLICT'):
        q.activate(sql, 'legal', release_id, expected_revision=1, expected_release_id=release_id)
    assert q.activate(sql, 'legal', release_id, expected_revision=2, expected_release_id=next_id)['revision'] == 3


def test_missing_partial_or_changed_release_cannot_be_selected_or_activated(setup):
    remote, sql, release_id, value, _ = setup
    with pytest.raises(DPError, match='QUERY_RELEASE_MISSING'):
        q.activate(sql, 'legal', '0'*64, expected_revision=0)
    remote.releases[release_id] = q.json_body({**value, 'status': 'UPLOADING'})
    with pytest.raises(DPError, match='QUERY_RELEASE_BINDING'):
        q.select_release(sql, release_id=release_id)
    assert not remote.active


def test_state_is_external_cas_and_response_loss_is_not_a_duplicate(setup, monkeypatch):
    remote, _, _, _, _ = setup
    sql = StateSQL(remote, binding='test', deadline=time.monotonic()+10)
    state = State(sql, scope_hash=digest(['team','session']))
    def forbidden(*a, **k):
        pytest.fail('serving state must not open a local database or file')
    from pathlib import Path
    monkeypatch.setattr(Path, 'mkdir', forbidden)
    monkeypatch.setattr(Path, 'open', forbidden)
    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    first = state.put('request/1', {'attempts': 1}, expected_revision=0)
    assert first['revision'] == 1 and not first['reconciled']
    remote.fail_after_write = True
    with pytest.raises(DPError, match='WRITE_UNCONFIRMED'):
        state.put('request/1', {'attempts': 2}, expected_revision=1)
    writes = remote.writes
    assert state.put('request/1', {'attempts': 2}, expected_revision=1)['reconciled']
    assert remote.writes == writes
    with pytest.raises(StateConflict):
        state.put('request/1', {'attempts': 99}, expected_revision=1)
    other = State(sql, scope_hash=digest(['other-team','session']))
    assert other.read('request/1') is None
    stored = remote.states[(state.scope_hash, 'request/1')]
    stored['body'] = '{"attempts":0}'
    with pytest.raises(DPError, match='STATE_HASH'):
        state.read('request/1')


@pytest.mark.parametrize('mutation', [
    {'deadline_at': 'later'}, {'binding_hash': 'other'}, {'request_id': 'new'},
    {'usage': {'model': 0}}, {'usage': {'model': 2, 'sql': 1}},
])
def test_resume_cannot_reset_request_or_cumulative_budget(mutation):
    before = {'request_id': 'same', 'binding_hash': 'pin', 'deadline_at': 'fixed', 'usage': {'model': 1}}
    with pytest.raises(DPError):
        assert_resume(before, {**before, **mutation})
    assert_resume(before, {**before, 'usage': {'model': 2}})


def test_publisher_streams_existing_fts_positions_instead_of_retokenizing(tmp_path):
    path = tmp_path/'fts.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE unit(key TEXT PRIMARY KEY,document_id TEXT,source_id TEXT,json TEXT)')
        db.execute('INSERT INTO unit VALUES(?,?,?,?)', ('u','d','s','{}'))
        db.execute('CREATE VIRTUAL TABLE unit_fts USING fts5(key UNINDEXED,body)')
        db.execute('INSERT INTO unit_fts VALUES(?,?)', ('u','이사회 승인 이사회'))
    before = path.read_bytes()
    rows = list(asset_rows(path, 'fulltext/units.sqlite'))
    assert path.read_bytes() == before
    posts = [r for r in rows if r['kind'].endswith('.unit_fts_posting')]
    assert {r['value']['token']: r['value']['positions'] for r in posts} == {'승인': [1], '이사회': [0,2]}
    assert all('unit_fts_data' not in r['kind'] for r in rows)
    assert len(rows) == 5
    assert next(r['value'] for r in rows if r['kind'].endswith('_stats')) == {'documents':1,'tokens':3}
    assert all(r['document_id']=='d' for r in posts)


def test_existing_verified_dataiku_publication_projects_query_rows_and_preserves_active(published, tmp_path):
    source_oracle, source_release, generation = published
    query_oracle = Oracle()
    class Combined:
        SQL_PATH = '/sql'
        def request(self, method, path, json):
            target = query_oracle if 'LEGAL_RAG_QUERY_' in json['statementText'] else source_oracle
            return target.request(method,path,json)
    from lawrag.pipeline.oracle_query_publish import publish
    kwargs = dict(generation=generation, source_release_id=source_release['release_id'],
                  target_binding='test', directory=tmp_path/'query-publication')
    result = publish(Combined(), **kwargs)
    assert result['status'] == 'COMPLETE' and result['active_changed'] is False
    assert not query_oracle.active
    sql = SQL(Combined(), journal=tmp_path/'read.jsonl', binding='test')
    manifest = q.read_release(sql, result['release_id'])
    assert manifest['source_release_id'] == source_release['release_id']
    assert any(k.endswith('.unit_fts_posting') for k in manifest['tables'])
    assert publish(Combined(), **kwargs)['release_id'] == result['release_id']
    before = copy.deepcopy(query_oracle.releases)
    row = next(iter(query_oracle.rows.values()))
    row['VALUE'] = '{}'; row['N'] = 2
    with pytest.raises(DPError):
        publish(Combined(), **kwargs)
    assert query_oracle.releases == before
    assert json.loads((tmp_path/'query-publication/state.json').read_text())['status'] == 'FAILED'


def test_complete_request_pins_source_index_state_and_detects_original_tampering(published, tmp_path, monkeypatch):
    source_oracle, source_release, generation = published
    query_oracle = Oracle()
    from test_oracle_query import ReadOracle
    source_reader = ReadOracle()
    source_reader.data = source_oracle.data
    class Combined:
        SQL_PATH = '/sql'
        def request(self, method, path, json):
            statement = json['statementText']
            if 'LEGAL_RAG_QUERY_' in statement:
                target = query_oracle
            elif any(table in statement for table in ('LEGAL_SRC_DOCUMENT_A','LEGAL_SRC_SOURCE_UNIT_A','LEGAL_SRC_BLOCK_PAYLOAD_A')):
                target = source_reader
            else:
                target = source_oracle
            return target.request(method,path,json)
    from lawrag.pipeline.oracle_query_publish import publish
    result = publish(Combined(), generation=generation, source_release_id=source_release['release_id'],
                     target_binding='test', directory=tmp_path/'query-publication')
    sql = SQL(Combined(), journal=tmp_path/'activate.jsonl', binding='test')
    q.activate(sql, 'legal', result['release_id'], expected_revision=0)
    from semantic_runtime.oracle_query_request import open_request
    from pathlib import Path
    def forbidden(*a, **k):
        pytest.fail('Oracle request must not touch a local data file')
    monkeypatch.setattr(Path, 'mkdir', forbidden)
    monkeypatch.setattr(Path, 'open', forbidden)
    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    request = open_request(Combined(), connection_binding='test', document_ids=['d'],
                           deadline=time.monotonic()+10, channel='legal')
    assert request.release_id == result['release_id'] and request.pointer_revision == 1
    original = request.sources.source('d','0')
    assert original['text']
    before = request.sql.calls
    state = request.state(digest(['team','session']))
    assert state.put('run/1', {'sql_calls': before}, expected_revision=0)['revision'] == 1
    assert request.sql.calls > before
    block = next(r for r in source_reader.data['block_payload'].values() if r['DOCUMENT_ID']=='d' and r['BLOCK_ID']=='0')
    block['TEXT'] += ' changed'
    with pytest.raises(DPError, match='QUERY_SOURCE_HASH'):
        request.sources.source('d','0')
