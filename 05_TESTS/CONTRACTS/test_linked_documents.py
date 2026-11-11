"""Internal rules that a read internal rule hands details to by name only (linked_documents).

Synthetic documents and sentences (no internal rule text). The field case (2026-11-10): an
operating guideline said "관련 준칙에서 정한 바에 따라 신상품으로 인정되는" and "세부 준칙에서
정한다" without naming the rule, and the answer asked the user which rule was meant.
"""
from copy import deepcopy
from types import SimpleNamespace as S

import pytest

from semantic_runtime.legal_agent import linked_documents as ld, guided_navigation as gn, guided_answer as g
from semantic_runtime.legal_agent import evidence_inventory as inventory

P = 'internal > risk_team > 2. 소관 준칙 > '
DOCS = {
    'guide': P + '03 상품위원회운영지침 > 상품위원회운영지침(20251205)_조직개편',
    'product': P + '08 상품관리준칙 > 상품관리준칙(20251205)_조직개편',
    'product_old': P + '08 상품관리준칙 > 상품관리준칙(20151207)',
    'invest': P + '10-1 투자위험관리준칙 > 투자위험관리준칙(20240101)',
    'ops': P + '07 운영위험관리준칙 > 운영위험관리준칙(20230101)',
    'committee': P + '06 위험관리위원회 운영준칙 > 위험관리위원회운영준칙(20160823)',
    'detail': P + '01 위험관리기준시행세칙 > 위험관리기준시행세칙(20220331)',
    'law': 'external > risk_team > law > 금융투자업규정',
}
GUIDE_TEXT = ('3. "신상품"이라 함은 관련 준칙에서 정한 바에 따라 신상품으로 인정되는 상품을 말한다.\n'
              '② 제1항에서 정하지 않은 상품 관련 전결권에 관한 사항은 세부 준칙에서 정한다.\n'
              '③ 그 밖의 용어는 위험관리기준 시행세칙에서 정하는 바에 따른다.\n'
              '1. 상품 판매 및 사후관리 관련 준칙의 제·개정 및 폐지\n'
              '④ 서비스는 신규사업 심의위원회 지침에 따라 처리한다.\n'
              '⑤ 이 지침의 개정은 위원회의 결의에 의한다.')
ARTICLES = {
    'product': [('a1', '제1-1조', '목적'), ('a2', '제2-1조', '신상품 판단 기준'), ('a3', '제2-2조', '상품 판매 프로세스'),
                ('a4', '제3-1조', '전결권')],
    'invest': [('b1', '제1조', '목적'), ('b2', '제5조', '투자 한도')],
    'ops': [('c1', '제1조', '목적')],
    'committee': [('d1', '제1조', '목적')],
    'detail': [('e1', '제1조', '목적'), ('e2', '제2조', '용어의 정의')],
}


class Units(dict):
    """Oracle-shaped units: point lookups and children_for (no corpus enumeration)."""
    def __init__(self):
        super().__init__()
        self.children = {}
        for did, articles in ARTICLES.items():
            self[(did, 'root')] = {'surface': '본문', 'parent': None}
            self.children[(did, None)] = ['root']
            self.children[(did, 'root')] = [uid for uid, _, _ in articles]
            for uid, surface, title in articles:
                self[(did, uid)] = {'surface': surface, 'title': title, 'parent': 'root'}
        self.lookups = []

    def children_for(self, did, parent):
        self.lookups.append((did, parent))
        for uid in self.children.get((did, parent), ()):
            yield (did, uid), self[(did, uid)]

    def items(self):
        raise AssertionError('corpus enumeration')


class Repo:
    def __init__(self): self.events = []
    def event(self, kind, payload): self.events.append((kind, deepcopy(payload)))


def context(did):
    team = 'risk_team'
    return {'source_category': 'external' if did == 'law' else 'internal', 'team': team}


def session(scope=None):
    scope = set(DOCS) if scope is None else set(scope)
    matcher = S(documents=dict(DOCS), document_context={d: context(d) for d in DOCS}, units=Units())
    store = S(source=lambda did, bid: {'text': GUIDE_TEXT if did == 'guide' else ''})
    return S(matcher=matcher, scope=scope, store=store, repo=Repo(),
             tools=S(sources={'guide:3': {'document_id': 'guide', 'unit_id': '3'}}))


