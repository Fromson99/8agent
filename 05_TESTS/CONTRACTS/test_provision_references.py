"""조문 인용을 항·호·목 마디까지 잇는 계약 — 마커 모양이 아니라 구조 위치로."""
import json
import sqlite3

from semantic_runtime.term_references import compile_references

SCHEMA = '''CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,article TEXT,json TEXT);
CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,PRIMARY KEY(source_id,reference_id));
CREATE TABLE source_unit_map(source_id TEXT,unit_id TEXT,parent_id TEXT,ordinal TEXT,surface TEXT,block_ids TEXT,family TEXT,PRIMARY KEY(source_id,unit_id));
CREATE TABLE document_frame(document_id TEXT PRIMARY KEY,json TEXT);'''


def article(db, sid, doc, name, heading, root, blocks, units):
    """blocks: [(block_id, text)], units: [(unit_id, parent, ordinal, surface, [block_ids])]"""
    value = {'id': sid, 'document_id': doc, 'document_name': name, 'heading': heading,
             'unit_id': root, 'blocks': [{'block_id': b, 'text': t} for b, t in blocks]}
    db.execute('INSERT INTO source VALUES (?,?,?,?)', (sid, doc, heading, json.dumps(value, ensure_ascii=False)))
    for uid, parent, ordinal, surface, bids, *family in units:
        db.execute('INSERT INTO source_unit_map VALUES (?,?,?,?,?,?,?)',
                   (sid, uid, parent, json.dumps(ordinal), surface, json.dumps(bids), family[0] if family else None))


def frame(db, doc, ladder):
    from semantic_runtime.term_references import frame_roles
    db.execute('INSERT INTO document_frame VALUES (?,?)', (doc, json.dumps(frame_roles({'rungs': [{'families': f} for f in ladder]}))))


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


def test_range_is_one_case_and_stays_unresolved_when_structure_is_missing():
    refs = build()
    r = refs[('l10', '제3조부터제5조까지')]
    assert r['target_source_ids'] == []
    assert r['mention_text'] == '제3조부터 제5조까지'
    assert r['resolution_state'] == 'UNKNOWN'
    assert r['reason'] == 'RANGE_OR_SUBARTICLE_UNRESOLVED'


def test_article_and_provision_ranges_expand_with_per_target_extents():
    db = sqlite3.connect(':memory:')
    db.executescript(SCHEMA)
    frame(db, 'd', [['kr_article'], ['circled']])
    for number in range(2, 6):
        units = []
        blocks = [(str(number * 10), f'제{number}조')]
        if number == 3:
            blocks += [('31', '① 하나'), ('32', '② 둘'), ('33', '③ 셋')]
            units = [('u31', 'u3', [1], '①', ['31'], 'circled'),
                     ('u32', 'u3', [2], '②', ['32'], 'circled'),
                     ('u33', 'u3', [3], '③', ['33'], 'circled')]
        article(db, f'a{number}', 'd', '법', f'제{number}조', f'u{number}', blocks, units)
    article(db, 'a6', 'd', '법', '제6조', 'u6', [
        ('60', '제6조 제2조부터 제5조까지 및 제3조제1항부터 제3항까지를 준용한다.')], [])
    compile_references(db)
    refs = {json.loads(raw)['locator']: json.loads(raw) for (raw,) in db.execute('SELECT json FROM reference')}
    articles = refs['제2조부터제5조까지']
    assert articles['resolution_state'] == 'MULTI_TARGET'
    assert articles['target_source_ids'] == ['a2', 'a3', 'a4', 'a5']
    provisions = refs['제3조제1항부터제3항까지']
    assert provisions['resolution_state'] == 'MULTI_TARGET'
    assert provisions['target_source_ids'] == ['a3']
    assert [target['unit_id'] for target in provisions['targets']] == ['u31', 'u32', 'u33']
    rows = db.execute('SELECT source_id,unit_id,block_ids FROM reference_target WHERE reference_id=? ORDER BY ordinal',
                      (provisions['id'],)).fetchall()
    assert rows == [('a3', 'u31', '["31"]'), ('a3', 'u32', '["32"]'), ('a3', 'u33', '["33"]')]


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


