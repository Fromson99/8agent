"""MAIN204 (2026-11-11): connection lists, block IDs, children and terms read together.

In-memory fakes; the same statements on a real Oracle are in 09_ARTIFACTS/AUDITS/20261111-sql-loops-main204.
"""
import json
from types import SimpleNamespace

import pytest

from semantic_runtime import oracle_query, oracle_query_index as qi, oracle_query_matcher as qm
from semantic_runtime.oracle_query_catalog import Records
from semantic_runtime.oracle_dp_io import DPError, digest
from semantic_runtime.legal_agent import connection_scope as cs, storage_admission as sa


TEXT = {'type': 'text', 'has_null': False, 'has_empty': False}


def tools(ends, refs, columns=TEXT):
    calls = []

    def page(kind, **filters):
        calls.append((kind, filters))
        if 'owner_ids' in filters:
            rows = [{'source_id': s, 'reference_id': r} for s, r in ends if s in filters['owner_ids']]
        else:
            rows = [{'id': r, 'json': json.dumps({'id': r})} for r in refs if r in filters['lookup_ids']]
        return {'rows': rows, 'next': None}
    manifest = {'tables': {'end': {'columns': {'source_id': columns}}, 'ref': {'columns': {'id': columns}}}}
    request = SimpleNamespace(records=SimpleNamespace(page=page, manifest=manifest), sources=SimpleNamespace(allowed=frozenset({'d'})), release_id='r')
    value = qi.Tools.__new__(qi.Tools)
    value.request, value.db = request, SimpleNamespace(tables={'reference_end': ('end',), 'reference': ('ref',)}, request=request)
    return value, calls


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    from semantic_runtime import oracle_query_cache
    store = SimpleNamespace(get=lambda key: (False, None), put=lambda key, value: None, check=lambda: None)
    monkeypatch.setattr(oracle_query_cache, 'for_request', lambda request: store)
    monkeypatch.setattr(oracle_query, 'bulk_page', lambda read, rows: read(rows))


def test_references_come_from_two_keyed_reads_in_id_order():
    value, calls = tools([('a', 'r2'), ('a', 'r1'), ('b', 'r3')], ['r1', 'r2', 'r3'])
    assert [json.loads(t)['id'] for t in value.references_from('a', '', None, 257)] == ['r1', 'r2']
    assert [k for k, _ in calls] == ['end', 'ref']
    assert 'b' not in calls[0][1]['owner_ids'] and sorted(calls[1][1]['lookup_ids']) == ['r1', 'r2']


def test_references_keep_after_only_and_limit():
    value, _ = tools([('a', f'r{i}') for i in range(1, 7)], [f'r{i}' for i in range(1, 7)])
    ids = lambda text: [json.loads(t)['id'] for t in text]
    assert ids(value.references_from('a', 'r2', None, 257)) == ['r3', 'r4', 'r5', 'r6']
    assert ids(value.references_from('a', '', {'r5', 'r1'}, 257)) == ['r1', 'r5']
    assert ids(value.references_from('a', '', None, 2)) == ['r1', 'r2']


def test_reference_outside_the_request_documents_is_dropped_and_does_not_use_up_the_limit():
    value, _ = tools([('a', 'r1'), ('a', 'r2'), ('a', 'r3')], ['r2', 'r3'])
    assert [json.loads(t)['id'] for t in value.references_from('a', '', None, 2)] == ['r2', 'r3']


def test_prefetch_reads_many_anchors_once():
    value, calls = tools([('a', 'r1'), ('b', 'r2')], ['r1', 'r2'])
    value.prefetch_references(['a', 'b'])
    count = len(calls)
    value.references_from('a', '', None, 257)
    value.references_from('b', '', None, 257)
    assert count == 2 and len(calls) == count


def test_release_without_the_keys_keeps_the_exists_form(monkeypatch):
    value, calls = tools([], [], columns={'type': 'null', 'has_null': False, 'has_empty': False})
    monkeypatch.setattr(qi.Tools, '_references_scan', lambda self, *a: ['scan'])
    assert value.references_from('a', '', None, 10) == ['scan'] and not calls
    value.prefetch_references(['a'])
    assert not calls


def records():
    manifest = {'tables': {'k': {}}}
    captured = []

    def query(text, binds, limit):
        captured.append((text, binds))
        return []
    return Records(SimpleNamespace(query=query), digest(manifest), manifest, document_ids=['d']), captured


def test_page_owner_ids_is_an_indexed_list_and_bounded():
    reader, captured = records()
    reader.page('k', owner_ids=['a', 'b'], limit=5)
    assert 'OWNER_ID IN (:owner0,:owner1)' in captured[0][0]
    with pytest.raises(DPError):
        reader.page('k', owner_ids=[str(i) for i in range(101)], limit=5)
    with pytest.raises(DPError):
        reader.page('k', owner_ids=['a'], owner_id='b', limit=5)


def test_owner_ids_row_outside_the_list_is_refused():
    reader, _ = records()
    row = {'ROW_ID': 'x', 'DOCUMENT_ID': 'd', 'LOOKUP_ID': 'l', 'OWNER_ID': 'zz', 'TARGET_ID': None, 'VALUE': '{}', 'N': 2}
    with pytest.raises(DPError):
        reader._verified('k', [row], owner_ids=['a'])


