"""다른 법으로 가는 인용·위임과 그 역방향 — 약칭은 문서 선언·명명 관례·등록 사전으로만 푼다."""
import json
import sqlite3

from semantic_runtime.term_references import compile_references

SCHEMA = '''CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,article TEXT,json TEXT);
CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,PRIMARY KEY(source_id,reference_id));'''

LAW = '자본시장과 금융투자업에 관한 법률'


def build(rows, aliases=None, delegations=None):
    db = sqlite3.connect(':memory:')
    db.executescript(SCHEMA)
    for sid, doc, name, heading, texts in rows:
        value = {'id': sid, 'document_id': doc, 'document_name': name, 'heading': heading, 'unit_id': None,
                 'blocks': [{'block_id': sid + str(i), 'text': t} for i, t in enumerate(texts)]}
        db.execute('INSERT INTO source VALUES (?,?,?,?)', (sid, doc, heading, json.dumps(value, ensure_ascii=False)))
    compile_references(db, aliases or {}, delegations or [])
    refs = [json.loads(p) for (p,) in db.execute('SELECT json FROM reference')]
    ends = db.execute('SELECT source_id,reference_id FROM reference_end').fetchall()
    return refs, ends


BASE = [
    ('L9', 'law', 'RAW > law > ' + LAW, '제9조(정의)', ['제9조(정의) 대통령령으로 정하는 자를 말한다.']),
    ('L10', 'law', 'RAW > law > ' + LAW, '제10조(적용)', ['제10조(적용) 이 법 제9조에 따른다.']),
    ('D5', 'dec', 'RAW > law > ' + LAW + ' 시행령', '제5조(전문투자자)', ['제5조(전문투자자) 법 제9조에서 "대통령령으로 정하는 자"란 다음과 같다.']),
    ('R1', 'rule', 'RAW > law > 증권 규정', '제1조(목적)', ['제1조(목적) 「' + LAW + '」(이하 "자본법"이라 한다), 같은 법 시행령(이하 "영"이라 한다)에 따른다.']),
    ('R2', 'rule', 'RAW > law > 증권 규정', '제2조(준용)', ['제2조(준용) 자본법 제10조와 영 제5조, 「' + LAW + '」 제9조 및 동법 제10조를 준용한다.']),
    ('I1', 'int', '위험관리기준', '제3조(근거)', ['제3조(근거) 자본시장법 제9조 및 자본시장과금융투자업에관한법률 제10조에 따른다.']),
]


def target(refs, source, locator):
    hit = [r for r in refs if r['source_id'] == source and r['locator'] == locator]
    assert hit, (source, locator, [(r['source_id'], r['locator']) for r in refs])
    return hit[0]['target_source_ids']


def test_enforcement_decree_law_means_its_parent_statute():
    refs, _ = build(BASE)
    assert target(refs, 'D5', '제9조') == ['L9']                  # 시행령의 `법` = 상위 법률


def test_self_declared_and_same_law_aliases():
    refs, _ = build(BASE)
    assert target(refs, 'L10', '제9조') == ['L9']                 # 이 법
    assert target(refs, 'R2', '제10조') == ['L10']                # 선언 약칭 `자본법`
    assert target(refs, 'R2', '제5조') == ['D5']                  # `같은 법 시행령(이하 "영")`
    locs = [r for r in refs if r['source_id'] == 'R2' and r['locator'] == '제10조']
    assert len(locs) == 2 and all(r['target_source_ids'] == ['L10'] for r in locs)   # 동법 제10조 도


def test_internal_rule_reaches_the_statute_by_registered_or_spaced_name():
    refs, _ = build(BASE, aliases={'자본시장법': LAW})
    assert target(refs, 'I1', '제9조') == ['L9']                  # 등록 약칭
    assert target(refs, 'I1', '제10조') == ['L10']                # 띄어쓰기 없는 정식 이름


def test_official_delegation_and_reverse_direction():
    edge = {'kind': '시행령', 'link': '대통령령',
            'src': {'name': LAW, 'jo': '제9조', 'anchor': '제9조'},
            'dst': {'name': LAW + ' 시행령', 'jo': '제5조'}}
    refs, ends = build(BASE, delegations=[edge])
    official = [r for r in refs if r['resolution'] == 'OFFICIAL_DELEGATION']
    assert len(official) == 1 and official[0]['source_id'] == 'L9' and official[0]['target_source_ids'] == ['D5']
    incoming = {rid for sid, rid in ends if sid == 'L9'}
    # 법 제9조에서 보면: 공식 위임(나감) + 시행령·규정·내규가 부른 것(들어옴)
    callers = {r['source_id'] for r in refs if r['id'] in incoming}
    assert {'L9', 'D5', 'R2', 'L10'} <= callers


def test_joined_articles_keep_the_named_law():
    rows = BASE + [('R3', 'rule', 'RAW > law > 증권 규정', '제3조(적용)',
                    ['제3조(적용) 「' + LAW + '」 제9조제1항 및 제10조, 제9조 또는 제10조에 따른다.'])]
    refs, _ = build(rows)
    got = [r['target_source_ids'] for r in refs if r['source_id'] == 'R3' and r['origins'] == ['raw_explicit_article_hint']]
    assert got and all(t and t[0] in ('L9', 'L10') for t in got)