def test_document_frame_citation_uses_its_own_markers():
    """조가 `14.`, 항이 `1)` 인 문서는 `14. 1)에 따른` 이라고 부른다 — 그 틀 그대로 잇는다."""
    db = sqlite3.connect(':memory:')
    db.executescript(SCHEMA)
    article(db, 'p14', 'dp', '표준투자권유준칙', '14. 설명의무', 'w14',
            [('50', '14. 설명의무'), ('51', '1) 임직원등은 설명하여야 한다.'), ('52', '(1) 상품의 내용'),
             ('53', '2) 확인받는다.')],
            [('w141', 'w14', [1], '1)', ['51']), ('w1411', 'w141', [1], '(1)', ['52']),
             ('w142', 'w14', [2], '2)', ['53'])])
    article(db, 'p15', 'dp', '표준투자권유준칙', '15. 외화증권', 'w15',
            [('60', '15. 외화증권'), ('61', '1) 외화증권은 14. 1)에 따른 설명시 13.2)와 함께 1. 목록은 무시한다.'),
             ('62', '부 칙(2022. 14. 1)')],
            [('w151', 'w15', [1], '1)', ['61'])])
    compile_references(db)
    refs = {json.loads(p)['locator']: json.loads(p) for (p,) in db.execute('SELECT json FROM reference')}
    r = refs['14.1)']
    assert r['target_source_ids'] == ['p14'] and r['target_unit_path'] == ['1)']
    assert r['target_block_ids'] == ['51', '52'] and r['resolution'] == 'EXACT_SAME_DOCUMENT_PROVISION'
    assert '13.2)' not in refs              # 틀에 13. 이 없으면 잇지 않는다
    assert not any(k.startswith('1.') for k in refs)
    rows = [json.loads(p) for (p,) in db.execute('SELECT json FROM reference')]
    assert sum(r['locator'] == '14.1)' for r in rows) == 1   # 부칙 날짜는 인용이 아니다



def test_item_citation_follows_the_frame_role_not_the_first_layer():
    """틀상 조 아래가 항(①)인 조에서 `제4조제2호` 는 ② 로 가지 않는다."""
    db = sqlite3.connect(':memory:')
    db.executescript(SCHEMA)
    frame(db, 'd', [['kr_장'], ['kr_article'], ['circled', 'dot_number:1'], ['dot_number:1']])
    article(db, 'a4', 'd', '규정', '제4조(정의)', 'u4', [('1', '제4조(정의)'), ('2', '① 가'), ('3', '② 나')],
            [('u41', 'u4', [1], '①', ['2'], 'circled'), ('u42', 'u4', [2], '②', ['3'], 'circled')])
    article(db, 'a5', 'd', '규정', '제5조(범위)', 'u5', [('4', '제5조(범위)'), ('5', '1. 하나'), ('6', '2. 둘')],
            [('u51', 'u5', [1], '1.', ['5'], 'dot_number:1'), ('u52', 'u5', [2], '2.', ['6'], 'dot_number:1')])
    article(db, 'a6', 'd', '규정', '제6조(적용)', 'u6', [('7', '제6조(적용) 제4조제2호 및 제5조제2호에 따른다.')], [])
    compile_references(db)
    refs = {json.loads(p)['locator']: json.loads(p) for (p,) in db.execute('SELECT json FROM reference')}
    assert refs['제4조제2호']['target_level'] == 'article'           # 제4조에는 호가 없다
    assert refs['제4조제2호']['reason'] == 'PROVISION_NOT_IN_STRUCTURE'
    assert refs['제5조제2호']['target_unit_path'] == ['2.']          # 항 없는 조의 호


def test_paren_frame_document_cites_with_its_own_markers():
    """이 문서 틀은 조→(1)→가. 이다. `제4조제1항제2호` 와 `제4조(1)` 이 모두 그 마디로 간다."""
    db = sqlite3.connect(':memory:')
    db.executescript(SCHEMA)
    frame(db, 'd', [['kr_article'], ['paren_number:both'], ['hangul_dot']])
    article(db, 'a4', 'd', '내규', '제4조(한도)', 'u4',
            [('1', '제4조(한도)'), ('2', '(1) 위험한도는'), ('3', '가. 시장위험'), ('4', '나. 신용위험')],
            [('u41', 'u4', [1], '(1)', ['2'], 'paren_number:both'),
             ('u411', 'u41', [1], '가.', ['3'], 'hangul_dot'), ('u412', 'u41', [2], '나.', ['4'], 'hangul_dot')])
    article(db, 'a5', 'd', '내규', '제5조(보고)', 'u5',
            [('5', '제5조(보고) 제4조제1항제2호의 한도와 제4조(1)에 따라 보고한다.')], [])
    compile_references(db)
    refs = {json.loads(p)['locator']: json.loads(p) for (p,) in db.execute('SELECT json FROM reference')}
    assert refs['제4조제1항제2호']['target_unit_path'] == ['(1)', '나.']
    assert refs['제4조(1)']['target_unit_path'] == ['(1)']
    assert refs['제4조(1)']['origins'] == ['raw_explicit_frame_hint']


