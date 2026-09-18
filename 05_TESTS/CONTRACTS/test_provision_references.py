"""조문 인용을 항·호·목 마디까지 잇는 계약 — 마커 모양이 아니라 구조 위치로."""
import json
import sqlite3

from semantic_runtime.term_references import compile_references

SCHEMA = '''CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,article TEXT,json TEXT);
CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,PRIMARY KEY(source_id,reference_id));
CREATE TABLE source_unit_map(source_id TEXT,unit_id TEXT,parent_id TEXT,ordinal TEXT,surface TEXT,block_ids TEXT,PRIMARY KEY(source_id,unit_id));'''


def article(db, sid, doc, name, heading, root, blocks, units):
    """blocks: [(block_id, text)], units: [(unit_id, parent, ordinal, surface, [block_ids])]"""
    value = {'id': sid, 'document_id': doc, 'document_name': name, 'heading': heading,
             'unit_id': root, 'blocks': [{'block_id': b, 'text': t} for b, t in blocks]}
    db.execute('INSERT INTO source VALUES (?,?,?,?)', (sid, doc, heading, json.dumps(value, ensure_ascii=False)))
    for uid, parent, ordinal, surface, bids in units:
        db.execute('INSERT INTO source_unit_map VALUES (?,?,?,?,?,?)',
                   (sid, uid, parent, json.dumps(ordinal), surface, json.dumps(bids)))


def build():
    db = sqlite3.connect(':memory:')
    db.executescript(SCHEMA)
    # 협회식 틀: 제4조 아래 항이 `1)`, 그 아래 `(1)`
    article(db, 'k4', 'dk', '표준준칙', '제4조(적합성)', 'u4',
            [('10', '제4조(적합성)'), ('11', '1) 임직원은 확인한다.'), ('12', '(1) 재산상황'),
             ('13', '(2) 투자목적'), ('14', '2) 회사는 기록한다.')],
            [('u41', 'u4', [1], '1)', ['11']), ('u411', 'u41', [1], '(1)', ['12']),
             ('u412', 'u41', [2], '(2)', ['13']), ('u42', 'u4', [2], '2)', ['14'])])
    article(db, 'k5', 'dk', '표준준칙', '제5조(설명)', 'u5',
            [('20', '제5조(설명) 제4조제1항제2호에 따른 목적을 확인하고 제4조제1항 및 제2항을 준용한다.'),
             ('21', '1) 설명한다.'), ('22', '2) 제1항에도 불구하고 제4조제9항은 제외한다.')],
            [('u51', 'u5', [1], '1)', ['21']), ('u52', 'u5', [2], '2)', ['22'])])
    # 법령식 틀: 항은 ①, 호는 `1.`, 호의2 까지
    article(db, 'l9', 'dl', 'RAW > law > 자본시장법', '제9조(정의)', 'v9',
            [('30', '제9조(정의)'), ('31', '⑰ 이 법에서 다음 각 호'), ('32', '1. 하나'),
             ('33', '2의2. 둘의둘'), ('34', '⑱ 이 항에서 제2호에 해당하는 자')],
            [('v917', 'v9', [17], '⑰', ['31']), ('v9171', 'v917', [1], '1.', ['32']),
             ('v91722', 'v917', [2, 2], '2의2.', ['33']), ('v918', 'v9', [18], '⑱', ['34']),
             ('v9182', 'v918', [2], '2.', [])])
    article(db, 'l10', 'dl', 'RAW > law > 자본시장법', '제10조(적용)', 'v10',
            [('40', '제10조(적용) 「자본시장법」 제9조제17항제2호의2에 해당하는 자와 제3조부터 제5조까지'),],
            [])
    compile_references(db)
    return {(v['source_id'], v['locator']): v for v in
            (json.loads(p) for (p,) in db.execute('SELECT json FROM reference'))}


def test_kofia_frame_citation_lands_on_the_one_paren_unit():
    refs = build()
    r = refs[('k5', '제4조제1항제2호')]
    assert r['target_source_ids'] == ['k4'] and r['target_level'] == 'provision'
    assert r['target_unit_path'] == ['1)', '(2)'] and r['target_block_ids'] == ['13']


def test_paragraph_citation_reads_the_whole_paragraph():
    refs = build()
    r = refs[('k5', '제4조제1항')]
    assert r['target_unit_path'] == ['1)'] and r['target_block_ids'] == ['11', '12', '13']


def test_continued_citation_belongs_to_the_previous_article():
    refs = build()
    r = refs[('k5', '제2항')]           # `제4조제1항 및 제2항`
    assert r['target_source_ids'] == ['k4'] and r['target_unit_path'] == ['2)']
    assert r['resolution'] == 'EXACT_CONTINUED_PROVISION'


def test_bare_paragraph_is_this_article():
    refs = build()
    r = refs[('k5', '제1항')]           # 5조 2) 안의 `제1항에도 불구하고`
    assert r['target_source_ids'] == ['k5'] and r['target_unit_path'] == ['1)']


def test_bare_item_inside_a_paragraph_is_that_paragraphs_item():
    refs = build()
    r = refs[('l9', '제2호')]           # ⑱ 안의 `제2호` → ⑱ 2.
    assert r['target_unit_path'] == ['⑱', '2.']


def test_law_frame_with_branch_number_and_folder_prefixed_name():
    refs = build()
    r = refs[('l10', '제9조제17항제2호의2')]
    assert r['resolution'] == 'EXACT_NAMED_DOCUMENT_ARTICLE'
    assert r['target_unit_path'] == ['⑰', '2의2.'] and r['target_block_ids'] == ['33']


def test_missing_provision_still_reaches_the_article_and_says_why():
    refs = build()
    r = refs[('k5', '제4조제9항')]
    assert r['target_source_ids'] == ['k4'] and r['target_level'] == 'article'
    assert r['reason'] == 'PROVISION_NOT_IN_STRUCTURE'


def test_ranges_stay_unresolved():
    refs = build()
    assert refs[('l10', '제3조')]['target_source_ids'] == []


def test_chained_continuations_keep_the_first_article():
    db = sqlite3.connect(':memory:')
    db.executescript(SCHEMA)
    article(db, 'k4', 'dk', '표준준칙', '제4조(적합성)', 'u4',
            [('10', '제4조(적합성)'), ('11', '1) 가'), ('12', '2) 나'), ('13', '3) 다')],
            [('u41', 'u4', [1], '1)', ['11']), ('u42', 'u4', [2], '2)', ['12']), ('u43', 'u4', [3], '3)', ['13'])])
    article(db, 'k5', 'dk', '표준준칙', '제5조(설명)', 'u5',
            [('20', '제5조(설명) 제4조제1항, 제2항 및 제3항을 준용한다.')], [])
    compile_references(db)
    refs = {json.loads(p)['locator']: json.loads(p) for (p,) in db.execute('SELECT json FROM reference')}
    assert refs['제3항']['target_source_ids'] == ['k4'] and refs['제3항']['target_unit_path'] == ['3)']
