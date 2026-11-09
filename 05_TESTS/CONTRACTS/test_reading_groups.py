"""Synthetic contract tests for whole-document reading groups; no model calls."""
import json
import sqlite3
from types import SimpleNamespace as S

import pytest

from semantic_runtime.basis_links.contracts import BasisError
from semantic_runtime.basis_links.reading_groups import build, POLICY


def document(units, blocks):
    """units: (id, parent, surface, title); blocks: (id, owner, chars)."""
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.executescript('CREATE TABLE source_unit(document_id,unit_id,parent_id,json);'
                     'CREATE TABLE source_block(document_id,block_id,unit_id,text);')
    for uid, parent, surface, title in units:
        db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',
                   ('i', uid, parent, json.dumps({'surface': surface, 'title': title, 'span': [0, 1]})))
    for bid, owner, chars in blocks:
        db.execute('INSERT INTO source_block VALUES(?,?,?,?)', ('i', str(bid), owner, '가' * chars))
    return S(db=db, check_unchanged=lambda: None)


ARTICLE = [('ch', None, '제1장', '제1장 총칙'), ('a5', 'ch', '제5조', '한도'),
           ('p1', 'a5', '①', ''), ('i1', 'p1', '1.', ''), ('i2', 'p1', '2.', ''), ('p2', 'a5', '②', ''),
           ('a6', 'ch', '제6조', '보고')]
# block: 0 장 제목, 1 조 제목, 2 ①머리, 3 1호, 4 2호, 5 ①단서, 6 ②, 7 제6조
TEXT = [(0, 'ch', 10), (1, 'a5', 10), (2, 'p1', 40), (3, 'i1', 100), (4, 'i2', 100), (5, 'p1', 30), (6, 'p2', 100),
        (7, 'a6', 50)]


def spans(result):
    return [(s['block_id'], s['start_cp'], s['end_cp']) for g in result['groups'] for r in g['rows'] for s in r['segments']]


def test_small_document_is_one_group_with_every_row():
    result = build(document(ARTICLE, TEXT), 'i')
    assert result['schema_version'] == POLICY and result['totals'] == {'blocks': 8, 'chars': 440, 'groups': 1, 'rows': 8}
    group = result['groups'][0]
    assert group['node']['unit_id'] == 'ch' and group['spine'] == [] and group['path'] == []
    assert [r['role'] for r in group['rows']] == ['lead', 'lead', 'lead', 'own', 'own', 'tail', 'own', 'own']
    assert group['rows'][3]['path'] == ['제1장 총칙', '제5조 한도', '①'] and group['rows'][3]['label'] == '1.'
    assert group['rows'][5]['label'] == '① (꼬리 문장)'
    assert sorted(spans(result)) == sorted((str(b), 0, n) for b, _, n in TEXT)


def test_oversized_parent_splits_by_children_and_carries_spine():
    result = build(document(ARTICLE, TEXT), 'i', max_chars=150)
    titles = [g['title'] for g in result['groups']]
    assert titles == ['제1장 총칙 (머리 문장)', '제5조 한도 (머리 문장)', '① (머리 문장) ~ 1.', '2. ~ ① (꼬리 문장)', '②', '제6조 보고']
    second_item = result['groups'][3]
    assert second_item['path'] == ['제1장 총칙', '제5조 한도', '①']
    by_unit = {e['unit_id']: e['rows'] for e in second_item['spine']}
    # The lead sentence stays visible to items read in a later group.
    assert [(r['role'], r['position'], r['chars']) for r in by_unit['p1']] == [('lead', 'before', 40)]
    assert [r['role'] for r in by_unit['a5']] == ['lead'] and [r['role'] for r in by_unit['ch']] == ['lead']
    assert second_item['spine_omitted'] == []
    # Spine text is context only: each block is still a row exactly once.
    assert sorted(spans(result)) == sorted((str(b), 0, n) for b, _, n in TEXT)
    assert len({g['group_id'] for g in result['groups']}) == 6 and [g['index'] for g in result['groups']] == list(range(6))


def test_row_limit_splits_even_when_text_is_short():
    result = build(document(ARTICLE, TEXT), 'i', max_rows=3)
    assert all(len(g['rows']) <= 3 for g in result['groups']) and result['totals']['rows'] == 8
    assert sorted(spans(result)) == sorted((str(b), 0, n) for b, _, n in TEXT)