def test_parenthesised_and_same_article_continuations():
    db = sqlite3.connect(':memory:')
    db.executescript(SCHEMA)
    frame(db, 'd', [['kr_article'], ['circled'], ['dot_number:1']])
    article(db, 'a2', 'd', '법', '제2조(평가)', 'u2', [('1', '제2조(평가)'), ('2', '① 가'), ('3', '1. 하나'), ('4', '② 나')],
            [('u21', 'u2', [1], '①', ['2'], 'circled'), ('u211', 'u21', [1], '1.', ['3'], 'dot_number:1'),
             ('u22', 'u2', [2], '②', ['4'], 'circled')])
    article(db, 'a9', 'd', '법', '제9조(적용)', 'u9', [('9', '제9조(적용) ① 가'), ('10', '② 나')],
            [('u91', 'u9', [1], '①', ['9'], 'circled'), ('u92', 'u9', [2], '②', ['10'], 'circled')])
    article(db, 'a3', 'd', '법', '제3조(준용)', 'u3', [
        ('20', '제3조(준용) 제2조(제1항제1호에 한정한다), 제2조(평가 등)제2항 및 같은 조 제1항과 별지 제2호서식에 따른다.')], [])
    compile_references(db)
    rows = [json.loads(p) for (p,) in db.execute('SELECT json FROM reference')]
    got = {(r['locator'], tuple(r['target_unit_path'])) for r in rows if r['target_source_ids'] == ['a2']}
    assert ('제1항제1호', ('①', '1.')) in got      # 괄호 안 — 앞의 제2조
    assert ('제2항', ('②',)) in got                # 조 제목 괄호 뒤 — 앞의 제2조
    assert ('같은조제1항', ('①',)) in got           # 같은 조 — 앞의 제2조
    assert not any(r['locator'].startswith('제2호') and r['origins'] == ['raw_explicit_provision_hint'] for r in rows)


def test_reverse_reference_keeps_the_source_paragraph_extent_and_explicit_role():
    """CM003형: target은 제26조제1항제3호, 역방향 READ는 제23조제4항 전체다."""
    db = sqlite3.connect(':memory:')
    db.executescript(SCHEMA)
    frame(db, 'reg', [['kr_article'], ['circled'], ['dot_number:1']])
    frame(db, 'rule', [['kr_article'], ['circled'], ['dot_number:1']])
    article(db, 'reg26', 'reg', '코스닥시장 상장규정', '제26조(신규상장 의무보유)', 'r26',
            [('300', '① 다음 각 호'), ('301', '3. 제3자 배정 취득자. 다만, 세칙으로 정하는 경우는 제외한다.')],
            [('r261', 'r26', [1], '①', ['300'], 'circled'),
             ('r2613', 'r261', [3], '3.', ['301'], 'dot_number:1')])
    article(db, 'rule23', 'rule', '코스닥시장 상장규정 시행세칙', '제23조(예외)', 's23',
            [('236', '④ 규정 제26조제1항제3호 단서에서 "세칙으로 정하는 경우"란 다음 각 호의 어느 하나에 해당하는 경우를 말한다.'),
             ('237', '1. 종업원이 취득한 경우'), ('238', '2. 벤처금융 또는 전문투자자가 취득한 경우')],
            [('s234', 's23', [4], '④', ['236'], 'circled'),
             ('s2341', 's234', [1], '1.', ['237'], 'dot_number:1'),
             ('s2342', 's234', [2], '2.', ['238'], 'dot_number:1')])
    compile_references(db)
    refs = [json.loads(row[0]) for row in db.execute('SELECT json FROM reference')]
    ref = next(row for row in refs if row.get('source_id') == 'rule23')
    assert ref['target_source_ids'] == ['reg26']
    assert ref['target_unit_id'] == 'r2613' and ref['target_block_ids'] == ['301']
    assert ref['source_unit_id'] == 's234' and ref['source_block_ids'] == ['236', '237', '238']
    assert ref['reference_role'] == 'SPECIFIES_DELEGATED_CASES_OF'

    # 기본 작업 큐도 상장규정 쪽에서 역조회해 시행세칙 제4항을 후보화한다.
    from types import SimpleNamespace
    from semantic_runtime.work_navigation import WorkSession
    session = WorkSession.__new__(WorkSession)
    session.t = SimpleNamespace(db=db, sources={
        'reg26': next(json.loads(row[0]) for row in db.execute("SELECT json FROM source WHERE id='reg26'")),
        'rule23': next(json.loads(row[0]) for row in db.execute("SELECT json FROM source WHERE id='rule23'"))})
    session.references_work = {}; session.metadata = {'reg26': {}, 'rule23': {}}
    session.pool = {}; session.followup_ids = set()
    session.discover_references('reg26')
    incoming = next(row for row in session.references_work.values() if row['direction'] == 'INCOMING')
    assert incoming['target_source_ids'] == ['rule23']
    assert incoming['target_unit_path'] == ['④']
    assert incoming['target_block_ids'] == ['236', '237', '238']
    assert 'rule23' in session.pool
