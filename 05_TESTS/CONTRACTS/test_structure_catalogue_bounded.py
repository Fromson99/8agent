"""Field 2026-11-06 11:24Z (dev silver, DP=oracle): the first question stopped at the start of
the investigation with ``QUERY_FULL_CATALOGUE: use a bounded key lookup``. The stored structure
catalogue scanned the whole coordinate index for any query without a named document + article
pair, and the Oracle coordinate index answers key lookups only.

With an index that refuses enumeration the catalogue must return exactly the page it returns
with the in-memory index.
"""
import pytest

from semantic_runtime.legal_agent import structure_query as sq
from semantic_runtime.oracle_dp_io import DPError
from semantic_runtime.oracle_query_index import Lists
from test_structure_first_search import matcher

QUERIES = [
    ['제6조'],                              # bare article number across documents
    ['제7조 금융투자업'],
    ['자본시장법 제6조', '제6조'],
    ['자본시장법 제99조'],                   # named document, missing article
    ['금융투자업'],                          # stored title, no article number
    ['자본시장법 금융투자업 종류'],
    ['자본시장법 시행령 금융투자업'],
    ['금융투자업', '제6조의2'],
    ['자본시장법'],
    ['전혀없는표제'],
]


def key_lookup_only(m):
    index = sq.coordinate_index(m)
    lookups = []

    def fetch(key):
        lookups.append(key)
        return list(index.get(key, []))
    m.coordinate_index = Lists(fetch)
    return m, lookups


def with_second_title(m):
    # A stored title on a non-article unit and on a sub-article must not enter the article list.
    m.structures.add('금융투자업', {'document_id': 'law', 'unit_id': '제6조제1항', 'kind': 'TITLE'})
    m.structures.add('금융투자업', {'document_id': 'decree', 'unit_id': 'missing', 'kind': 'TITLE'})
    m.structures.add('금융투자업', {'document_id': 'decree', 'unit_id': '제7조', 'kind': 'TITLE'})
    return m


@pytest.mark.parametrize('extra', [False, True])
@pytest.mark.parametrize('queries', QUERIES)
def test_key_lookup_index_gives_the_in_memory_page(queries, extra):
    def fresh():
        return with_second_title(matcher()) if extra else matcher()
    expected = sq.catalogue(fresh(), ['law', 'decree'], queries=queries)
    bounded, lookups = key_lookup_only(fresh())
    with pytest.raises(DPError, match='QUERY_FULL_CATALOGUE'):
        iter(bounded.coordinate_index)
    assert sq.catalogue(bounded, ['law', 'decree'], queries=queries) == expected


def test_bare_article_number_is_one_exact_lookup_per_document():
    m, lookups = key_lookup_only(matcher())
    page = sq.catalogue(m, ['law', 'decree'], queries=['제6조'])
    assert {(r['document_id'], r['unit_id']) for r in page['items']} == {('law', '제6조'), ('decree', '제6조')}
    assert {('law', '제6조'), ('decree', '제6조')} <= set(lookups)
    assert all(coordinate == '제6조' for _, coordinate in lookups)


def test_title_hit_outside_the_named_document_is_not_looked_up():
    m, lookups = key_lookup_only(with_second_title(matcher()))
    page = sq.catalogue(m, ['law', 'decree'], queries=['자본시장법 시행령 금융투자업'])
    assert all(r['document_id'] == 'decree' for r in page['items'])
    assert all(did == 'decree' for did, _ in lookups)


class Counted(dict):
    """A unit map that counts point lookups (the Oracle port pays one SQL per miss)."""
    def __init__(self, *a):
        super().__init__(*a)
        self.lookups = 0

    def __getitem__(self, key):
        self.lookups += 1
        return super().__getitem__(key)

    def get(self, key, default=None):
        self.lookups += 1
        return super().get(key, default)


class ListedCoordinates(dict):
    """Oracle-shaped stored coordinates: one document listing carries each unit."""
    def __init__(self, values, units):
        super().__init__(values)
        self.units = units

    def for_document(self, did):
        return ((k, v) for k, v in dict.items(self) if k[0] == did)

    def for_document_units(self, did):
        return ((k, v, dict.__getitem__(self.units, k)) for k, v in dict.items(self) if k[0] == did)

    def __getitem__(self, key):
        self.units.lookups += 1
        return super().__getitem__(key)

    def get(self, key, default=None):
        self.units.lookups += 1
        return super().get(key, default)


def large_document(oracle_shaped, articles=240):
    """One large document: a few stored titles repeat, every other article has its own title."""
    from types import SimpleNamespace
    from lawrag.core.legal_coordinate import find_coordinates
    from semantic_runtime.navigation_match import SurfaceIndex, norm
    names, headings = SurfaceIndex(), SurfaceIndex()
    documents = {'big': '큰모의규정', 'small': '작은모의규정'}
    for did, title in documents.items():
        names.add(title, did)
    coords, units, sources = {}, Counted(), {}
    for did, n in (('big', articles), ('small', 3)):
        for i in range(1, n+1):
            key = (did, str(i))
            coords[key] = find_coordinates(f'제{i}조')[0].coordinate
            title = ('정의' if i == 1 else '보고 의무' if i in (7, 14, 21, 28) else
                     '적용 범위' if i in (2, 3, 5) else f'개별사항{i}')
            dict.__setitem__(units, key, {'coordinate_scope': 'body', 'title': title, 'span': [i, i+1], 'parent': None})
            sources[f'{did}:{i}'] = {'document_id': did, 'unit_id': str(i)}
            headings.add(title, {'document_id': did, 'unit_id': str(i), 'kind': 'TITLE'})
    calls = []
    m = SimpleNamespace(document_names=names, structures=headings, documents=documents,
        title_keys={norm(x) for x in documents.values()}, units=units, sources=sources,
        _unit_sources=lambda did, uid: calls.append((did, uid)) or [f'{did}:{uid}'])
    m.stored_coordinates = ListedCoordinates(coords, units) if oracle_shaped else coords
    if oracle_shaped:
        index = sq.coordinate_index(SimpleNamespace(stored_coordinates=coords, units=dict(units)))
        bounded = Lists(lambda key: list(index.get(key, [])))
        bounded.document_units = lambda did: frozenset(u for (d, _), ids in index.items() if d == did for u in ids)
        m.coordinate_index = bounded
    return m, calls


@pytest.mark.parametrize('queries,document_id', [
    (['큰모의규정 보고 의무'], None),          # one named document, no article number
    (['큰모의규정의 적용 범위는?', '보고'], None),
    (['보고 의무 기준'], 'big'),
    (['큰모의규정 정의'], None),
    (['작은모의규정 적용 범위'], None),
])
def test_one_named_document_is_listed_once_and_only_the_page_reads_sources(queries, document_id):
    cost = []
    for articles in (240, 480):
        m, calls = large_document(True, articles)
        for offset in (0, 8):
            page = sq.catalogue(m, ['big', 'small'], queries=queries, document_id=document_id, offset=offset)
            want = sq.catalogue(large_document(False, articles)[0], ['big', 'small'],
                                queries=queries, document_id=document_id, offset=offset)
            assert page == want
        cost.append((len(calls), m.units.lookups))
    # Point lookups follow the returned pages and the matching titles, not the document size.
    assert cost[0] == cost[1], cost
    assert cost[0][0] <= 2*8 + 2, cost
