"""Bounded Oracle reads with real transferred rows; no Oracle/model connection."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

import pytest

from test_oracle_dp import Oracle, fixture_source, run, substring
from semantic_runtime import oracle_dp_io as io
from semantic_runtime.oracle_query import QuerySQL, Snapshot


def test_external_state_mount_must_not_fall_back_to_serving_disk(tmp_path,monkeypatch):
    from semantic_runtime.oracle_query_service import external_path
    with pytest.raises(io.DPError,match='QUERY_STATE_PATH'):
        external_path(str(tmp_path),'GENOS_RUNTIME_DIR')
    original=Path.read_text
    def mountinfo(path,*args,**kwargs):
        if str(path)=='/proc/self/mountinfo':
            return ('1 0 0:1 / / rw - ext4 /dev/root rw\n'
                    '2 1 0:2 / /external\\040state rw - nfs4 server:/runtime rw\n'
                    '3 2 0:3 / /external\\040state/local rw - tmpfs tmpfs rw\n')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',mountinfo)
    assert external_path('/external state/jobs','GENOS_RUNTIME_DIR')==Path('/external state/jobs')
    with pytest.raises(io.DPError,match='serving-local'):
        external_path('/external state/local/jobs','GENOS_RUNTIME_DIR')


def test_request_context_shares_one_pin_and_closes_on_failure():
    from semantic_runtime.oracle_query_service import request_context,_REQUEST
    from types import SimpleNamespace
    closed=[]
    with pytest.raises(RuntimeError,match='test failure'):
        with request_context() as slot:
            slot['app']=SimpleNamespace(state=SimpleNamespace(pipeline=SimpleNamespace(store=SimpleNamespace(close=lambda:closed.append(True)))))
            with request_context() as nested: assert nested is slot
            assert not closed
            raise RuntimeError('test failure')
    assert closed==[True] and _REQUEST.get() is None


class ReadOracle(Oracle):
    def request(self, method, path, json):
        sql = json['statementText']
        binds = {b['name']: b['value'] for b in json.get('binds', [])}
        if 'version' not in binds:
            return super().request(method, path, json)
        self.calls.append(json)
        kind = next(k for k, t in io.TABLES.items() if t in sql)
        rows = [r for r in self.data[kind].values()
                if r['DATASET_VERSION'] == binds['version'] and r['DOCUMENT_ID'] == binds['document']]
        if 'unit' in binds:
            rows = [r for r in rows if r['UNIT_ID'] == binds['unit']]
        ids = {v for k, v in binds.items() if re.fullmatch('b[0-9]+', k)}
        if ids:
            rows = [r for r in rows if r['BLOCK_ID'] in ids]
        if 'block_start' in binds:
            rows = sorted((r for r in rows if int(r['BLOCK_ID']) >= binds['block_start']
                           and int(r['BLOCK_ID']) < binds.get('stop', 10**10)
                           and int(r['BLOCK_ID']) > binds.get('after', -1)), key=lambda r: int(r['BLOCK_ID']))
        rows = rows[:json['limit']]
        result = []
        for row in rows:
            r = copy.deepcopy(row)
            for col in io.CLOBS.intersection(io.COLUMNS[kind]):
                r[col+'__TOTAL'] = None if row[col] is None else io.units(row[col])
                r[col] = substring(row[col], 1, io.LOB_UNITS)
            result.append(r)
        return {'items': [{'resultSet': {'items': result, 'offset': 0, 'hasMore': False}}]}


@pytest.fixture
def bound(tmp_path):
    source = fixture_source(tmp_path/'source', n=12)
    manifest_path = source.with_name('manifest.json')
    manifest = json.loads(manifest_path.read_text())
    manifest['scope'] = {'document_version_ids': ["doc'한글"]}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False))
    remote = ReadOracle()
    run(remote, source, tmp_path, action='run')
    text = manifest_path.read_text()
    version = hashlib.sha256(text.encode()).hexdigest()
    sql = QuerySQL(remote, binding='test', deadline=time.monotonic()+30)
    snapshot = Snapshot('a'*64, version, manifest['generation_id'], manifest['store_sha256'], manifest,
                        frozenset(), io.digest({'release_id': 'a'*64, 'connection': 'test'}))
    remote.calls.clear()
    return remote, sql, snapshot, source


def test_queries_preserve_unicode_order_and_compact_text_without_serving_files(bound, monkeypatch):
    remote, sql, snapshot, source = bound
    with sqlite3.connect(source) as db:
        expected = db.execute('SELECT text FROM source_block WHERE block_id="0"').fetchone()[0]
    reader = snapshot.reader(sql, document_ids=["doc'한글"])
    def forbidden(*args, **kwargs):
        pytest.fail('query provider must not create/open SQLite or serving files')
    monkeypatch.setattr(Path, 'open', forbidden)
    monkeypatch.setattr(Path, 'mkdir', forbidden)
    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    rows = reader.sources("doc'한글", ['2', '0', '2'])
    assert [r['block_id'] for r in rows] == ['2', '0', '2']
    assert rows[1]['text'] == expected
    assert json.loads(rows[1]['json'])['text'] == expected
    assert all(c['statementText'].startswith('SELECT ') for c in remote.calls)
    assert all('LEGAL_RAG_ASSET_PART' not in c['statementText'] for c in remote.calls)
    assert sql.calls == len(remote.calls)
    assert reader.unit("doc'한글", 'unit-1')['parent_id'] is None


def test_keyset_range_pages_do_not_scan_other_documents(bound):
    remote, sql, snapshot, _ = bound
    reader = snapshot.reader(sql, document_ids=["doc'한글"])
    first = reader.blocks("doc'한글", start=2, stop=8, limit=4)
    second = reader.blocks("doc'한글", start=2, stop=8, after=first['next_after'], limit=4)
    assert [r['block_id'] for r in first['rows']+second['rows']] == ['2','3','4','5','6','7']
    assert second['next_after'] is None
    assert all(':document' in c['statementText'] for c in remote.calls)


def test_section_reads_only_selected_range_and_keeps_ancestor_contract(bound,monkeypatch):
    remote, sql, snapshot, _ = bound
    child = next(iter(remote.data['source_unit'].values()))
    child['SOURCE_JSON'] = json.dumps({'span':[3,7],'title':'선택 조항','family':'ARTICLE'})
    child['PARENT_ID'] = 'chapter'
    parent = {**child,'UNIT_ID':'chapter','PARENT_ID':None,
              'SOURCE_JSON':json.dumps({'span':[0,12],'title':'상위 장','family':'CHAPTER'})}
    remote.data['source_unit'][tuple(parent[k] for k in io.KEYS['source_unit'])] = parent
    reader = snapshot.reader(sql,document_ids=["doc'한글"])
    monkeypatch.setattr(Path,'open',lambda *a,**k:pytest.fail('section opened serving file'))
    monkeypatch.setattr(sqlite3,'connect',lambda *a,**k:pytest.fail('section opened SQLite'))
    result = reader.section("doc'한글",'unit-1')
    assert result['title']=='선택 조항' and [a['id'] for a in result['ancestors']]==['chapter','unit-1']
    assert [b['block_id'] for b in result['blocks']]==['3','4','5','6']
    assert all(b['text'] for b in result['blocks'])
    with pytest.raises(io.DPError,match='QUERY_SECTION_SIZE'):
        reader.section("doc'한글",'unit-1',max_blocks=3)
    parent['PARENT_ID']='unit-1'
    with pytest.raises(io.DPError,match='QUERY_ANCESTOR'):
        reader.section("doc'한글",'unit-1')


def test_source_without_unit_keeps_original_instead_of_inventing_section(bound):
    remote, sql, snapshot, _ = bound
    row = next(r for r in remote.data['block_payload'].values() if r['BLOCK_ID']=='2')
    row['UNIT_ID']=None
    result = snapshot.reader(sql,document_ids=["doc'한글"]).source_scope("doc'한글",'2')
    assert result['unresolved_reason']=='SOURCE_WITHOUT_STRUCTURAL_UNIT'
    assert result['unit_id'] is None and result['blocks'][0]['text']==row['TEXT']


@pytest.mark.parametrize('scope', [None, 'doc', ['foreign']])
def test_scope_rejected_before_data_query(bound, scope):
    remote, sql, snapshot, _ = bound
    with pytest.raises(io.DPError, match='QUERY_SCOPE'):
        snapshot.reader(sql, document_ids=scope)
    assert not remote.calls


def test_empty_scope_exclusion_connection_binding_and_missing_source(bound):
    remote, sql, snapshot, _ = bound
    reader = snapshot.reader(sql, document_ids=[])
    with pytest.raises(io.DPError, match='QUERY_SCOPE'):
        reader.source("doc'한글", '0')
    from dataclasses import replace
    with pytest.raises(io.DPError, match='QUERY_SCOPE'):
        replace(snapshot, excluded=frozenset(["doc'한글"])).reader(sql, document_ids=["doc'한글"])
    other = QuerySQL(remote, binding='other', deadline=time.monotonic()+30)
    with pytest.raises(io.DPError, match='QUERY_BINDING'):
        snapshot.reader(other, document_ids=[])
    reader = snapshot.reader(sql, document_ids=["doc'한글"])
    with pytest.raises(io.DPError, match='QUERY_SOURCE_MISSING'):
        reader.sources("doc'한글", ['1', 'missing'])


def test_budget_and_read_only_are_enforced_before_physical_call(bound):
    remote, sql, snapshot, _ = bound
    reader = snapshot.reader(sql, document_ids=["doc'한글"])
    sql.max_calls = 1
    reader.document("doc'한글")
    with pytest.raises(io.BudgetPause):
        reader.document("doc'한글")
    assert len(remote.calls) == 1
    with pytest.raises(io.DPError, match='READ_ONLY'):
        sql.request('DELETE FROM X', write=True)
    sql.deadline = time.monotonic()-1
    with pytest.raises(io.BudgetPause):
        reader.document("doc'한글")
    assert len(remote.calls) == 1


@pytest.mark.parametrize('result', [
    {'items': [{'resultSet': {'items': [], 'offset': 0, 'hasMore': True}}]},
    {'items': [{'errorCode': 1031}]},
    {'items': [{'resultSet': {'items': [], 'offset': 1, 'hasMore': False}}]},
])
def test_incomplete_or_denied_result_never_becomes_empty_success(bound, monkeypatch, result):
    remote, sql, snapshot, _ = bound
    monkeypatch.setattr(remote, 'request', lambda *a, **k: result)
    with pytest.raises(io.DPError):
        snapshot.reader(sql, document_ids=["doc'한글"]).document("doc'한글")
    assert sql.calls == 1


def test_manifest_hash_binding_is_verified_without_assets(bound, monkeypatch):
    remote, sql, snapshot, source = bound
    import semantic_runtime.oracle_query as query
    text = source.with_name('manifest.json').read_text()
    release = {'source_manifest': snapshot.manifest, 'source_manifest_text': text,
               'dataset_version': snapshot.dataset_version, 'search_selection': None}
    monkeypatch.setattr(query, 'get_release', lambda *a: release)
    assert Snapshot.open(sql, 'a'*64).dataset_version == snapshot.dataset_version
    release['source_manifest_text'] += ' '
    with pytest.raises(io.DPError, match='QUERY_MANIFEST'):
        Snapshot.open(sql, 'a'*64)
