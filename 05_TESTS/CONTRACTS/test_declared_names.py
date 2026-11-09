"""Names a document declares for itself (`X(이하 "Y"라 한다)`), prepared once per process.

No stored table: the units of the published fulltext index that hold 이하 are read in
bounded batches, declarations are parsed from their original text and kept in process
memory per document. They only add search queries and resolve a declared law-title
abbreviation to an authorized document.
"""
import itertools
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from semantic_runtime.legal_agent import declared_names as dn
from semantic_runtime.legal_agent import query_scope as qs

ROOT = Path(__file__).resolve().parents[2]
GENERATION = ROOT / '01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation'
_IDENTITY = itertools.count()


class Index:
    """Fulltext index double: every unit holds 이하; correctness comes from dn.parse."""
    def __init__(self, units, fail=None):
        self.units, self.fail, self.calls = units, fail, []
        self.manifest = {'index_sha256': 'fixture-%d' % next(_IDENTITY)}

    def _allowed(self, allowed):
        return [u for u in self.units if u['source_id'] in allowed]

    def law_groups_page(self, db, terms, allowed, *, cursor=None, limit=12, **kwargs):
        if self.fail:
            raise self.fail
        self.calls.append(('laws', list(terms), set(allowed)))
        counts = {}
        for u in self._allowed(allowed):
            counts[u['document_id']] = counts.get(u['document_id'], 0) + 1
        offset = cursor or 0
        items = [{'document_id': d, 'unit_count': n} for d, n in sorted(counts.items())][offset:offset + limit]
        return {'items': items, 'total': len(counts), 'next_cursor': offset + limit if offset + limit < len(counts) else None}

    def rank_page(self, db, terms, allowed, *, cursor=None, limit=16, **kwargs):
        self.calls.append(('units', list(terms), set(allowed)))
        rows = self._allowed(allowed)
        offset = cursor or 0
        items = rows[offset:offset + limit]
        return {'items': items, 'total': len(rows), 'next_cursor': offset + limit if offset + limit < len(rows) else None}


def unit(did, text):
    return {'document_id': did, 'source_id': 's-' + did + '-' + str(len(text)) + text[:6], 'unit_id': '1',
            'block_ids': ['0'], 'document_name': did, 'text': text}


TITLES = {'audit': '주식회사 등의 외부감사에 관한 법률', 'audit-r': '주식회사 등의 외부감사에 관한 법률 시행령',
          'rule': '증권의 발행 및 공시 등에 관한 규정', 'fair': '독점규제 및 공정거래에 관한 법률',
          'startup': '중소기업창업 지원법 시행령'}
DECLARING = [
    unit('rule', '① 「주식회사 등의 외부감사에 관한 법률」(이하 "외감법"이라 한다) 제2조에 따른 회사'),
    unit('rule', '「중소기업창업 지원법」(이하 "법"이라 한다) 제3조'),
    unit('startup', '법 제32조제1항에 따른 창업지원 전담조직(이하 "창업지원전담조직"이라 한다)은 다음 업무를 한다.'),
    unit('startup', '경찰청장, 관할 시ㆍ도경찰청장 또는 경찰서장(이하 "경찰관서장"이라 한다)에게 조회를 요청한다.'),
    unit('startup', '창업민원처리협의회의 위원장(이하 이 조에서 "위원장"이라 한다)은 회의를 소집한다.'),
    unit('startup', '① 법 제34조제2항에 따른 성장유망 창업기업(이하 "유망기업"이라 한다)을 선정한다.'),
    unit('startup', '자산총액이 100억원 이하인 회사는 제외한다.'),
]
ALL = sorted(TITLES)


def matcher(units, **kwargs):
    index = Index(units, **kwargs)
    sources = SimpleNamespace(ids_for_documents=lambda docs: {u['source_id'] for u in units if u['document_id'] in docs})
    return SimpleNamespace(document_context={d: {'document_title': t} for d, t in TITLES.items()},
                           documents=dict(TITLES), document_aliases={}, units={},
                           unit_fulltext=index, unit_fulltext_db=object(), sources=sources)


def session(units, **kwargs):
    return SimpleNamespace(matcher=matcher(units, **kwargs))


def scope_of(m, name, authorized=None):
    quote = name + ' 보면 돼'
    change = {'operation': 'REPLACE', 'user_quote': quote, 'targets': [{'document': name, 'structure': None, 'selection': None}]}
    return [t['document_id'] for t in qs.resolve(change, None, m, list(authorized or TITLES), quote)['targets']]


