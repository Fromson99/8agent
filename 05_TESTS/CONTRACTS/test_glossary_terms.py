"""용어 사전 표제어를 쪼개지 않는 본문 검색 낱말 (r6 붙은 구절 · r7 근접, ADR-1479/1480 후보, MAIN 미반영)."""


def test_glossary_terms_stay_one_phrase_in_the_body_search():
    from semantic_runtime import fulltext as ft
    from semantic_runtime.navigation_match import MorphIndex
    lexicon = MorphIndex()
    for word in ('IPO', '주식매수선택권', '증여의제'):
        lexicon.add(word, word)
    q = 'IPO 단계에서 벤처기업 주식매수선택권과 증여의제는?'
    assert ft.question_terms(q)[:3] == ['I', 'P', 'O']  # without a lexicon: morphemes as before
    terms = ft.question_terms(q, lexicon)
    assert terms[0] == 'I P O' and '주식~매수~선택' in terms and '증여~의제' in terms
    assert not {'I', 'P', 'O', '주식', '매수', '선택', '증여', '의제'} & set(terms) and '단계' in terms
    class Broken:
        surfaces = None
    assert ft.question_terms(q, Broken()) == ft.question_terms(q)  # an unreadable lexicon cuts nothing out


def test_glossary_terms_match_near_each_other_not_only_adjacent():
    import sqlite3
    from semantic_runtime import fulltext as ft
    assert ft.expression(['I P O', '주식~매수~선택', '단계']) == '"I P O" OR NEAR("주식" "매수" "선택", 5) OR "단계"'
    db = sqlite3.connect(':memory:'); db.execute('CREATE VIRTUAL TABLE t USING fts5(body,tokenize="unicode61")')
    rows = ['주식 매수 선택', '주식 의 매수 를 선택', '주식 x x x x x x x x 매수 선택', 'I P O 공모', 'I x P x O']
    for row in rows:
        db.execute('INSERT INTO t VALUES(?)', (row,))
    found = [r[0] for r in db.execute('SELECT body FROM t WHERE t MATCH ?', (ft.expression(['I P O', '주식~매수~선택']),))]
    assert found == ['주식 매수 선택', '주식 의 매수 를 선택', 'I P O 공모']


def test_oracle_near_groups_become_member_phrases_with_a_distance():
    from semantic_runtime.oracle_query_fulltext import UnitIndex
    from semantic_runtime import fulltext as ft
    phrases, near = UnitIndex.__new__(UnitIndex)._query_parts(['I P O', '주식~매수~선택', '단계'])
    assert phrases == [('i', 'p', 'o'), ('주식',), ('매수',), ('선택',), ('단계',)]
    span = ft.NEAR_DISTANCE + 2
    assert near == {1: (['매수', '선택'], span), 2: (['주식', '선택'], span), 3: (['주식', '매수'], span)}
