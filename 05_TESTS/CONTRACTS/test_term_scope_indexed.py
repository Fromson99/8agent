"""Term-in-scope check on Oracle by one indexed read (2026-11-11, term-scope-indexed on MAIN215).

Field 11-11: navigation_match._in_scope's `occurrence JOIN source` went through the plan translator,
which expanded every source row of the release for each occurrence of the term (60 s ReadTimeout in a
document comparison; 121 s for one common term on 21 local Gold documents). Oracle tools now answer
with one SQL on the physical key columns that stops at the first article in scope.
"""
from types import SimpleNamespace

import pytest

from semantic_runtime import oracle_query_index as qi
from semantic_runtime.navigation_match import ReverseMatcher
from semantic_runtime.oracle_dp_io import DPError


def tools(rows=(1,)):
    sent = []

    class SQL:
        def query(self, statement, binds=(), *, limit=100):
            sent.append((statement, dict((n, v) for n, v, _ in binds), limit))
            return [{'FOUND': r} for r in rows]
    request = SimpleNamespace(release_id='rel', sql=SQL(),
                              records=SimpleNamespace(table=lambda kind: 'ROWS'))
    t = qi.Tools.__new__(qi.Tools)
    t.request = request
    t.db = SimpleNamespace(tables={'occurrence': ('k.occurrence', {}), 'source': ('k.source', {})})
    t.sources = SimpleNamespace(kind='k.source')
    t.scope = {'d1', 'd2', 'd3'}
    return t, sent


def test_one_indexed_read_stops_at_first_article_and_is_remembered():
    t, sent = tools()
    assert t.term_in_documents('concept:a', {'d1', 'd2'}) is True
    assert t.term_in_documents('concept:a', ['d2', 'd1']) is True
    assert len(sent) == 1
    statement, binds, limit = sent[0]
    assert limit == 1 and statement.endswith('FETCH FIRST 1 ROWS ONLY')
    assert 'JSON_TABLE(o.VALUE_JSON' not in statement and 'JSON_TABLE(s.VALUE_JSON' not in statement
    assert 's.LOOKUP_ID=o.OWNER_ID' in statement and 'o.LOOKUP_ID=:t_key' in statement
    assert binds['t_key'] == 'concept:a' and binds['t_documents'] == '["d1","d2"]'
    assert binds['t_occurrence'] == 'k.occurrence' and binds['t_source'] == 'k.source'


def test_absent_term_and_other_scope_are_separate_answers():
    t, sent = tools(rows=())
    assert t.term_in_documents('concept:a', {'d1'}) is False
    assert t.term_in_documents('concept:a', {'d2'}) is False
    assert len(sent) == 2
    assert t.term_in_documents('concept:a', set()) is False and len(sent) == 2


def test_scope_outside_request_is_refused():
    t, sent = tools()
    with pytest.raises(DPError, match='QUERY_SCOPE'):
        t.term_in_documents('concept:a', {'d1', 'other'})
    assert not sent


def test_hashed_key_keeps_the_full_value_predicate():
    t, sent = tools()
    long_id = 'moleg:legal_terms:' + 'x' * 600
    t.term_in_documents(long_id, {'d1'})
    statement, binds, _ = sent[0]
    assert binds['t_key'].startswith('sha256:') and binds['t_term'] == long_id
    assert "JSON_VALUE(o.VALUE_JSON,'$.term_id'" in statement


def test_navigation_match_uses_the_oracle_check_instead_of_the_join():
    asked = []

    class DB:
        def execute(self, *a):
            raise AssertionError('the occurrence/source join must not run on Oracle')
    m = ReverseMatcher.__new__(ReverseMatcher)
    m.tools = SimpleNamespace(terms={'concept:a': {}, 'concept:b': {'scope_document_id': 'z'}}, db=DB(),
                              term_in_documents=lambda tid, scope: asked.append((tid, set(scope))) or True)
    assert m._in_scope('concept:a', {'d1'}) is True
    assert m._in_scope('concept:b', {'d1'}) is False  # scoped to another document: no read
    assert m._in_scope('concept:missing', {'d1'}) is False
    assert asked == [('concept:a', {'d1'})]


def test_sqlite_tools_keep_the_join():
    rows = []

    class DB:
        def execute(self, statement, params):
            rows.append(statement)
            return SimpleNamespace(fetchone=lambda: (1,))
    m = ReverseMatcher.__new__(ReverseMatcher)
    m.tools = SimpleNamespace(terms={'concept:a': {}}, db=DB())
    assert m._in_scope('concept:a', {'d1'}) is True
    assert rows and 'JOIN source' in rows[0]
