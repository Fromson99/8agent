"""Long CLOB binds in pieces and the remaining reference joins (2026-11-12, clob-pieces-reference-api on MAIN217).

A JDBC string bound to a CLOB position is refused past 32,767 bytes (ORA-01460); how GENOS ORDS binds a
CLOB-typed value is unknown, so serving sends any CLOB over 30,000 bytes as pieces joined in SQL.
"""
import json
from types import SimpleNamespace

import pytest

from semantic_runtime import oracle_dp_io
from semantic_runtime.oracle_dp_io import DPError, clob_pieces


def test_short_and_non_clob_binds_are_unchanged():
    statement = "SELECT 1 FROM T WHERE K IN (SELECT j.k FROM JSON_TABLE(:units,'$[*]' COLUMNS(k VARCHAR2(512) PATH '$')) j)"
    binds = [('units', json.dumps(['a'] * 10), 'CLOB'), ('big', 'x' * 40000, 'VARCHAR2')]
    assert clob_pieces(statement, binds) == (statement, binds)


def test_long_clob_is_split_under_the_limit_and_joined_in_place():
    value = json.dumps(['단위:%05d' % i for i in range(9000)], ensure_ascii=False)  # Korean: 3 bytes a character
    statement = "SELECT :units AS a, :units_more AS b FROM DUAL WHERE x=:units"
    out, binds = clob_pieces(statement, [('units', value, 'CLOB'), ('units_more', 'y', 'CLOB')])
    pieces = [b for b in binds if b[0].startswith('units__')]
    assert len(pieces) >= 4 and all(len(b[1].encode()) <= 30000 and b[2] == 'CLOB' for b in pieces)
    assert ''.join(b[1] for b in pieces) == value
    joined = '(' + '||'.join('TO_CLOB(:%s)' % b[0] for b in pieces) + ')'
    assert out == 'SELECT ' + joined + ' AS a, :units_more AS b FROM DUAL WHERE x=' + joined
    assert ('units_more', 'y', 'CLOB') in binds


def test_long_clob_missing_from_statement_is_refused():
    with pytest.raises(DPError, match='QUERY_SQL_BINDS'):
        clob_pieces('SELECT 1 FROM DUAL', [('units', 'z' * 40000, 'CLOB')])


def test_request_sends_the_pieces():
    sent = []
    client = SimpleNamespace(SQL_PATH='/sql', request=lambda method, path, json: sent.append(json) or
                             {'items': [{'resultSet': {'items': [], 'hasMore': False, 'offset': 0}}]})
    sql = oracle_dp_io.SQL.__new__(oracle_dp_io.SQL)
    sql.client, sql.calls, sql.max_calls, sql.deadline = client, 0, 10, float('inf')
    sql.event = lambda *a, **k: None
    sql.request("SELECT 1 FROM JSON_TABLE(:d,'$[*]' COLUMNS(k VARCHAR2(9) PATH '$')) j", [('d', json.dumps(['k' * 20] * 3000), 'CLOB')])
    names = [b['name'] for b in sent[0]['binds']]
    assert names == ['d__0', 'd__1', 'd__2'] and ':d__2)' in sent[0]['statementText'] and ':d,' not in sent[0]['statementText']


def test_witness_counts_without_the_count_table_use_indexed_reference_reads():
    from pathlib import Path
    from semantic_runtime.legal_agent import workflow_relation_cards
    text = Path(workflow_relation_cards.__file__).read_text(encoding='utf-8')
    assert 'references_at(self.s.tools, r[\'source_id\'])' in text and 'FROM reference_end x JOIN reference r' not in text


def test_links_api_on_oracle_uses_indexed_reads():
    from pathlib import Path
    from semantic_runtime import app
    text = Path(app.__file__).read_text(encoding='utf-8')
    oracle = text[text.index("if hasattr(index,'request'):"):text.index('db=index.resident_connect()')]
    assert 'references_at(tools,source_id)' in oracle and 'JOIN' not in oracle


def test_writes_keep_their_binds():
    sent = []
    client = SimpleNamespace(SQL_PATH='/sql', request=lambda method, path, json: sent.append(json) or {'items': [{'result': 0}]})
    sql = oracle_dp_io.SQL.__new__(oracle_dp_io.SQL)
    sql.client, sql.calls, sql.max_calls, sql.deadline = client, 0, 10, float('inf')
    sql.event = lambda *a, **k: None
    sql.request('BEGIN INSERT INTO T VALUES(:body); END;', [('body', 'x' * 40000, 'CLOB')], write=True)
    assert [b['name'] for b in sent[0]['binds']] == ['body']
