"""ADR-0544 S2 contracts (ADR-0543 eight + three precedence cases). run-002 fixture: non-range sentence: `<이름> 시행령/시행규칙` resolves the name first.

Sentences are copied from the active generation's source text. Run through
adr0544_runner.py so `semantic_runtime` is the frozen candidate revision.
"""
import json
import os
import sqlite3
from pathlib import Path

import pytest

from semantic_runtime import term_references
from semantic_runtime.term_references import compile_references

LAW = '자본시장과 금융투자업에 관한 법률'
GOV = '금융회사의 지배구조에 관한 법률'
MANUAL = '금융투자회사의 컴플라이언스 매뉴얼 Ⅲ편(자산운용)'
FORM = '상장예비심사신청서 서식-1 일반기업(2024.1.1 개정)'
UW = '증권 인수업무 등에 관한 규정'

SCHEMA = '''CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,article TEXT,json TEXT);
CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
CREATE TABLE reference_end(source_id TEXT,reference_id TEXT,PRIMARY KEY(source_id,reference_id));'''

ROWS = [
    ('K9', 'law', LAW, '제9조(정의)', ['제9조(정의) 대통령령으로 정하는 자를 말한다.']),
    ('K225', 'dec', LAW + ' 시행령', '제225조(환매가격 및 환매수수료)', ['제225조(환매가격 및 환매수수료) 환매가격은 다음과 같다.']),
    ('K14', 'rul', LAW + ' 시행규칙', '제14조(공개매수대상 주식등의 수의 산정방법)', ['제14조(공개매수대상 주식등의 수의 산정방법) 주식등의 수는 다음과 같다.']),
    ('G3', 'gov', GOV + ' 시행령', '제3조(특수관계인의 범위)', ['제3조(특수관계인의 범위) 다음 각 호의 자를 말한다.']),
    ('U1', 'uw', UW, '제1조(목적)', ['제1조(목적)\n이 규정은 「자본시장과 금융투자업에 관한 법률」(이하 “법”이라 한다) 제286조제1항제1호에 의하여 금융투자회사가 증권을 인수하는 데 필요한 사항을 정함을 목적으로 한다.']),
    ('U6', 'uw', UW, '제6조(공동주관회사)', ['② 제1항에 따른 주식등의 보유비율 산정에 관하여는 법 시행규칙 제14조제1항을 준용한다.']),
    ('M1', 'man', MANUAL, '2. 환매', ['환매청구에 응하는 경우 등 대통령령으로 정하는 경우(자본시장법 시행령 제225조)']),
    ('M2', 'man', MANUAL, '3. 자금세탁', ['☞ 특정금융정보법 시행령 제8조의6']),
    ('M3', 'man', MANUAL, '4. 평가', ['자산운용회사는 법 제238조제3항 및 시행령 제261조제3항에 따라 평가하여야 한다.']),
    ('F1', 'form', FORM, '1. 최대주주', ['6호가목에 의한 최대주주 본인과 금융회사의 지배구조에 관한 법률 시행령 제3조제1항에 따른 특수관계인']),
    ('C10', 'com', '상법', '제10조(적용)', ['제10조(적용) 시행령 제5조에 따른다.']),
    ('Y10', 'ydec', '유가증권시장 공시규정 시행세칙', '제1조(목적)', ['제1조(목적) 「자본시장과 금융투자업에 관한 법률 시행령」(이하 "법 시행령"이라 한다)에 따른다.']),
    ('Y11', 'ydec', '유가증권시장 공시규정 시행세칙', '제2조(범위)', ['다만, 법 시행령 제10조제2항제8호의 자 중 투자자문업자, 투자일임업자는 제외한다.']),
    ('K10', 'dec', LAW + ' 시행령', '제10조(전문투자자의 범위 등)', ['제10조(전문투자자의 범위 등) 다음 각 호의 자를 말한다.']),
    ('K9D', 'dec', LAW + ' 시행령', '제9조(기타)', ['제9조(기타) 다음과 같다.']),
    ('M4', 'man', MANUAL, '5. 실명', ['관련법령 | 금융실명법 제4조제1항제5호, 같은 법 시행령 제9조제1항에 따라 위탁자인 해외계열 금융투자회사']),
    ('M0', 'man', MANUAL, '1. 목적', ['이 매뉴얼은 「자본시장과 금융투자업에 관한 법률」(이하 "법"이라 한다)의 준수를 위한 것이다.']),
    ('T13', 'cit', '법인세법 시행령', '제13조(배당 또는 분배의제의 시기)', ['제13조(배당 또는 분배의제의 시기) 다음과 같다.']),
    ('T99', 'cit', '법인세법 시행령', '제99조(화물료)', ['1. 「항만공사법」에 의한 항만공사가 공급하는 동법 시행령 제13조제1항제1호나목의 규정에 의한 화물료']),
    ('C11', 'com', '상법', '제11조(위임)', ['제11조(위임) 이 법 시행령 제5조에 따른다.']),
    ('D5', 'comdec', '상법 시행령', '제5조(세부)', ['제5조(세부) 법 제10조에 따른다.']),
]


