"""A body-search group no unit satisfies falls back to its rarest words (MAIN203 regression)."""
import sqlite3
import pytest

from semantic_runtime.oracle_query_fulltext import PROJECTION_ROWS, RELAX_WORDS, rare_words, relaxed_terms
from semantic_runtime.unit_fulltext import UnitFulltextIndex


def test_rare_words_take_rarest_first_within_word_and_row_limits():
    df = {'a': 5, 'b': 1, 'c': 3, 'd': 4, 'e': 2, 'zero': 0}
    assert rare_words(['a', 'b', 'c', 'd', 'e', 'zero'], df) == ['b', 'e', 'c', 'd'][:RELAX_WORDS]
    assert rare_words(['x', 'y'], {'x': 100, 'y': PROJECTION_ROWS}) == ['x']


def test_group_of_only_common_words_is_left_unchanged():
    terms, report = relaxed_terms(['조 항'], {'조 항': ('조', '항')}, {'조': 47520, '항': 47036})
    assert (terms, report) == (['조 항'], [])


def test_only_the_empty_group_is_replaced_and_words_are_not_repeated():
    terms, report = relaxed_terms(['이사 선임', '통지 의무', '통지 기한'],
        {'통지 의무': ('통지', '의무'), '통지 기한': ('통지', '기한')}, {'통지': 10, '의무': 20, '기한': 30})
    assert terms == ['이사 선임', '통지', '의무', '기한']
    assert [r['group'] for r in report] == ['통지 의무', '통지 기한']


@pytest.fixture
def index():
    db = sqlite3.connect(':memory:')
    db.executescript('''CREATE TABLE unit(key TEXT PRIMARY KEY,document_id TEXT,source_id TEXT);
        CREATE VIRTUAL TABLE unit_fts USING fts5(key UNINDEXED,body,tokenize="unicode61");''')
    for key, sid, body in (('k1', 's1', '이사 선임 절차'), ('k2', 's2', '통지 기한 연장'), ('k3', 's3', '보고 의무')):
        db.execute('INSERT INTO unit VALUES(?,?,?)', (key, 'd', sid))
        db.execute('INSERT INTO unit_fts VALUES(?,?)', (key, body))
    idx = UnitFulltextIndex.__new__(UnitFulltextIndex)
    idx.source_ids = frozenset(('s1', 's2', 's3'))
    idx.check_unchanged = lambda: None
    return idx, db


def test_sqlite_group_found_together_stays_exact(index):
    idx, db = index
    assert idx.relax_groups(db, ['이사 선임'], ['s1', 's2', 's3']) == (['이사 선임'], [])


def test_sqlite_group_with_no_unit_becomes_its_words(index):
    idx, db = index
    terms, report = idx.relax_groups(db, ['통지 의무'], ['s1', 's2', 's3'])
    assert sorted(terms) == ['의무', '통지'] and report[0]['group'] == '통지 의무'


def test_sqlite_emptiness_is_judged_inside_the_allowed_sources(index):
    idx, db = index
    assert idx.relax_groups(db, ['이사 선임'], ['s2'])[1][0]['group'] == '이사 선임'


def test_sqlite_single_word_makes_no_query(index):
    idx, db = index
    calls = []
    db.set_trace_callback(calls.append)
    assert idx.relax_groups(db, ['이사'], ['s1']) == (['이사'], [])
    assert calls == []