def test_parse_reads_title_clause_and_scope_from_the_original():
    found = {d['name']: d for u in DECLARING for d in dn.parse(u['text'])}
    assert found['외감법']['kind'] == 'TITLE' and found['외감법']['long_form'] == '주식회사 등의 외부감사에 관한 법률'
    assert found['창업지원전담조직']['kind'] == 'CLAUSE'
    assert dn.core(found['창업지원전담조직']['long_form']) == '창업지원 전담조직'
    assert found['경찰관서장']['long_form'].endswith('경찰서장')
    assert found['위원장']['scope_text'] == '이 조에서'
    assert all(d['declaration'].endswith('한다') for d in found.values())
    assert dn.generic('법') and dn.generic('시행령') and not dn.generic('외감법')


def test_declarations_are_read_once_per_process_and_index():
    s = session(DECLARING)
    dn.expand(s, ['외감법 제8조'], ALL)
    first = len(s.matcher.unit_fulltext.calls)
    assert first and all(terms == ['이하'] for _, terms, _ in s.matcher.unit_fulltext.calls)
    _, report = dn.expand(s, ['공정거래법상 계열회사'], ALL)
    assert len(s.matcher.unit_fulltext.calls) == first, 'cached: no second read'
    assert report['cache']['read_documents'] == 0


def test_structure_first_discovery_uses_only_cached_declarations():
    s = session(DECLARING)
    queries, report = dn.expand(s, ['외감법 제8조'], ALL, read=False)
    assert queries == ['외감법 제8조'] and not s.matcher.unit_fulltext.calls, 'no body index read'
    assert report['cache']['not_loaded_documents'] == len(ALL)
    dn.expand(s, ['외감법 제8조'], ALL)            # a body-search request loads them
    queries, _ = dn.expand(s, ['외감법 제8조'], ALL, read=False)
    assert queries[1:] == ['주식회사 등의 외부감사에 관한 법률 제8조']


def test_declared_law_title_abbreviation_resolves_the_scope_document():
    m = matcher(DECLARING)
    assert scope_of(m, '외감법') == ['audit'], 'the 「title」 resolves exactly, not to the 시행령'
    with pytest.raises(qs.UnresolvedScope):
        scope_of(m, '법')               # a document-local name never becomes an alias
    with pytest.raises(qs.UnresolvedScope):
        scope_of(m, '경찰관서장')        # a clause long form is not a document


def test_declarations_naming_different_laws_stay_ambiguous():
    m = matcher(DECLARING + [unit('fair', '「독점규제 및 공정거래에 관한 법률」(이하 "외감법"이라 한다)')])
    with pytest.raises(qs.UnresolvedScope):
        scope_of(m, '외감법')


def test_only_authorized_documents_are_read_and_used():
    m = matcher(DECLARING)
    with pytest.raises(qs.UnresolvedScope):   # only 'rule' declares it, and 'rule' is not authorized
        scope_of(m, '외감법', ['audit', 'audit-r'])
    allowed = {u['source_id'] for u in DECLARING if u['document_id'] in ('audit', 'audit-r')}
    assert all(scope <= allowed for _, _, scope in m.unit_fulltext.calls)
    # A later request authorized for 'rule' reads it then and resolves.
    assert scope_of(m, '외감법') == ['audit']


def test_failed_read_keeps_the_existing_unresolved_result_and_is_not_cached():
    m = matcher(DECLARING, fail=RuntimeError('QUERY_SQL_RESULT_BUDGET'))
    with pytest.raises(qs.UnresolvedScope):
        scope_of(m, '외감법')
    m.unit_fulltext.fail = None
    assert scope_of(m, '외감법') == ['audit']


def test_expand_adds_the_title_in_place_of_a_law_abbreviation():
    queries, report = dn.expand(session(DECLARING), ['외감법 제8조'], ALL)
    assert queries == ['외감법 제8조', '주식회사 등의 외부감사에 관한 법률 제8조']
    assert report['added_queries'] == ['주식회사 등의 외부감사에 관한 법률 제8조']
    assert report['declarations'][0]['document_id'] == 'rule'


def test_a_name_is_matched_as_written_with_suffix_or_particle():
    units = DECLARING + [unit('rule', '「증권의 발행 및 공시 등에 관한 규정」(이하 "승인기준서"라 한다)')]
    queries, _ = dn.expand(session(units), ['승인기준서 제1조'], ALL)
    assert queries[1:] == ['증권의 발행 및 공시 등에 관한 규정 제1조']
    queries, _ = dn.expand(session(DECLARING), ['외감법의 감사인 선임'], ALL)
    assert queries[1:] == ['주식회사 등의 외부감사에 관한 법률의 감사인 선임']
    # 상 in 공정거래법상 is tagged as a noun suffix: the name may also end before it.
    units = DECLARING + [unit('rule', '「독점규제 및 공정거래에 관한 법률」(이하 "공정거래법"이라 한다)')]
    queries, _ = dn.expand(session(units), ['공정거래법상 상호출자제한기업집단 지정 기준'], ALL)
    assert queries[1:] == ['독점규제 및 공정거래에 관한 법률상 상호출자제한기업집단 지정 기준']


