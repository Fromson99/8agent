"""Oracle unit listings shared per pinned release (2026-11-11, unit-listings-shared on MAIN212).

MAIN212 reused the document tree across requests, so the request memo of unit rows was never filled
and section/chapter matching looked units up one SQL at a time (big-document guard V1 2,034 -> 2,992).
One listing per (release, document) now serves every request of the process; the ACL stays per request.
"""
from types import SimpleNamespace

import pytest

from semantic_runtime import oracle_query_matcher as qm


def fake(monkeypatch, listed, points):
    def pages(request, kind, *, budget=10000, **filters):
        if kind == 'native.structure_proof':
            yield {'document_id': 'd', 'unit_count': 3}
            return
        listed.append(request.records.release_id)
        for n in range(3):
            yield {'document_id': 'd', 'unit_id': str(n), 'unit': {'parent': None, 'title': 't%d' % n}}
    monkeypatch.setattr(qm, 'pages', pages)
    monkeypatch.setenv('GENOS_ORACLE_SHARED_CACHE', 'on')
    qm._LISTINGS.clear()

    def units(release, allowed=('d',)):
        def page(kind, **filters):
            points.append(filters)
            return {'rows': []}
        request = SimpleNamespace(sources=SimpleNamespace(allowed=frozenset(allowed)),
                                  records=SimpleNamespace(release_id=release, page=page))
        return qm.Units(request)
    return units


def test_one_listing_per_release_serves_later_requests_without_sql(monkeypatch):
    listed, points = [], []
    units = fake(monkeypatch, listed, points)
    first = units('r1')
    assert [k for k, _ in first.for_document('d')] == [('d', '0'), ('d', '1'), ('d', '2')]
    second = units('r1')
    # A later request: point lookup and listing come from the process listing, no SQL.
    assert second[('d', '2')]['title'] == 't2'
    assert len(list(second.for_document('d'))) == 3
    assert listed == ['r1'] and points == []
    with pytest.raises(KeyError):
        second[('d', '9')]
    assert points == []
    # Another release is another listing.
    assert not units('r2')._held('d')
    list(units('r2').for_document('d'))
    assert listed == ['r1', 'r2']


def test_shared_listing_keeps_the_request_acl(monkeypatch):
    listed, points = [], []
    units = fake(monkeypatch, listed, points)
    list(units('r1').for_document('d'))
    other = units('r1', allowed=())
    with pytest.raises(KeyError):
        other[('d', '0')]
    with pytest.raises(qm.DPError, match='unauthorized'):
        list(other.document_rows('d'))
    assert listed == ['r1'] and points == []


def test_off_keeps_the_request_only_memo(monkeypatch):
    listed, points = [], []
    units = fake(monkeypatch, listed, points)
    monkeypatch.setenv('GENOS_ORACLE_SHARED_CACHE', 'off')
    list(units('r1').for_document('d'))
    list(units('r1').for_document('d'))
    assert listed == ['r1', 'r1']