def investigation(monkeypatch, s, question='신규 상품 판단 기준과 프로세스, 전결권'):
    record = {'source_id': 'guide:3', 'document_id': 'guide', 'offer': {'unit_id': '3', 'block_ids': ['b1']},
              'evidence': [{'source_id': 'guide:3', 'spans': [{'block_id': 'b1'}]}]}
    monkeypatch.setattr(inventory, 'acquired_records', lambda p, **_: {'g1': record})
    def readable(inv, did, uid, link=None):
        return {'document_id': did, 'source_id': did + ':' + str(uid), 'unit_id': str(uid)}, None
    monkeypatch.setattr(gn, 'readable_article', readable)
    monkeypatch.setattr(gn, '_location_label', lambda inv, identity, row, action:
                        ld.title_of(DOCS[identity['document_id']]) + ' · ' + str(row.get('heading') or identity.get('unit_id')))
    return S(s=s, p={'turn': 1}, question=question)


def test_phrases_find_named_described_and_nameless_rules_but_not_the_rule_itself():
    found = {p['phrase']: p for p in ld.phrases(GUIDE_TEXT)}
    assert found['관련 준칙']['form'] == 'NAMELESS' and '신상품' in found['관련 준칙']['clause']
    assert found['세부 준칙']['form'] == 'NAMELESS' and '전결권' in found['세부 준칙']['clause']
    assert found['상품 판매 및 사후관리 관련 준칙']['form'] == 'DESCRIBED'
    assert found['상품 판매 및 사후관리 관련 준칙']['descriptor'] == '상품 판매 및 사후관리'
    assert found['위험관리기준 시행세칙']['form'] == 'NAMED' and found['위험관리기준 시행세칙']['kind'] == '세칙'
    assert found['신규사업 심의위원회 지침']['form'] == 'NAMED'
    assert '지침' not in found and '이 지침' not in found  # the citing rule itself


def test_alias_declared_in_the_same_text_names_the_long_title():
    text = '고난도금융투자상품 제조 및 판매에 관한 영업행위준칙(이하 "고난도상품준칙")에 해당하는 상품은 고난도상품준칙에서 정하는 바에 따라 처리한다.'
    named = [p for p in ld.phrases(text) if p['phrase'] == '고난도상품준칙']
    assert named and named[0]['name'] == '고난도금융투자상품 제조 및 판매에 관한 영업행위준칙'


def test_title_keys_drop_folder_numbers_and_edition_tails():
    assert ld.title_of(DOCS['product']) == '상품관리준칙'
    assert ld.title_of(P + '01 위험관리기준시행세칙 > 위험관리기준시행세칙(20160823).docx') == '위험관리기준시행세칙'
    assert ld.kind_of(ld.nospace('위험관리기준 시행세칙')) == '세칙'


def test_nameless_rule_resolves_by_an_informative_title_word_and_the_latest_edition():
    s = session()
    phrase = next(p for p in ld.phrases(GUIDE_TEXT) if p['phrase'] == '관련 준칙')
    decision = ld.resolve(s, 'guide', phrase, '신규 상품 판단 기준')
    assert decision['status'] == 'CONFIRMED' and [d['document_id'] for d in decision['documents']] == ['product']
    assert '상품' in decision['words']
    # "위험"·"관리" are in half of the candidate titles: they do not tell them apart.
    assert '관리' not in decision['words']


def test_named_rule_resolves_by_exact_title_and_a_missing_one_is_none():
    s = session()
    found = {p['phrase']: p for p in ld.phrases(GUIDE_TEXT)}
    assert ld.resolve(s, 'guide', found['위험관리기준 시행세칙'])['documents'][0]['document_id'] == 'detail'
    missing = ld.resolve(s, 'guide', found['신규사업 심의위원회 지침'])
    assert missing['status'] == 'NONE' and missing['reason'] == 'NO_TITLE_MATCH'