def test_names_declared_for_a_long_form_are_reported_not_added():
    queries, report = dn.expand(session(DECLARING), ['성장유망 창업기업의 선정'], ALL)
    assert queries == ['성장유망 창업기업의 선정'], 'a document-local name is not a corpus-wide search word'
    assert any(r['name'] == '유망기업' for r in report['declarations'])
    s = session(DECLARING)
    queries, report = dn.expand(s, ['경찰서장의 조회 요청'], ALL)
    assert queries == ['경찰서장의 조회 요청']
    declarations, _ = dn.CACHE.documents(s.matcher.unit_fulltext, object(), s.matcher.sources, ALL)
    assert any(r['name'] == '경찰관서장' and not r['exact'] for r in dn.as_long_form(declarations, '경찰서장', '경찰서장의'))


def test_expand_failure_leaves_queries_and_reports_the_reason():
    queries, report = dn.expand(session(DECLARING, fail=RuntimeError('budget')), ['외감법 제8조'], ALL)
    assert queries == ['외감법 제8조'] and report['skipped'][0]['reason'].startswith('RuntimeError')


@pytest.mark.skipif(not (GENERATION / 'fulltext/units.sqlite').exists(), reason='local data generation absent')
def test_real_generation_declarations():
    from semantic_runtime.unit_fulltext import UnitFulltextIndex
    from semantic_runtime.storage import Store
    from semantic_runtime.term_index import TermIndex
    index = UnitFulltextIndex(GENERATION / 'fulltext', json.loads((GENERATION / 'navigation/manifest.json').read_text()))
    db = index.connect()
    store = Store(GENERATION)
    docs = [r[0] for r in store.db.execute('SELECT document_id FROM document')]
    tools = TermIndex(GENERATION / 'navigation', store).tools(docs)
    try:
        s = SimpleNamespace(matcher=SimpleNamespace(unit_fulltext=index, unit_fulltext_db=db, sources=tools.sources))
        queries, report = dn.expand(s, ['외감법 제8조'], docs)
        assert '주식회사의 외부감사에 관한 법률 제8조' in queries
        declarations, _ = dn.CACHE.documents(index, db, tools.sources, docs)
        assert any(d['long_form'].endswith('경찰서장') for d in dn.as_name(declarations, '경찰관서장'))
        # Literal comparison: names the tokenizer splits differently in a question are found.
        assert dn.as_name(declarations, '명의개서대행계약', '명의개서대행계약의')
    finally:
        db.close()
        tools.db.close()


def test_a_request_does_not_read_while_the_background_build_runs():
    """Oracle warm-up builds the list in the background (local Oracle, 1,547 documents: 47 s of
    SQL on the request path); meanwhile a request uses only what is cached, then the list."""
    s = session(DECLARING)
    index = s.matcher.unit_fulltext
    identity = index.manifest['index_sha256']
    assert dn.CACHE.reserve(identity) and not dn.CACHE.reserve(identity), 'one build per index'
    try:
        queries, report = dn.expand(s, ['외감법 제8조'], ALL)
        assert queries == ['외감법 제8조'] and not index.calls, 'no request-path read while building'
        assert report['cache']['preloading'] and report['cache']['not_loaded_documents'] == len(ALL)
        assert dn.document_declarations(s.matcher, s.matcher.sources, 'rule') == []
        dn.CACHE.documents(index, object(), s.matcher.sources, ALL, preload=True)   # the background build
        assert index.calls and all(kind in ('laws', 'units') for kind, _, _ in index.calls)
    finally:
        dn.CACHE.release(identity)
    read = len(index.calls)
    queries, report = dn.expand(s, ['외감법 제8조'], ALL)
    assert queries[1:] == ['주식회사 등의 외부감사에 관한 법률 제8조'] and len(index.calls) == read
    assert {d['name'] for d in dn.document_declarations(s.matcher, s.matcher.sources, 'rule')} >= {'외감법', '법'}


def test_oracle_warmup_preload_switch(monkeypatch):
    from semantic_runtime import oracle_query_service as serving
    factory = object.__new__(serving.Factory)
    monkeypatch.setenv('GENOS_DECLARED_NAMES_PRELOAD', 'off')
    assert factory.preload_declared_names('fixture-preload-off') == 'off'
    monkeypatch.delenv('GENOS_DECLARED_NAMES_PRELOAD')
    assert dn.CACHE.reserve('fixture-preload-busy')
    try:
        assert factory.preload_declared_names('fixture-preload-busy') == 'running', 'never a second build'
    finally:
        dn.CACHE.release('fixture-preload-busy')