class Blocks(oracle_query.SourceReader):
    def __init__(self, rows, reuse=True):
        self.calls, self.rows, self.reuse = 0, rows, reuse
        self.snapshot = SimpleNamespace(dataset_version='v')
        self.sql = SimpleNamespace(query=self.query)
        self._memo_lock = __import__('threading').Lock()
        self._blocks, self._documents, self._units, self._memo_bytes = {}, {}, {}, 0

    def _reuse(self):
        return self.reuse

    def _where(self, did):
        return '', [('version', 'v', 'VARCHAR2'), ('document', did, 'VARCHAR2')]

    def query(self, text, binds, limit):
        self.calls += 1
        after = dict((b[0], b[1]) for b in binds).get('after_block', -1)
        unit = dict((b[0], b[1]) for b in binds).get('unit')
        rows = [{'DATASET_VERSION': 'v', 'DOCUMENT_ID': 'd', 'BLOCK_ID': str(n), 'UNIT_ID': u} for n, u in self.rows
                if n > after and (unit is None or u == unit)]
        return rows[:limit]


@pytest.fixture
def names(monkeypatch):
    from semantic_runtime import oracle_dp_io
    monkeypatch.setattr(oracle_dp_io, 'names', lambda sql, key, table: SimpleNamespace(c=lambda c: c, select=lambda c: c, table='T'))


def test_block_ids_of_a_document_come_from_one_listing(names):
    reader = Blocks([(1, 'u1'), (2, 'u1'), (3, 'u2'), (10, None), (11, 'u2')])
    assert reader.block_ids('d', unit_id='u2') == ['3', '11']
    assert reader.block_ids('d', unit_id='u1') == ['1', '2']
    assert reader.block_ids('d', start=2, stop=11) == ['2', '3', '10']
    assert reader.block_ids('d', unit_id='missing') == []
    assert reader.calls == 1


def test_block_listing_is_off_without_reuse(names):
    reader = Blocks([(1, 'u1')], reuse=False)
    assert reader.block_ids('d', unit_id='u1') == ['1'] and reader.block_ids('d', unit_id='u1') == ['1']
    assert reader.calls == 2


def test_very_long_document_keeps_the_per_unit_read(names, monkeypatch):
    monkeypatch.setattr(oracle_query, 'BULK_PAGE', 3)
    monkeypatch.setattr(oracle_query.SourceReader, 'BLOCK_LISTING_MAX', 3)
    reader = Blocks([(i, 'u1') for i in range(1, 8)])
    assert reader.block_ids('d', unit_id='u1') == [str(i) for i in range(1, 8)]
    first = reader.calls
    assert reader.block_ids('d', unit_id='u1') == [str(i) for i in range(1, 8)]
    assert reader.calls - first == 3  # per-unit read: pages of 3, no second listing


def test_section_children_of_a_walk_come_from_one_read():
    calls = []
    rows = [{'document_id': 'd', 'unit_id': 'c1', 'unit': {'parent': 'p1', 'span': [1, 2]}},
            {'document_id': 'd', 'unit_id': 'c2', 'unit': {'parent': 'p2', 'span': [3, 4]}}]

    def page(kind, **filters):
        calls.append(filters)
        return {'rows': [r for r in rows if r['unit']['parent'] in filters.get('owner_ids', [filters.get('owner_id')])], 'next': None}
    units = qm.Units.__new__(qm.Units)
    units.request = SimpleNamespace(records=SimpleNamespace(page=page), sources=SimpleNamespace(allowed=frozenset({'d'})), release_id='r')
    units.remember = lambda row: row
    session = SimpleNamespace(matcher=SimpleNamespace(units=units))
    cs.prefetch_section_children(session, 'd', ['p1', 'p2', 'p3'])
    assert len(calls) == 1
    assert cs.section_children(session, 'd', 'p1') == ['c1'] and cs.section_children(session, 'd', 'p2') == ['c2']
    assert cs.section_children(session, 'd', 'p3') == [] and len(calls) == 1
    cs.prefetch_section_children(session, 'd', ['p1'])
    assert len(calls) == 1


def test_terms_of_a_question_come_from_one_read():
    calls = []

    def page(kind, **filters):
        calls.append(filters)
        return {'rows': [{'id': k, 'json': json.dumps({'label': k})} for k in filters['lookup_ids']], 'next': None}
    request = SimpleNamespace(records=SimpleNamespace(page=page))
    terms = qi.SQLMap.__new__(qi.SQLMap)
    terms.db, terms.kind, terms.key, terms.value, terms.decode, terms.records, terms._memo = SimpleNamespace(request=request), 't', 'id', 'json', json.loads, request.records, {}
    terms.prefetch(['a', 'b', 'a'])
    assert terms['a'] == {'label': 'a'} and terms['b'] == {'label': 'b'} and len(calls) == 1


def test_capacity_is_measured_again_before_refusing(monkeypatch):
    seen = []

    class Store:
        def allocated_bytes(self, max_age=None):
            seen.append(max_age)
            return 900 if max_age is None else 10
    from semantic_runtime import oracle_runtime_paths as paths
    monkeypatch.setattr(paths, 'virtual', lambda root: True)
    monkeypatch.setattr(paths, 'records', lambda: Store())
    monkeypatch.setattr(sa, 'settings', lambda: (1000, 200, 0))
    with sa.admission('x'):
        pass
    assert seen == [None, 0]


def test_full_budget_is_still_refused_after_the_fresh_measure(monkeypatch):
    class Store:
        def allocated_bytes(self, max_age=None):
            return 900
    from semantic_runtime import oracle_runtime_paths as paths
    monkeypatch.setattr(paths, 'virtual', lambda root: True)
    monkeypatch.setattr(paths, 'records', lambda: Store())
    monkeypatch.setattr(sa, 'settings', lambda: (1000, 200, 0))
    with pytest.raises(sa.StorageCapacity):
        with sa.admission('x'):
            pass