def test_candidates_stay_inside_the_request_scope_and_internal_documents():
    s = session(scope={'guide', 'invest', 'ops', 'committee', 'law'})  # product rule not granted
    phrase = next(p for p in ld.phrases(GUIDE_TEXT) if p['phrase'] == '관련 준칙')
    decision = ld.resolve(s, 'guide', phrase, '신규 상품')
    assert all(d['document_id'] in s.scope for d in decision.get('documents', []))
    assert 'product' not in str(decision)
    assert all(r['document_id'] != 'law' for r in ld.catalogue(s))
    # A wider scope of the same session gets its own catalogue, not the narrower one.
    s.scope = set(DOCS)
    assert any(r['document_id'] == 'product' for r in ld.catalogue(s))


def test_tied_candidates_are_a_choice_and_unrelated_words_are_none():
    s = session()
    tied = {'phrase': '관련 준칙', 'form': 'NAMELESS', 'kind': '준칙', 'clause': '상품 투자 한도는', 'descriptor': None}
    s.matcher.documents['guide'] = P + '공통업무지침'  # the citing title adds no word
    decision = ld.resolve(s, 'guide', tied)
    assert decision['status'] == 'CHOICE' and {d['document_id'] for d in decision['documents']} == {'product', 'invest'}
    none = {'phrase': '관련 준칙', 'form': 'NAMELESS', 'kind': '준칙', 'clause': '보고 서식은', 'descriptor': None}
    assert ld.resolve(s, 'guide', none)['status'] == 'NONE'


def test_locations_read_question_titled_articles_of_the_resolved_rule(monkeypatch):
    s = session()
    inv = investigation(monkeypatch, s)
    rows = ld.locations(inv, [], {'guide:3': {'b1'}}, s.matcher.units)
    labels = [r['label'] for r in rows]
    assert '상품관리준칙 · 제2-1조 신상품 판단 기준' in labels
    read = [r for r in rows if r.get('specifies')]
    assert read and all(r['specifies'] == ['상품위원회운영지침 · 3'] and r['identity']['document_id'] == 'product' for r in read)
    assert '상품관리준칙 · 제2-1조 신상품 판단 기준' in {r['label'] for r in read}
    assert all(r['connection']['anchor_source_id'] == 'guide:3' and r['delegated'] for r in rows)
    kind, payload = s.repo.events[-1]
    assert kind == 'DELEGATED_DOCUMENTS_RESOLVED' and payload['model_called'] is False and payload['search_called'] is False
    assert payload['stored_as_citation'] is False
    statuses = {d['phrase']: d['status'] for d in payload['decisions']}
    assert statuses['신규사업 심의위원회 지침'] == 'NONE'
    # Structure lookups only through children_for (no corpus enumeration), each document once.
    lookups = s.matcher.units.lookups
    assert len(lookups) == len(set(lookups))


def test_already_read_targets_are_not_offered_again(monkeypatch):
    s = session()
    inv = investigation(monkeypatch, s)
    rows = ld.locations(inv, [], {'guide:3': {'b1'}, 'product:a2': {'x'}}, s.matcher.units)
    assert all(r['identity']['source_id'] != 'product:a2' for r in rows)


def test_switch_off_returns_nothing_and_records_nothing(monkeypatch):
    monkeypatch.setenv('GENOS_DELEGATION_LINKS', 'off')
    s = session()
    inv = investigation(monkeypatch, s)
    assert ld.locations(inv, [], {'guide:3': {'b1'}}, s.matcher.units) == [] and s.repo.events == []


def test_external_documents_are_not_anchors(monkeypatch):
    s = session()
    inv = investigation(monkeypatch, s)
    record = {'source_id': 'law:3', 'document_id': 'law', 'offer': {'unit_id': '3'}, 'evidence': []}
    monkeypatch.setattr(inventory, 'acquired_records', lambda p, **_: {'g1': record})
    s.store = S(source=lambda did, bid: {'text': GUIDE_TEXT})
    assert ld.locations(inv, [], {'law:3': {'b1'}}, s.matcher.units) == [] and s.repo.events == []