def build(anchor_table=False):
    db = sqlite3.connect(':memory:')
    db.executescript(SCHEMA)
    if anchor_table:  # forces the v2 compiler path through the dispatch wrapper
        db.execute('CREATE TABLE structure_anchor(source_id TEXT,unit_id TEXT,json TEXT)')
    for sid, doc, name, heading, texts in ROWS:
        value = {'id': sid, 'document_id': doc, 'document_name': 'RAW > ' + name, 'heading': heading, 'unit_id': None,
                 'blocks': [{'block_id': sid + str(i), 'text': t} for i, t in enumerate(texts)]}
        db.execute('INSERT INTO source VALUES (?,?,?,?)', (sid, doc, heading, json.dumps(value, ensure_ascii=False)))
    compile_references(db, {'자본시장법': LAW}, [])
    return [json.loads(p) for (p,) in db.execute('SELECT json FROM reference')]


def ref(refs, source, locator):
    hit = [r for r in refs if r['source_id'] == source and r['locator'].startswith(locator)]
    assert len(hit) == 1, (source, locator, [(r['source_id'], r['locator']) for r in refs])
    return hit[0]


def reached(r):
    """Article reached either as canonical target or as provision inspection candidate."""
    extra = [t.get('source_id') for t in r.get('inspection_targets') or []]
    return set(r['target_source_ids']) | set(extra)


def test_runner_imports_frozen_candidate():
    frozen = os.environ.get('ADR0544_FROZEN_ROOT')
    assert frozen, 'run through adr0544_runner.py'
    assert Path(term_references.__file__).resolve().is_relative_to(Path(frozen).resolve())


def test_declared_law_alias_then_enforcement_rule_suffix():
    r = ref(build(), 'U6', '제14조')
    assert r['document_name_hint'] == LAW + ' 시행규칙'
    assert r['document_hint_basis'] == 'declared+suffix'
    assert r.get('reason') != 'DOCUMENT_MISSING'
    assert 'K14' in reached(r)


def test_registered_alias_then_decree_suffix():
    r = ref(build(), 'M1', '제225조')
    assert r['document_name_hint'] == LAW + ' 시행령'
    assert r['document_hint_basis'] == 'registered+suffix'
    assert r['target_source_ids'] == ['K225']


def test_full_statute_name_then_decree_suffix():
    r = ref(build(), 'F1', '제3조')
    assert r['document_name_hint'] == GOV + ' 시행령'
    assert 'G3' in reached(r)


def test_unknown_name_stays_unresolved_without_self_title():
    r = ref(build(), 'M2', '제8조의6')
    assert r['target_source_ids'] == []
    assert r['document_name_hint'] != MANUAL + ' 시행령'
    assert r['document_name_hint'] is None


def test_bare_decree_in_non_statute_is_not_self_titled():
    r = ref(build(), 'M3', '제261조')
    assert r['target_source_ids'] == []
    assert r['document_name_hint'] != MANUAL + ' 시행령'


def test_statute_bare_decree_convention_kept():
    r = ref(build(), 'C10', '제5조')
    assert r['target_source_ids'] == ['D5']
    assert r['document_hint_basis'] == 'convention'


def test_self_law_then_decree_suffix():
    r = ref(build(), 'C11', '제5조')
    assert r['target_source_ids'] == ['D5']
    assert r['document_hint_basis'] == 'self+suffix'


def test_decree_law_convention_kept():
    r = ref(build(), 'D5', '제10조')
    assert r['target_source_ids'] == ['C10']
    assert r['document_hint_basis'] == 'convention'


def test_declared_suffixed_phrase_beats_composition():
    r = ref(build(), 'Y11', '제10조')
    assert r['document_name_hint'] == LAW + ' 시행령'
    assert r['document_hint_basis'] == 'declared'
    assert 'K10' in reached(r)


def test_untracked_same_law_is_not_the_declared_law():
    r = ref(build(), 'M4', '제9조')
    assert 'K9D' not in reached(r)
    assert r['document_name_hint'] != LAW + ' 시행령'


def test_same_law_after_named_statute_is_not_self_decree():
    r = ref(build(), 'T99', '제13조')
    assert 'T13' not in reached(r)
    assert r['document_name_hint'] != '법인세법 시행령'


# Supplementary (not an S2 criterion): the same contracts through the v2 compiler path.
@pytest.mark.parametrize('source,locator,hint', [
    ('U6', '제14조', LAW + ' 시행규칙'), ('M1', '제225조', LAW + ' 시행령'), ('F1', '제3조', GOV + ' 시행령')])
def test_v2_path_supplementary(source, locator, hint):
    r = ref(build(anchor_table=True), source, locator)
    assert r['document_name_hint'] == hint
