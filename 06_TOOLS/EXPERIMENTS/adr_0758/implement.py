from pathlib import Path
R=Path(__file__).resolve().parents[3]
C=R/'02_BACKEND/lawrag/research/candidates/adr_0758/integrated/snapshot'
p=C/'02_BACKEND/semantic_runtime/legal_agent/law_candidates.py'
s=p.read_text()
at="@latency.timed('law.recall.discover', pressure=True)"
helper='''def search_queries(session, plan):
    """Preserve accepted query intent; raw text is only a legacy fallback."""
    explicit = getattr(session, 'law_search_queries', None)
    planned = plan.get('queries') if getattr(session, 'entry_search', None) else None
    selected = explicit or planned
    if selected:
        queries = list(dict.fromkeys(q.strip() for q in selected if isinstance(q, str) and q.strip()))
        if queries:
            return queries, ('selected_search_queries' if explicit else 'accepted_request_queries')
    from .source_recall import focused_queries
    return focused_queries(session.context.request['question'], plan), 'legacy_request_expansion'


'''
assert at in s;s=s.replace(at,helper+at,1)
s=s.replace("queries = getattr(s, 'law_search_queries', None) or focused_queries(s.context.request['question'], plan)","queries, query_origin = search_queries(s, plan)\n        route_queries = list(dict.fromkeys(([s.context.request['question']] if query_origin == 'legacy_request_expansion' else []) + queries))")
s=s.replace('return structured_discovery(s, queries, terms)','return structured_discovery(s, queries, terms, route_queries=route_queries, query_origin=query_origin)')
s=s.replace("structural = resolve(s.context.request['question'], s.matcher, s.scope)\n        query_routes = [resolve(query, s.matcher, s.scope) for query in queries]", "query_routes = [resolve(query, s.matcher, s.scope) for query in route_queries]\n        structural = query_routes[0]")
s=s.replace("catalogue = {'contract': CONTRACT, 'terms': terms, 'queries': queries, 'law_page': page,", "catalogue = {'contract': CONTRACT, 'terms': terms, 'queries': queries, 'route_queries': route_queries, 'query_origin': query_origin, 'law_page': page,")
s=s.replace("digest({'terms': terms, 'scope': sorted(s.scope), 'index': idx.manifest['index_sha256']})", "digest({'terms': terms, 'route_queries': route_queries, 'query_origin': query_origin, 'scope': sorted(s.scope), 'index': idx.manifest['index_sha256']})")
s=s.replace('def structured_discovery(s, queries, terms):','def structured_discovery(s, queries, terms, *, route_queries=None, query_origin=\'legacy_request_expansion\'):')
s=s.replace("routes = [sq.resolve(q, s.matcher, s.scope) for q in [s.context.request['question'], *queries]]\n    directory = sq.catalogue(s.matcher, s.scope, queries=[s.context.request['question'], *queries],", "route_queries = route_queries if route_queries is not None else list(dict.fromkeys([s.context.request['question'], *queries]))\n    routes = [sq.resolve(q, s.matcher, s.scope) for q in route_queries]\n    directory = sq.catalogue(s.matcher, s.scope, queries=route_queries,")
s=s.replace("catalogue={'contract':CONTRACT,'terms':terms,'queries':queries,'law_page':page,", "catalogue={'contract':CONTRACT,'terms':terms,'queries':queries,'route_queries':route_queries,'query_origin':query_origin,'law_page':page,")
s=s.replace("digest({'terms':terms,'queries':queries,'scope':sorted(s.scope),", "digest({'terms':terms,'queries':queries,'route_queries':route_queries,'query_origin':query_origin,'scope':sorted(s.scope),")
p.write_text(s)
p=C/'02_BACKEND/semantic_runtime/legal_agent/law_navigation.py';s=p.read_text();s=s.replace("queries=[question], limit=self.policy['article_page_size'])", "queries=record['law_navigation'].get('route_queries', [question]), limit=self.policy['article_page_size'])");p.write_text(s)
p=C/'02_BACKEND/semantic_runtime/legal_agent/structure_query.py';s=p.read_text()
at='def catalogue(matcher, scope, *, queries=None, document_id=None, offset=0, limit=8,'
helper='''def heading_term_candidates(matcher, docs, query, term_cache):
    """Metadata-only hints inside one identified document, never exact evidence."""
    if len(docs) != 1 or find_coordinates(query):
        return {}
    from ..fulltext import question_terms
    query_terms = set(question_terms(query))
    found = {}
    for (did, uid), coordinate in matcher.stored_coordinates.items():
        if did not in docs or coordinate.chain:
            continue
        unit = matcher.units[(did, uid)]
        if unit.get('coordinate_scope') != 'body':
            continue
        key = did, uid
        if key not in term_cache:
            term_cache[key] = set(question_terms(unit.get('title', '')))
        title_terms = term_cache[key]
        matched = title_terms & query_terms
        if len(matched) >= 2 and len(matched) * 3 >= len(title_terms) * 2:
            found[key] = (len(matched), len(matched) / len(title_terms))
    return found


'''
assert at in s;s=s.replace(at,helper+at,1)
s=s.replace("rows = {}; resolutions = []\n    index = coordinate_index(matcher)", "rows = {}; resolutions = []; ranking = {}; term_cache = {}\n    index = coordinate_index(matcher)",1)
at="        for did, uid in keys:\n            unit = matcher.units[(did, uid)]"
rep="""        # Even an exact short heading can coexist with a more descriptive
        # punctuation/particle variant. Offer both; the model must READ it.
        named = {did for h in document_hits(query, matcher) for did in h['values']} if query else set()
        active = docs & named if named else docs
        if document_id and named and named != {document_id}:
            active = set()
        anchored = document_id is not None or len(named_batch) == 1
        terms = heading_term_candidates(matcher, active, query, term_cache) if anchored and query else {}
        terms = {key: score for key, score in terms.items()
                 if (key[0], matcher.stored_coordinates[key].canonical_surface()) in index}
        exact_coordinate = bool(find_coordinates(query))
        for key in keys:
            ranking[key] = max(ranking.get(key, (0, 0, 0)), (int(exact_coordinate), 0, 0))
        for key, score in terms.items():
            ranking[key] = max(ranking.get(key, (0, 0, 0)), (0, *score))
        keys |= terms.keys()
        for did, uid in keys:
            unit = matcher.units[(did, uid)]"""