def test_unread_locations_keeps_the_specification_of_linked_rows(monkeypatch):
    s = session()
    inv = investigation(monkeypatch, s)
    monkeypatch.setattr(gn, 'scan_read_originals', lambda inv, known: {'cited': {}, 'defers': {}, 'contexts': {}})
    monkeypatch.setattr(gn, 'phrase_hints', lambda *a, **k: {})
    monkeypatch.setattr(gn, 'cited_locations', lambda *a, **k: [])
    monkeypatch.setattr(gn, 'delegated_locations', lambda *a, **k: [])
    monkeypatch.setattr(gn, 'relation_locations', lambda *a, **k: [])
    monkeypatch.setattr(gn, 'vector_top_locations', lambda *a, **k: [])
    import semantic_runtime.vector_navigation as vn
    monkeypatch.setattr(vn, 'top_candidates', lambda inv, n: [])
    s.tools = S(sources={'guide:3': {'document_id': 'guide', 'unit_id': '3', 'blocks': [{'block_id': 'b1'}]}})
    inv.p = {'turn': 1}
    import semantic_runtime.legal_agent.unit_reading as ur
    monkeypatch.setattr(inventory, 'acquired_records', lambda p, **_: {'g1': {'source_id': 'guide:3', 'document_id': 'guide',
        'offer': {'unit_id': '3', 'block_ids': ['b1']}, 'evidence': [{'source_id': 'guide:3', 'spans': [{'block_id': 'b1'}]}]}})
    rows = gn.unread_locations(inv)
    linked = [r for r in rows if r.get('delegated')]
    read = [r for r in linked if r.get('specifies')]
    assert read and all(r['relation'] for r in read)
    # The answer stage reads them as lower rules of the read article (server read, no model choice).
    reads = g.read_choices([], read)
    kinds = [k for k, _ in g.server_read_rows(reads, set())]
    assert kinds and set(kinds) == {'SPECIFIES'}
    assert all('delegated' in r for r in reads)


def test_the_same_words_in_two_clauses_are_resolved_separately_and_a_clause_word_alone_is_a_choice():
    s = session()
    text = ('1. "거래적격사"라 함은 집합투자업자 중 관련 준칙에서 정한 선정 기준을 충족한 회사를 말한다.\n'
            '3. "신상품"이라 함은 관련 준칙에서 정한 바에 따라 신상품으로 인정되는 상품을 말한다.')
    found = [p for p in ld.phrases(text) if p['phrase'] == '관련 준칙']
    assert len(found) == 2
    first, second = (ld.resolve(s, 'guide', p) for p in found)
    # 투자 meets only the clause (집합투자업자), not the citing title or question: offered, not read.
    assert first['status'] == 'CHOICE' and first['reason'] == 'CLAUSE_WORD_ONLY'
    assert second['status'] == 'CONFIRMED' and second['documents'][0]['document_id'] == 'product'


def test_choice_rows_are_offered_without_a_server_read(monkeypatch):
    s = body_session({})
    s.store = S(source=lambda did, bid: {'text': '1. 집합투자업자 중 관련 준칙에서 정한 선정 기준을 충족한 회사를 말한다.'})
    s.matcher.documents['guide'] = P + '공통업무지침'
    inv = investigation(monkeypatch, s, question='선정 기준을 충족한 회사')
    rows = ld.locations(inv, [], {'guide:3': {'b1'}}, s.matcher.units)
    assert rows and all(not r.get('specifies') for r in rows) and all('후보' in r['delegated'] for r in rows)


def test_narrowed_search_scope_still_reads_a_verified_delegated_document(monkeypatch):
    from semantic_runtime.legal_agent import query_scope as qs
    granted = []
    s = session()
    s.tools = S(sources={'guide:3': {'document_id': 'guide', 'unit_id': '3'},
                         'product:a2': {'document_id': 'product', 'unit_id': 'a2', 'blocks': [{'block_id': 'p1'}]}})
    monkeypatch.setattr(qs, 'active', lambda session: {'targets': [{'document_id': 'guide', 'unit_id': None}]})
    monkeypatch.setattr(qs, 'grant', lambda session, sid, blocks, witness: granted.append((sid, witness['connection']['kind'])))
    monkeypatch.setattr(gn, '_acquired_blocks', lambda inv: {'guide:3': {'b1'}})
    inv = S(s=s, p={})
    identity = {'document_id': 'product', 'source_id': 'product:a2', 'unit_id': 'a2'}
    link = {'kind': 'DELEGATED_DOCUMENT', 'anchor_source_id': 'guide:3', 'phrase': '관련 준칙'}
    assert gn.grant_connected_read(inv, identity, link) is None and granted == [('product:a2', 'DELEGATED_DOCUMENT')]
    # The phrase must stand in the acquired anchor text.
    assert gn.grant_connected_read(inv, identity, {**link, 'phrase': '없는 준칙'}) == 'CONNECTION_NOT_VERIFIED'


