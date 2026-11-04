"""Prepared Oracle reads: values, ACL predicates, syntax and no runtime parser.

Optional live cases use SELECT-only JSON fixtures and the existing loopback
read-only account. They never create tables or modify published data.
"""
import builtins
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace as NS

import pytest

from semantic_runtime.oracle_dp_io import DPError, units
from semantic_runtime.oracle_query_catalog import ROW, LOOKUP_ENCODING, lookup_key
from semantic_runtime.oracle_query_db import Connection
from semantic_runtime.oracle_query_shape import shape
from semantic_runtime.oracle_query_plans import PLANS
from semantic_runtime.oracle_sql_tokens import tokens, mapped_columns

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def catalogue(monkeypatch):
    spec = importlib.util.spec_from_file_location('prepare_native_test', ROOT/'06_TOOLS/maintenance/prepare_oracle_queries.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def register(sql):
        key, entry = module.prepare(sql)
        monkeypatch.setitem(PLANS, key, entry)
    return register


def request(columns, sql=None):
    table = {'asset': 'fixture', 'table': 'sample', 'lookup_encoding': LOOKUP_ENCODING, 'columns': columns}
    return NS(sql=sql, release_id='release', sources=NS(allowed={'allowed'}),
              records=NS(manifest={'tables': {'sample.rows': table}}))


def test_shape_preserves_bind_order_list_cardinality_literals_and_quoted_text():
    a = shape("SELECT id FROM sample WHERE id IN (?,?) AND label=? AND body='literal ? :fake'", ['a', 'b', 'value'])
    b = shape("select id from sample where id in (?) and label=? and body='different'", ['c', 'value'])
    assert a[0] == b[0]
    assert a[2]['s0'] == [('a8_p0', 'a'), ('a8_p1', 'b')]
    assert a[2]['s1'] == [('a8_p2', 'value')]
    assert a[2]['s2'][0][1] == 'literal ? :fake'
    assert shape('SELECT id FROM sample WHERE id=?', ['x'])[0] != shape('SELECT id FROM sample WHERE id IN (?)', ['x'])[0]
    for sql, args in [('SELECT ?', []), ('SELECT :x', [1]), ('SELECT ?; DELETE FROM x', [1]), ('SELECT ?', [object()])]:
        with pytest.raises(DPError):
            shape(sql, args)


def test_lexical_mapping_never_changes_bind_comment_or_literal():
    sql = "DOCUMENT_ID=:DOCUMENT_ID AND TEXT='DOCUMENT_ID :TEXT' /* DOCUMENT_ID */ -- TEXT\n ORDER BY \"BLOCK_ID\""
    names = NS(c=lambda name: 'P_' + name)
    out = mapped_columns(sql, names, ['DOCUMENT_ID', 'TEXT', 'BLOCK_ID'])
    assert out == "P_DOCUMENT_ID=:DOCUMENT_ID AND P_TEXT='DOCUMENT_ID :TEXT' /* DOCUMENT_ID */ -- TEXT\n ORDER BY P_BLOCK_ID"
    assert [t.kind for t in tokens("q'[FROM SIDDA.X]' :FROM")] == ['string', 'bind']
    with pytest.raises(DPError, match='unterminated'):
        tokens("SELECT 'broken")


def test_source_reader_physical_mapping_without_sqlglot(monkeypatch):
    from semantic_runtime import oracle_query
    original = builtins.__import__
    def blocked(name, *args, **kwargs):
        if name == 'sqlglot' or name.startswith('sqlglot.'):
            raise ModuleNotFoundError("No module named 'sqlglot'", name='sqlglot')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', blocked)
    captured = []
    def read(sql, kind, predicate, binds, **kwargs):
        captured.append((predicate, binds, kwargs['order']))
        return [{'DATASET_VERSION': 'version', 'DOCUMENT_ID': 'allowed'}]
    monkeypatch.setattr(oracle_query, 'read_rows', read)
    sql = NS(client=NS(schema_map=NS(names=lambda kind: NS(c=lambda col: 'P_' + col))))
    reader = oracle_query.SourceReader(sql, NS(dataset_version='version'), {'allowed'})
    assert len(reader._rows('block_payload', 'allowed', ' AND BLOCK_ID=:BLOCK_ID',
                           [('BLOCK_ID', '1', 'VARCHAR2')], order='BLOCK_ID')) == 1
    assert captured[0][0] == 'P_DATASET_VERSION=:version AND P_DOCUMENT_ID=:document AND P_BLOCK_ID=:BLOCK_ID'
    assert captured[0][1][-1] == ('BLOCK_ID', '1', 'VARCHAR2')
    assert captured[0][2] == 'P_BLOCK_ID'


def test_unknown_query_and_undeclared_table_fail_before_network(catalogue):
    conn = Connection(request({'id': {'type': 'text', 'max_bytes': 20}}), 'fixture')
    conn._pages = lambda *_: pytest.fail('unknown query reached Oracle')
    with pytest.raises(DPError, match='NOT_PREPARED'):
        conn.execute('SELECT unsupported_function(id) FROM sample')
    sql = 'SELECT id FROM undeclared WHERE id=?'
    catalogue(sql)
    with pytest.raises(DPError, match='QUERY_SQL_TABLE'):
        conn.execute(sql, ['x'])


def test_changed_query_source_requires_regeneration(monkeypatch):
    from semantic_runtime.oracle_query_native import validate_sources
    from semantic_runtime.oracle_query_plans import SOURCES
    validate_sources.cache_clear()
    try:
        monkeypatch.setitem(SOURCES, '02_BACKEND/semantic_runtime/storage.py', '0' * 64)
        with pytest.raises(DPError, match='QUERY_SQL_STALE'):
            validate_sources()
    finally:
        validate_sources.cache_clear()


def test_without_sqlglot_keeps_exact_long_value_scope_and_index(catalogue, monkeypatch):
    sql = 'SELECT id FROM sample WHERE id=?'
    catalogue(sql)
    value = "한글'😀" * 1000
    conn = Connection(request({'id': {'type': 'text', 'max_bytes': len(value.encode())}}), 'fixture')
    captured = []
    conn._pages = lambda statement, binds: (captured.append((statement, binds)) or iter([[value]]))
    original = builtins.__import__
    def blocked(name, *a, **kw):
        if name == 'sqlglot' or name.startswith('sqlglot.'):
            raise ModuleNotFoundError("No module named 'sqlglot'", name='sqlglot')
        return original(name, *a, **kw)
    monkeypatch.setattr(builtins, '__import__', blocked)
    assert conn.execute(sql, [value]).fetchone()[0] == value
    text, binds = captured[0]
    assert 'DBMS_LOB.COMPARE' in text and 'r.LOOKUP_ID' in text
    assert ('a8_p0', value, 'CLOB') in binds
    assert [v for n, v, _ in binds if n.startswith('a8_index_key')] == [lookup_key(value)]
    assert [json.loads(v) for n, v, _ in binds if n.startswith('a8_scope')] == [['allowed']]
    assert 'r.RELEASE_ID=:a8_release0' in text


VALUES = [
    {'id': 'a', 'label': '', 'body': '긴 원문 😀 ' * 1000, 'json': '{"n":1,"label":"alpha","array":[1,2],"flag":true}'},
    {'id': 'b', 'label': None, 'body': None, 'json': '{"n":2,"label":"beta","array":[],"flag":false}'},
    {'id': 'c', 'label': '값', 'body': 'short', 'json': '{"n":3,"label":"alpha","array":[3],"flag":null}'},
    # The common prefix exceeds one chunk; the astral characters straddle
    # UCS2 boundaries. DISTINCT/order must preserve the differing final byte.
    {'id': 'd', 'label': '경계', 'body': 'a' + '😀' * 2001 + '가', 'json': '{}'},
    {'id': 'e', 'label': '경계', 'body': 'a' + '😀' * 2001 + '나', 'json': '{}'},
]

CASES = [
    ('SELECT id,label,body FROM sample ORDER BY id', ()),
    ('SELECT * FROM sample WHERE id=?', ('a',)),
    ('SELECT id FROM sample WHERE label IS NULL ORDER BY id', ()),
    ('SELECT id FROM sample WHERE label IS NOT NULL ORDER BY id', ()),
    ("SELECT id FROM sample WHERE label='' ORDER BY id", ()),
    ("SELECT id FROM sample WHERE label<>'' ORDER BY id", ()),
    ('SELECT id FROM sample WHERE label=? ORDER BY id', ('',)),
    ('SELECT id FROM sample WHERE body=?', (VALUES[0]['body'],)),
    ('SELECT id FROM sample WHERE id IN (?,?) ORDER BY id', ('a', 'c')),
    ('SELECT id FROM sample WHERE id IN (' + ','.join('?' for _ in range(1001)) + ') ORDER BY id', tuple(['a'] * 1001)),
    ('SELECT id FROM sample WHERE id IN (SELECT value FROM json_each(?)) ORDER BY id', ('["a","c"]',)),
    ("SELECT id,json_extract(json,'$.n') AS n,json_extract(json,'$.array') AS arr,json_extract(json,'$.flag') AS flag FROM sample ORDER BY id", ()),
    ('SELECT id FROM sample ORDER BY id LIMIT ? OFFSET ?', (1, 1)),
    ('SELECT label,count(*) AS n FROM sample GROUP BY label ORDER BY label', ()),
    ('SELECT id FROM sample WHERE id=? UNION SELECT id FROM sample WHERE id=? ORDER BY id LIMIT ?', ('a', 'c', 2)),
    ('SELECT id,row_number() OVER(PARTITION BY label ORDER BY id) AS n FROM sample ORDER BY id', ()),
    ("SELECT id,CASE WHEN label IS NULL THEN 'missing' ELSE 'present' END AS state FROM sample ORDER BY id", ()),
    ('SELECT id,(instr(body,?)>0)+(instr(body,?)>0) AS score FROM sample ORDER BY score DESC,id', ('원문', 'short')),
    ('SELECT id FROM sample s WHERE EXISTS(SELECT 1 FROM sample t WHERE t.id=s.id AND t.label=?) ORDER BY id', ('값',)),
    ('WITH chosen AS (SELECT id,label FROM sample WHERE id IN (?,?)) SELECT id,label FROM chosen ORDER BY id', ('a', 'c')),
    ('SELECT id,label FROM (SELECT id,label FROM sample) WHERE label IS NULL ORDER BY id', ()),
    ('SELECT id FROM sample WHERE label IN (?,?) ORDER BY id', ('', '값')),
    ('SELECT id FROM sample WHERE label NOT IN (?) ORDER BY id', ('',)),
    ('SELECT id FROM sample WHERE label NOT IN (?,?) ORDER BY id', ('', None)),
    ('SELECT id FROM sample ORDER BY label,id', ()),
    ('SELECT id FROM sample ORDER BY label DESC,id', ()),
    ('SELECT count(*) AS n FROM sample GROUP BY label ORDER BY label', ()),
    ("SELECT json_extract(json,'$.label'),count(*) FROM sample GROUP BY 1 ORDER BY 1", ()),
    ('SELECT s.id,t.label FROM sample s LEFT JOIN sample t USING(id) WHERE t.id=?', ('c',)),
    ('SELECT DISTINCT body FROM sample ORDER BY body', ()),
    ('SELECT count(*) FROM (SELECT DISTINCT body FROM sample)', ()),
    ('SELECT body FROM sample WHERE id=? UNION SELECT body FROM sample WHERE id=? ORDER BY body', ('a', 'c')),
    ('SELECT id,row_number() OVER(ORDER BY body) AS n FROM sample ORDER BY id', ()),
]


@pytest.fixture(scope='module')
def live_connection():
    if os.environ.get('A8_NATIVE_SQL_ORACLE') != '1':
        pytest.skip('explicit loopback read-only Oracle contract run')
    import oracledb
    path = Path.home()/'.local/state/8-agent/gold-r12-1208/readonly-connection.json'
    assert not path.stat().st_mode & 0o077
    config = json.loads(path.read_text())
    assert config['dsn'].startswith('127.0.0.1:')
    with oracledb.connect(**config) as connection:
        connection.call_timeout = 30000
        yield connection


@pytest.mark.parametrize('statement,parameters', CASES)
def test_select_only_real_oracle_matches_sqlite(live_connection, catalogue, statement, parameters):
    catalogue(statement)
    from lawrag.pipeline.oracle_query_publish import _column_shapes
    spec = {'columns': {key: {'type': 'null', 'max_bytes': 0, 'has_null': False, 'has_empty': False} for key in VALUES[0]}}
    for row in VALUES:
        _column_shapes(spec, row)
    class SQL:
        def query(self, text, binds, *, limit):
            assert text.startswith('SELECT ')
            import oracledb
            types = {'CLOB': oracledb.DB_TYPE_CLOB, 'VARCHAR2': oracledb.DB_TYPE_VARCHAR, 'NUMBER': oracledb.DB_TYPE_NUMBER}
            with live_connection.cursor() as cursor:
                cursor.setinputsizes(**{n: types[t] for n, _, t in binds})
                cursor.execute(text, {n: v for n, v, _ in binds})
                names = [c[0] for c in cursor.description]
                return [dict(zip(names, [v.read() if isinstance(v, oracledb.LOB) else v for v in row])) for row in cursor.fetchmany(limit)]
    conn = Connection(request(spec['columns'], SQL()), 'fixture')
    view = conn._view
    def unique_view(name, number):
        text, binds = view(name, number)
        # A SELECT-only CLOB rowset models the published table directly.
        # Nesting JSON_TABLE here introduces fixture-only JSON string limits
        # and Oracle's unsupported JSON_TABLE optimizer chaining.
        rows = []
        for i, row in enumerate(VALUES):
            prefix = 'a8_fixture_' + str(number) + '_' + str(i)
            rows.append("SELECT 'release' RELEASE_ID,'sample.rows' KIND,'allowed' DOCUMENT_ID,:" + prefix +
                        '_id ROW_ID,:' + prefix + '_key LOOKUP_ID,:' + prefix + '_value VALUE_JSON FROM DUAL')
            binds += [(prefix + '_id', row['id'], 'VARCHAR2'),
                      (prefix + '_key', lookup_key(row['id']), 'VARCHAR2'),
                      (prefix + '_value', json.dumps(row, ensure_ascii=False), 'CLOB')]
        return text.replace(ROW, '(' + ' UNION ALL '.join(rows) + ')'), binds
    conn._view = unique_view
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE sample(id TEXT,label TEXT,body TEXT,json TEXT)')
        db.executemany('INSERT INTO sample VALUES(?,?,?,?)', [tuple(r.values()) for r in VALUES])
        expected = db.execute(statement, parameters).fetchall()
    actual = [tuple(row) for row in conn.execute(statement, parameters)]
    assert actual == expected
