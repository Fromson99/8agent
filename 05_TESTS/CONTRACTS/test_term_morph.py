"""Glossary terms start and end on noun morphemes, in questions and in articles."""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '00_SYSTEM/WORKSPACE.json').is_file())
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from semantic_runtime import navigation_match as nm  # noqa: E402
from semantic_runtime import term_morph as tm  # noqa: E402


def test_article_fragments_are_not_terms():
    assert tm.aligned_keys('제3조의2에 따른 사항을 확인하기 위하여') == {'사항', '확인'}
    keys = tm.aligned_keys('다음 각 호의 어느 하나에 해당하는 경우')
    assert {'호의', '하나', '해당하'}.isdisjoint(keys) and {'해당', '경우'} <= keys


def test_real_nouns_survive_including_near_best_readings():
    assert '대주' in tm.aligned_keys('당사가 대주로써')          # best reading is 대/VV 어/EC 주/VX
    assert '호의' in tm.aligned_keys('상대방의 호의로 받은 금품')  # 好意, not a locator here
    assert '투자권유대행인' in tm.aligned_keys('투자권유대행인의 금지행위')


def index(*labels):
    m = nm.MorphIndex()
    for label in labels:
        m.add(label, nm.norm(label))
    return m


def test_question_endings_and_verbs_do_not_seed():
    m = index('하나', '위해', '회사', '담보')
    assert [h['text'] for h in m.match('회사가 담보를 꼭 받아야 하나요?')] == ['회사', '담보']
    assert [h['text'] for h in m.match('이해상충 방지를 위해 회사가 해야 하는 조치')] == ['회사']


def test_longest_noun_run_wins_without_overlap():
    m = index('투자', '투자권유', '투자권유대행인', '금지행위')
    assert [h['text'] for h in m.match('투자권유대행인의 금지행위에 해당하는 경우')] == ['투자권유대행인', '금지행위']


def test_registered_spacing_is_required():
    m = index('승인요건')
    assert m.match('승인 요건이 필요한가') == []
    assert [h['text'] for h in m.match('승인요건이 필요한가')] == ['승인요건']


def test_specific_terms_come_first():
    matcher = nm.ReverseMatcher.__new__(nm.ReverseMatcher)
    lookup = __import__('sqlite3').connect(':memory:')
    lookup.row_factory = __import__('sqlite3').Row
    lookup.execute('CREATE TABLE label(key,source,node_id,label,kind)')
    lookup.executemany('INSERT INTO label VALUES (?,?,?,?,?)',
                       [('경우', 'dictionary', 't-common', '경우', 'SOURCE_LABEL'),
                        ('담보', 'dictionary', 't-rare', '담보', 'SOURCE_LABEL')])
    matcher.tools = SimpleNamespace(validate_scope=lambda x: x, df={'t-common': 900, 't-rare': 3},
                                    terms={'t-common': {'label': '경우'}, 't-rare': {'label': '담보'}})
    matcher.glossary = SimpleNamespace(dbs={'lookup': lookup})
    matcher.documents, matcher.document_context = {}, {}
    matcher.document_names, matcher.structures = nm.SurfaceIndex(), nm.SurfaceIndex()
    matcher.body = index('경우', '담보')
    result = matcher.starts('이 경우 담보를 받아야 하나요', ['doc'])
    assert [t['id'] for t in result['terms']] == ['t-rare', 't-common']


def test_pronoun_and_root_open_compounds_but_never_end_a_term():
    keys = tm.aligned_keys('자기주식 소각의무에 관한 규정')
    assert {'자기주식', '소각의무'} <= keys
    # PeCab 1.0.8 reads 민감도 as 민감/NNG + 도/JX; retain this known recall gap.
    assert '민감' in tm.aligned_keys('각 한도별(민감도/손실한도)')
    assert tm.aligned_keys('무엇인가요') == set()
    assert '상이' not in tm.aligned_keys('상충되거나 상이한 경우')


