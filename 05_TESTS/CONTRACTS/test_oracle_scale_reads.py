"""Oracle scale reads (2026-11-06, MAIN171): no whole-scope/whole-document enumeration on the Oracle port.

Pure contract checks with in-memory fakes; the real local Oracle runs are
06_TOOLS/maintenance/oracle_scale_guard (scaled row budget) and
09_ARTIFACTS/AUDITS/20261106-oracle-scale-fixes.
"""
from collections import defaultdict
from types import SimpleNamespace

import pytest

from semantic_runtime import oracle_query_matcher as qm
from semantic_runtime.oracle_dp_io import digest
from semantic_runtime.legal_agent import law_candidates as lc


class Scope(frozenset):
    """Lazy Oracle SourceScope stand-in: membership only, iteration forbidden."""
    def __new__(cls, ids, documents):
        value = super().__new__(cls, ids)
        value.document_ids = frozenset(documents)
        return value

    def __iter__(self):
        raise AssertionError('whole permitted-source set enumerated')


def test_permitted_source_descriptor_keeps_oracle_scope_lazy():
    scope = Scope({'s1', 's2'}, {'d1'})
    descriptor = lc.allowed_descriptor(scope)
    assert descriptor == {'documents': ['d1']}
    assert lc.descriptor_within(descriptor, scope)
    assert not lc.descriptor_within({'documents': ['d1', 'd2']}, scope)
    session = SimpleNamespace(tools=SimpleNamespace(sources=SimpleNamespace(ids_for_documents=lambda docs: ('scope', tuple(docs)))))
    assert lc.descriptor_scope(session, descriptor) == ('scope', ('d1',))
    # SQLite sets and older stored lists keep the previous form.
    assert lc.allowed_descriptor(frozenset({'b', 'a'})) == ['a', 'b']
    assert lc.descriptor_within(['a'], frozenset({'a', 'b'})) and lc.descriptor_scope(session, ['a']) == ['a']


def test_oracle_source_lookup_without_identity_is_not_an_unfiltered_page():
    from semantic_runtime.oracle_query_index import Sources
    calls = []
    request = SimpleNamespace(records=SimpleNamespace(page=lambda *a, **k: calls.append(k) or {'rows': []}),
                              sources=SimpleNamespace(allowed=frozenset({'d'})), release_id='r')
    sources = Sources.__new__(Sources)
    sources.request, sources.kind = request, 'nav.source'
    assert sources.get(None) is None and sources.get('') is None
    assert not calls  # lookup_id=None would have meant "no filter" (first rows of every document)
    assert sources.get('missing') is None and len(calls) == 1
    assert sources.get('missing') is None and len(calls) == 1  # memoized miss


def _surface_pages(rows):
    def pages(request, kind, *, budget=10000, **filters):
        assert kind == 'native.surface'
        for row in rows:
            if 'lookup_id' in filters and row['lookup_id'] != filters['lookup_id']:
                continue
            if 'target_ids' in filters and row['target_id'] not in filters['target_ids']:
                continue
            if 'owner_id' in filters and row['owner_id'] != filters['owner_id']:
                continue
            yield {'group': 'structure', 'key': row['key'], 'value': row['value']}
    return pages


@pytest.mark.parametrize('question', ['제1조제1항의 승인', '제10조와 제1조 그리고 제100조', '제1장 총칙 제1조', '승인 제1항'])
def test_large_title_group_uses_exact_keys_with_identical_matches(monkeypatch, question):
    from semantic_runtime.navigation_match import norm
    labels = ['제1조', '제1항', '제10조', '제100조', '제1장', '제1장총칙', '승인', '제2조', '제1호']
    rows = []
    for n, label in enumerate(labels * 3):
        key = norm(label)
        rows.append({'key': key, 'value': {'unit_id': str(n), 'document_id': 'd'}, 'lookup_id': 'structure:' + key[:2],
                     'owner_id': 'structure', 'target_id': digest(key)})
    monkeypatch.setattr(qm, 'pages', _surface_pages(rows))
    group = qm.RemoteSurface(object(), 'structure')
    exact = qm.RemoteSurface(object(), 'structure'); exact.GROUP_ROWS = 2  # every '제1' read becomes exact
    expected = group.match(question, include_nested=True)
    assert exact.match(question, include_nested=True) == expected and exact.large
    longest = qm.RemoteSurface(object(), 'structure'); longest.GROUP_ROWS = 2
    assert longest.match(question) == qm.RemoteSurface(object(), 'structure').match(question)