class OracleUnits(Units):
    """Request document memo shape (Units.document_rows / unit_count); counts listings."""
    def __init__(self, sizes=None):
        super().__init__()
        self.listings = []; self.sizes = sizes or {}

    def unit_count(self, did):
        return self.sizes.get(did, len(ARTICLES.get(did, [])) + 1)

    def document_rows(self, did):
        self.listings.append(did)
        yield {'document_id': did, 'unit_id': 'root', 'unit': self[(did, 'root')]}
        for uid, _, _ in ARTICLES.get(did, []):
            yield {'document_id': did, 'unit_id': uid, 'unit': self[(did, uid)]}

    def children_for(self, did, parent):
        raise AssertionError('root view would push out the navigation document')


def test_oracle_rounds_list_each_document_once_and_check_each_location_once(monkeypatch):
    s = session(); s.matcher.units = OracleUnits()
    inv = investigation(monkeypatch, s)
    checks = []
    original = gn.readable_article
    monkeypatch.setattr(gn, 'readable_article', lambda inv, did, uid, link=None: (checks.append((did, uid)), original(inv, did, uid, link))[1])
    first = ld.locations(inv, [], {'guide:3': {'b1'}}, s.matcher.units)
    for _ in range(2):  # later answer rounds, same originals
        again = ld.locations(inv, [], {'guide:3': {'b1'}}, s.matcher.units)
    assert [r['label'] for r in again] == [r['label'] for r in first] and first
    assert sorted(s.matcher.units.listings) == sorted(set(s.matcher.units.listings))  # each document listed once
    assert len(checks) == len(set(checks))  # each location checked once
    assert sum(k == 'DELEGATED_DOCUMENTS_RESOLVED' for k, _ in s.repo.events) == 1  # same decisions: one record


def test_a_document_above_the_listing_bound_is_not_listed(monkeypatch):
    s = session(); s.matcher.units = OracleUnits(sizes={'product': 5000})
    inv = investigation(monkeypatch, s)
    rows = ld.locations(inv, [], {'guide:3': {'b1'}}, s.matcher.units)
    assert 'product' not in s.matcher.units.listings and all(r['identity']['document_id'] != 'product' for r in rows)
    payload = s.repo.events[-1][1]
    assert any(a.get('skipped') == 'DOCUMENT_TOO_LARGE' for d in payload['decisions'] for a in d['articles'])


def test_only_lines_about_the_question_are_server_read(monkeypatch):
    """ADR-1484 q3: a question about 용어 followed the 신상품 line too. Words of the citing rule's own
    title (the question names it) and of the handed-over rule's name do not make a line relevant."""
    s = session()
    inv = investigation(monkeypatch, s, question='상품위원회 운영지침에 정의되지 않은 용어는 어디에서 정하나요?')
    rows = ld.locations(inv, [], {'guide:3': {'b1'}}, s.matcher.units)
    server = {r['identity']['document_id'] for r in rows if r.get('specifies')}
    assert server == {'detail'}
    lines = {d['phrase']: d['question_words_in_line'] for d in s.repo.events[-1][1]['decisions'] if 'question_words_in_line' in d}
    assert lines['위험관리기준 시행세칙'] >= 1 and lines['관련 준칙'] == 0


def test_an_equal_title_word_ranks_above_a_contained_one():
    s = session()
    picks = ld.target_articles(s, 'product', ['신상품', '기준'])
    assert picks[0]['coordinate'] == '제2-1조'  # 신상품 판단 기준: equal 기준 and 신상품 ⊃ 상품 handled


