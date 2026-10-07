"""Orphan public-glossary headwords: explained as references, never article seeds."""
import sqlite3
from types import SimpleNamespace

from semantic_runtime.navigation_match import ReverseMatcher
from semantic_runtime.term_agent import reference_note
from semantic_runtime.work_navigation import WorkSession

DOC = 'doc-1'


def mem(*ddl):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    for statement in ddl:
        db.execute(statement)
    return db


def matcher():
    store = mem('CREATE TABLE document(document_id,name,json)', 'CREATE TABLE source_unit(document_id,unit_id,parent_id,json)')
    store.execute("INSERT INTO document VALUES (?,?,'{}')", (DOC, '조세특례제한법 시행령'))
    tdb = mem('CREATE TABLE source(id,document_id,json)', 'CREATE TABLE occurrence(term_id,source_id)',
              'CREATE TABLE moleg_relation(source_id,target_id,code)')
    tdb.execute("INSERT INTO source VALUES ('s1',?,'{\"unit_id\":\"0\",\"heading\":\"제1조\"}')", (DOC,))
    terms = {
        'econedu:row:1': {'label': '그린벨트', 'source': 'econedu'},        # orphan
        'nts:1': {'label': '가결산', 'source': 'nts'},                     # occurs in the article
        'econedu:row:2': {'label': '유턴기업', 'source': 'econedu'},        # bridged via 일상용어
        'moleg:everyday_terms:9': {'label': '유턴기업'},
        'moleg:knowledge_terms:5': {'label': '국내복귀기업'},
    }
    tdb.execute("INSERT INTO occurrence VALUES ('nts:1','s1')")
    tdb.execute("INSERT INTO occurrence VALUES ('moleg:knowledge_terms:5','s1')")
    tdb.execute("INSERT INTO moleg_relation VALUES ('moleg:knowledge_terms:5','moleg:everyday_terms:9','140301')")
    lookup = mem('CREATE TABLE label(label,key,source,node_id)')
    for tid, term in terms.items():
        if not tid.startswith('moleg:'):
            lookup.execute('INSERT INTO label VALUES (?,?,?,?)', (term['label'], term['label'], 'dictionary', tid))
    tools = SimpleNamespace(db=tdb, terms=terms, validate_scope=lambda x: x)
    return ReverseMatcher(store, tools, SimpleNamespace(dbs={'lookup': lookup}))


def test_orphan_headword_is_a_reference_not_a_seed():
    result = matcher().starts('그린벨트 안에서 가결산은 어떻게 하나요', [DOC])
    assert [t['id'] for t in result['terms']] == ['nts:1']
    assert [r['id'] for r in result['references']] == ['econedu:row:1']
    assert result['references'][0]['question_spans'][0]['text'] == '그린벨트'


def test_bridged_or_linked_headword_is_not_an_orphan():
    result = matcher().starts('유턴기업 지원은?', [DOC])
    assert [t['id'] for t in result['terms']] == ['moleg:knowledge_terms:5']
    assert result['references'] == []


def test_out_of_scope_article_keeps_headword_as_reference():
    result = matcher().starts('가결산이란?', ['other-doc'])
    assert result['terms'] == [] and [r['id'] for r in result['references']] == ['nts:1']


def test_reference_terms_carry_definition_and_skip_seeded_spans():
    seed = {'terms': [{'id': 'nts:1', 'question_spans': [{'start': 10, 'end': 13, 'text': '가결산'}]}],
            'references': [{'id': 'econedu:row:1', 'question_spans': [{'start': 0, 'end': 4, 'text': '그린벨트'}]},
                           {'id': 'econedu:row:3', 'question_spans': [{'start': 10, 'end': 13, 'text': '가결산'}]},
                           {'id': 'econedu:row:4', 'question_spans': [{'start': 20, 'end': 24, 'text': '정의없음'}]}]}
    defs = {'econedu:row:1': [{'id': 'entry-definition:econedu:row:1', 'text': '개발제한구역을 말한다.'}],
            'econedu:row:3': [{'id': 'd3', 'text': 'x'}], 'econedu:row:4': []}
    session = SimpleNamespace(seed=seed, t=SimpleNamespace(terms={k: {'label': k[-5:], 'source': 'econedu'} for k in defs}),
                              term_definitions=lambda tid, end: defs[tid])
    rows = WorkSession.reference_terms(session)
    assert [r['id'] for r in rows] == ['econedu:row:1']
    assert rows[0]['definition'] == '개발제한구역을 말한다.' and rows[0]['status'] == 'REFERENCE_ONLY_NOT_EVIDENCE'
    note = reference_note(rows)
    assert '경제교육 경제용어사전' in note and '근거가 아닙니다' in note and '조문이 없습니다' in note