class Units:
    """children_for/unit_count/for_document port over a small tree; for_document counts uses."""
    def __init__(self, tree):
        self.tree, self.listed = tree, 0
        self.children = defaultdict(list)
        for uid, parent in tree.items():
            self.children[parent].append(uid)

    def __contains__(self, key):
        return key[1] in self.tree

    def children_for(self, did, parent):
        return (((did, u), {'parent': parent}) for u in self.children.get(parent, ()))

    def unit_count(self, did):
        return len(self.tree)

    def for_document(self, did):
        self.listed += 1
        return (((did, u), {'parent': p}) for u, p in self.tree.items())


def test_fulltext_scope_keys_on_oracle_walks_subtrees_and_skips_large_whole_documents(monkeypatch):
    tree = {'0': None, '1': '0', '2': '1', '3': '1', '4': None}
    units = Units(tree)
    calls = []

    class Index:
        def check_unchanged(self): pass
        def scope_keys(self, db, did, unit_ids):
            calls.append(list(unit_ids))
            return [(did + '#' + u, 'sid-' + u) for u in unit_ids]
    monkeypatch.setattr(lc, 'index', lambda session: (Index(), None))
    monkeypatch.setattr(lc.qs, 'active', lambda session: None)
    session = SimpleNamespace(scope={'d'}, matcher=SimpleNamespace(units=units))
    assert lc.fulltext_scope_keys(session, 'd', '1') == frozenset({'d#1', 'd#2', 'd#3'})
    monkeypatch.setattr(lc, 'SCOPE_KEY_UNITS', 2); calls.clear()
    assert lc.fulltext_scope_keys(session, 'd', '0') == frozenset({'d#0', 'd#1', 'd#2', 'd#3'})
    assert all(len(c) <= 2 for c in calls)
    # A whole document within the threshold is listed once; a larger one is "whole document" (None).
    assert lc.fulltext_scope_keys(session, 'd', None) == frozenset('d#' + u for u in tree) and units.listed == 1
    monkeypatch.setattr(lc, 'WHOLE_DOCUMENT_UNITS', 3)
    assert lc.fulltext_scope_keys(session, 'd', None) is None and units.listed == 1
    with pytest.raises(lc.ContractError, match='subtree is not stored'):
        lc.fulltext_scope_keys(session, 'd', '9')


def test_document_unit_listing_uses_published_count_budget_and_request_memo(monkeypatch):
    listed = []

    def pages(request, kind, *, budget=10000, **filters):
        if kind == 'native.structure_proof':
            yield {'document_id': 'big', 'unit_count': 12}
            return
        listed.append(budget)
        for n in range(12):
            yield {'document_id': 'big', 'unit_id': str(n), 'unit': {'parent': None}}
    monkeypatch.setattr(qm, 'pages', pages)
    # Request-only memo (process listing off); the shared listing is test_unit_listings_shared.py.
    monkeypatch.setenv('GENOS_ORACLE_SHARED_CACHE', 'off')
    units = qm.Units(SimpleNamespace(sources=SimpleNamespace(allowed=frozenset({'big'}))))
    assert len(list(units.for_document('big'))) == 12 and listed == [10000]
    assert len(list(units.for_document('big'))) == 12 and listed == [10000]  # memo, no second listing
    monkeypatch.setattr(units, 'counts', {'big': 20000})
    units.documents.clear()
    with pytest.raises(qm.DPError, match='differs from its published count'):
        list(units.document_rows('big'))
    assert listed[-1] == 20000  # a document larger than 10,000 units gets its own budget