def test_single_long_row_is_cut_into_parts_without_loss():
    store = document([('annex', None, '별표', '별표 1')], [(0, 'annex', 50), (1, 'annex', 250), (2, 'annex', 40)])
    result = build(store, 'i', max_chars=100)
    rows = [g['rows'][0] for g in result['groups']]
    assert [r['part'] for r in rows] == [{'index': i, 'count': 5} for i in range(1, 6)]
    assert spans(result) == [('0', 0, 50), ('1', 0, 100), ('1', 100, 200), ('1', 200, 250), ('2', 0, 40)]
    assert result['groups'][2]['title'] == '별표 1 (3/5)' and all(len(g['rows']) == 1 for g in result['groups'])
    # Other parts of the same row are not repeated as context.
    assert all(e['rows'] == [] for g in result['groups'] for e in g['spine'])


def test_unstructured_text_and_stored_owner_are_kept():
    # Text outside every unit is kept as its own rows; the stored block owner decides membership.
    store = document([('a', None, '1.', '목적'), ('b', None, '2.', '범위')],
                     [(0, None, 20), (1, 'a', 30), (2, 'b', 30), (3, 'b', 30), (4, None, 20)])
    result = build(store, 'i', max_chars=60)
    rows = [(r['unit_id'], r['label'], r['role']) for g in result['groups'] for r in g['rows']]
    assert rows == [(None, '구조 미분류 본문', 'own'), ('a', '1. 목적', 'own'), ('b', '2. 범위', 'own'),
                    (None, '구조 미분류 본문', 'own')]
    assert sorted(spans(result)) == [(str(i), 0, n) for i, n in enumerate((20, 30, 30, 30, 20))]


def test_identity_is_stable_and_limits_only_change_windows():
    first, again = build(document(ARTICLE, TEXT), 'i', max_chars=150), build(document(ARTICLE, TEXT), 'i', max_chars=150)
    assert first == again
    other = build(document(ARTICLE, TEXT), 'i', max_chars=300)
    assert len(other['groups']) < len(first['groups'])
    assert {r['row_id'] for g in other['groups'] for r in g['rows']} == {r['row_id'] for g in first['groups'] for r in g['rows']}


def test_long_ancestor_text_is_reported_not_silently_dropped():
    units = [('a', None, '제1조', '기준'), ('p1', 'a', '①', ''), ('p2', 'a', '②', '')]
    blocks = [(0, 'a', 90), (1, 'p1', 80), (2, 'p2', 80), (3, 'a', 90)]
    result = build(document(units, blocks), 'i', max_chars=100, max_spine_chars=100)
    group = next(g for g in result['groups'] if g['title'] == '②')
    kept = [r['role'] for e in group['spine'] for r in e['rows']]
    assert kept == ['lead'] and len(group['spine_omitted']) == 1
    tight = build(document(units, blocks), 'i', max_chars=100, max_spine_chars=50)
    group = next(g for g in tight['groups'] if g['title'] == '②')
    assert [e['label'] for e in group['spine']] == ['제1조 기준'] and group['spine'][0]['rows'] == []
    assert len(group['spine_omitted']) == 2


@pytest.mark.parametrize('units,blocks,limits,code', [
    ([('a', 'missing', '1.', '')], [(0, 'a', 10)], {}, 'BASIS_STRUCTURE'),
    ([('a', 'b', '1.', ''), ('b', 'a', '2.', '')], [(0, 'a', 10)], {}, 'BASIS_STRUCTURE'),
    ([('a', None, '1.', '')], [(0, 'ghost', 10)], {}, 'BASIS_STRUCTURE'),
    ([('a', None, '1.', '')], [(0, 'a', 10)], {'max_chars': 0}, 'BASIS_GROUP_LIMIT'),
    ([('a', None, '1.', '')], [(0, 'a', 10)], {'max_rows': True}, 'BASIS_GROUP_LIMIT'),
])
def test_invalid_structure_or_limits_stop(units, blocks, limits, code):
    with pytest.raises(BasisError) as error:
        build(document(units, blocks), 'i', **limits)
    assert error.value.code == code


def test_empty_blocks_are_not_rows():
    store = document([('a', None, '1.', '')], [(0, 'a', 10), (1, 'a', 0), (2, 'a', 5)])
    result = build(store, 'i')
    assert result['totals'] == {'blocks': 2, 'chars': 15, 'groups': 1, 'rows': 1}