class BodyIndex:
    """Unit body index restricted by the caller's allowed source set; records the words asked."""
    def __init__(self, bodies):
        self.bodies = bodies; self.calls = []

    def rank_page(self, db, terms, allowed, *, cursor=None, limit=16, unit_keys=None):
        self.calls.append((list(terms), sorted(allowed)))
        items = [{'key': sid, 'source_id': sid, 'document_id': sid.split(':')[0], 'unit_id': sid.split(':')[1],
                  'article_unit_id': sid.split(':')[1], 'heading': heading, 'text': text, 'score': -1}
                 for sid, (heading, text) in self.bodies.items() if sid in allowed and any(t in text for t in terms)]
        return {'items': items[:limit], 'total': len(items), 'next_cursor': None}


def body_session(bodies):
    s = session()
    s.tools = S(sources={**{sid: {'document_id': sid.split(':')[0]} for sid in bodies}, 'guide:3': {'document_id': 'guide', 'unit_id': '3'}})
    s.matcher.unit_fulltext = BodyIndex(bodies); s.matcher.unit_fulltext_db = S()
    return s


def test_stage_two_searches_the_target_body_and_offers_without_reading(monkeypatch):
    # No article title of 상품관리준칙 holds 위임·한도; its body does. Offered with the words, not read by the server.
    s = body_session({'product:a3': ('제2-2조 (상품 판매 프로세스)', '③ 상품 판매 승인 위임 한도는 다음 각 호와 같다.'),
                      'invest:b1': ('제1조', '위임 한도')})
    s.store = S(source=lambda did, bid: {'text': '② 제1항에서 정하지 않은 상품 관련 위임 한도에 관한 사항은 세부 준칙에서 정한다.'})
    inv = investigation(monkeypatch, s, question='상품의 위임 한도는?')
    rows = ld.locations(inv, [], {'guide:3': {'b1'}}, s.matcher.units)
    product = [r for r in rows if r['identity']['document_id'] == 'product']
    assert product and all(not r.get('specifies') and '본문에 질문 낱말' in r['delegated'] for r in product)
    words, allowed = s.matcher.unit_fulltext.calls[0]
    assert allowed == ['product:a3']  # only the target document
    assert '상품' not in words and '위임' in words  # the citing/target title word does not search
    payload = s.repo.events[-1][1]
    assert payload['search_called'] is True and payload['body_searches'][0]['hits'] == 1


def test_stage_three_offers_the_table_of_contents_when_title_and_body_miss(monkeypatch):
    s = body_session({'product:a1': ('제1-1조 (목적)', '이 준칙은 상품 도입 기준을 정한다.')})
    s.store = S(source=lambda did, bid: {'text': '② 제1항에서 정하지 않은 상품 관련 결재 순서에 관한 사항은 세부 준칙에서 정한다.'})
    inv = investigation(monkeypatch, s, question='상품 결재 순서는?')
    rows = [r for r in ld.locations(inv, [], {'guide:3': {'b1'}}, s.matcher.units) if r['identity']['document_id'] == 'product']
    assert rows and all(not r.get('specifies') and '목차' in r['delegated'] for r in rows)
    assert '제2-1조 신상품 판단 기준' in rows[0]['delegated']


def test_only_an_equal_title_word_is_read_by_the_server(monkeypatch):
    # 상품 is contained in 신상품 but equal to no title word of 제2-2조 alone → offered, not read; 제2-1조 has 판단 기준.
    s = session()
    inv = investigation(monkeypatch, s, question='신상품 판단 기준은?')
    rows = ld.locations(inv, [], {'guide:3': {'b1'}}, s.matcher.units)
    read = {r['label'] for r in rows if r.get('specifies')}
    assert '상품관리준칙 · 제2-1조 신상품 판단 기준' in read


def test_body_search_uses_question_words_only(monkeypatch):
    s = body_session({'product:a3': ('제2-2조', '③ 상품 판매 승인 위임 한도는 다음 각 호와 같다.')})
    s.store = S(source=lambda did, bid: {'text': '② 제1항에서 정하지 않은 상품 관련 집합투자업자 위임 한도에 관한 사항은 세부 준칙에서 정한다.'})
    inv = investigation(monkeypatch, s, question='상품의 위임 한도는?')
    ld.locations(inv, [], {'guide:3': {'b1'}}, s.matcher.units)
    words = set(s.matcher.unit_fulltext.calls[0][0])
    assert words <= {'위임', '한도'} and words  # not the clause's 집합·투자·업자