assert at in s;s=s.replace(at,rep,1)
at="        0 if r['kind'] == 'document' else 1,\n        matcher.units"
rep="        0 if r['kind'] == 'document' else 1,\n        tuple(-x for x in ranking.get((r['document_id'], r.get('unit_id')), (0, 0, 0))),\n        matcher.units"
assert at in s;s=s.replace(at,rep,1);p.write_text(s)

p=C/'05_TESTS/CONTRACTS/test_focused_input_modality.py'
with p.open('a') as f:f.write('''

@pytest.mark.parametrize('explicit,entry,expected,origin',[
    (None,{'mode':'STRUCTURE'},['자본시장법 금융 업무 재산 검사'],'accepted_request_queries'),
    (['자본시장법 신규 탐색'],{'mode':'FULLTEXT'},['자본시장법 신규 탐색'],'selected_search_queries')])
def test_selected_query_does_not_reinsert_excluded_raw_coordinate(explicit,entry,expected,origin):
    from semantic_runtime.legal_agent.law_candidates import search_queries
    s=S(context=S(request={'question':'업무 검사, 제310조는 제외'}),entry_search=entry,law_search_queries=explicit)
    queries,actual=search_queries(s,{'queries':['자본시장법 금융 업무 재산 검사']})
    assert queries==expected and actual==origin and all('310' not in q for q in queries)


def test_no_entry_retains_legacy_query_expansion():
    from semantic_runtime.legal_agent.law_candidates import search_queries
    s=S(context=S(request={'question':'제310조 검사'}))
    queries,origin=search_queries(s,{'queries':['검사']})
    assert origin=='legacy_request_expansion' and any('310' in q for q in queries)


def title_matcher():
    from test_structure_first_search import matcher
    m=matcher()
    m.units[('law','제6조')].update(title='선임',span=[0,10])
    m.structures.add('선임',{'document_id':'law','unit_id':'제6조','kind':'TITLE'})
    m.units[('law','제6조의2')].update(title='회사의 업무, 재산상태의 검사',span=[20,30])
    return m


def test_metadata_title_variant_ranks_before_short_literal_and_pages_without_loss():
    from semantic_runtime.legal_agent.structure_query import catalogue
    m=title_matcher();kw={'queries':['자본시장법 회사 업무 재산상태 검사 선임'],'limit':1}
    first=catalogue(m,['law','decree'],**kw)
    assert first['items'][0]['unit_id']=='제6조의2'
    assert first['navigation_hint_only'] and not first['citation_eligible']
    assert not first['items'][0]['content_read']
    second=catalogue(m,['law','decree'],offset=first['next_offset'],**kw)
    assert second['items'][0]['unit_id']=='제6조'


def test_metadata_title_overlap_preserves_exact_coordinate_and_scope():
    from semantic_runtime.legal_agent.structure_query import catalogue
    m=title_matcher()
    got=catalogue(m,['law','decree'],queries=['자본시장법 제6조 회사 업무 재산상태 검사'])
    assert [r['unit_id'] for r in got['items']]==['제6조']
    assert catalogue(m,['decree'],queries=['자본시장법 회사 업무 재산상태 검사'])['items']==[]
    assert catalogue(m,['law','decree'],queries=['회사 업무 재산상태 검사'])['items']==[]


def test_metadata_title_candidates_keep_ambiguous_originals_non_executable():
    from semantic_runtime.legal_agent.structure_query import catalogue
    m=title_matcher();m._unit_sources=lambda did,uid:['a','b']
    row=catalogue(m,['law'],queries=['자본시장법 회사 업무 재산상태 검사'])['items'][0]
    assert not row['source_binding_unique'] and row['source_id'] is None
''')
print('758 implementation staged')