def test_statutory_phrases_match_as_whole_words():
    assert tm.phrase_label('대통령령으로 정하는 경우') and tm.phrase_label('지방자치단체의 장')
    assert not tm.phrase_label('투자권유대행인') and not tm.phrase_label('정하는')
    keys = [tm.fold(x) for x in ('대통령령으로 정하는 경우', '지방자치단체의 장')]
    prefixes = {}
    for k in keys:
        prefixes.setdefault(k[:2], []).append(k)
    text = '그 밖에 대통령령으로 정하는 경우에는 지방자치단체의 장이 정한다. 지방자치단체의 장학금'
    found = tm.phrase_spans(text, prefixes)
    assert found[keys[0]] == {(5, 18)}
    assert found[keys[1]] == {(21, 30)}   # 장학금 does not end on 장


def test_official_details_order_definitions_before_english():
    import sqlite3
    from semantic_runtime.navigation_loop import moleg_definitions
    db = sqlite3.connect(':memory:')
    assert moleg_definitions(db, 'moleg:legal_terms:1', '증권', 5) is None
    db.execute('CREATE TABLE moleg_detail(term_id,seq,kind,kind_name,label_key,text,fields,request_id,response_sha256)')
    db.executemany('INSERT INTO moleg_detail VALUES (?,?,?,?,?,?,?,?,?)', [
        ('moleg:legal_terms:1', '19823', '011403', '법령한영사전', '증권', 'securities', '{}', 'r1', 'h1'),
        ('moleg:legal_terms:1', '2210156', '011402', '법령정의사전', '증권', '「자본시장법」 제4조에 따른 증권을 말한다.', '{"출처": "A법"}', 'r2', 'h2'),
        ('moleg:legal_terms:2', '5368153', '011402', '법령정의사전', '증권', '다른 법의 정의', '{}', 'r3', 'h3')])
    rows = moleg_definitions(db, 'moleg:legal_terms:1', '증권', 5)
    assert [(r['kind'], r['match_kind']) for r in rows] == [
        ('011402', 'SOURCE_ID'), ('011403', 'SOURCE_ID'), ('011402', 'LABEL_CANDIDATE')]
    assert rows[0]['source_fields']['출처'] == 'A법' and rows[1]['content_type'] == 'TRANSLATION'
    # A 지식용어 with the same label receives the 법령용어 records as candidates only.
    knowledge = moleg_definitions(db, 'moleg:knowledge_terms:9', '증권', 5)
    assert {r['match_kind'] for r in knowledge} == {'LABEL_CANDIDATE'} and len(knowledge) == 3


def test_definitions_from_our_laws_rank_first():
    import sqlite3
    from semantic_runtime.navigation_loop import moleg_definitions
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE moleg_detail(term_id,seq,kind,kind_name,label_key,text,fields,request_id,response_sha256)')
    db.executemany('INSERT INTO moleg_detail VALUES (?,?,?,?,?,?,?,?,?)', [
        ('moleg:legal_terms:1', '1', '011402', '법령정의사전', '자금', '다른 법 정의', '{"출처": "서울대학교 규칙[교육부령]"}', 'r', 'h'),
        ('moleg:legal_terms:2', '2', '011402', '법령정의사전', '자금', '우리 법 정의', '{"출처": "자본시장과 금융투자업에 관한 법률[법률 제1호]"}', 'r', 'h')])
    rows = moleg_definitions(db, 'moleg:knowledge_terms:5', '자금', 5, ['자본시장과 금융투자업에 관한 법률'])
    assert [r['text'] for r in rows] == ['우리 법 정의', '다른 법 정의']


def test_one_syllable_everyday_words_only_when_admitted():
    m = nm.MorphIndex()
    m.add_short('빚', None)
    m.add('부채', 'x')
    assert [h['text'] for h in m.match('빚을 못 갚으면')] == ['빚']
    assert nm.MorphIndex().match('빚을 못 갚으면') == []
