"""Process-lifetime reuse of published Oracle rows, and the quieter Oracle SQL log.

Fake ORDS client only (no database). What may be reused: SELECTs whose every
table is a published, content-addressed table of the release this request pinned.
What is always sent: active pointers, request state, Agent records, ontology and
vector heads, dictionary views, time-dependent SQL, unknown tables.
"""
import json
import logging
import re
import time

import pytest

from semantic_runtime import observability as obs
from semantic_runtime import oracle_query
from semantic_runtime.oracle_development_mapping import DevelopmentMapping
from semantic_runtime.oracle_dp_io import BudgetPause, DPError, digest
from semantic_runtime.oracle_query_catalog import SCHEMA, active, read_release
from semantic_runtime.oracle_query_state import StateSQL
from semantic_runtime.oracle_shared_cache import SharedRows, settings

R1, R2 = 'a' * 64, 'b' * 64


class Client:
    SQL_PATH = '/fake'

    def __init__(self, mapping=None, rows=None, fail=False):
        self.schema_map, self.sent, self.fail = mapping, [], fail
        self.rows = rows if rows is not None else [{'a': 1, 'b': 'x'}]

    def request(self, method, path, json):
        self.sent.append(json['statementText'])
        if self.fail:
            raise ConnectionError('ords down')
        rows = self.rows(json) if callable(self.rows) else self.rows
        return {'items': [{'resultSet': {'offset': 0, 'hasMore': False, 'items': [dict(r) for r in rows]}}]}


def request_sql(client, cache, *, seconds=60):
    sql = StateSQL(client, binding='b', deadline=time.monotonic() + seconds, max_calls=1000)
    sql.shared_cache = cache
    return sql


@pytest.fixture
def dev():
    mapping = DevelopmentMapping.load()
    client = Client(mapping)
    return mapping, client, SharedRows(client, 'env', environ={})


def published(mapping, key='SRCH_ROW'):
    return 'SELECT r.A FROM ' + mapping.physical_table(key) + ' r WHERE r.K=:k'


def test_published_rows_are_reused_across_requests_and_copied(dev):
    mapping, client, cache = dev
    for _ in range(3):  # three requests, one process
        sql = request_sql(client, cache)
        sql.pin_shared_cache(R1)
        rows = sql.query(published(mapping), [('k', '1', 'VARCHAR2')])
        assert rows == [{'A': 1, 'B': 'x'}]
        rows[0]['A'] = 99  # a caller mutating its rows never changes the next request's rows
    assert len(client.sent) == 1
    assert cache.status()['hits'] == 2 and cache.status()['misses'] == 1


@pytest.mark.parametrize('key', ['DOC_VER', 'DOC_UNIT', 'DOC_BLK', 'SRC_POST', 'SRCH_POST', 'SRCH_ROW'])
def test_every_published_table_is_reusable(dev, key):
    mapping, client, cache = dev
    assert cache.cacheable(published(mapping, key))


@pytest.mark.parametrize('kind', ['pointer', 'state', 'agent', 'ontology', 'vector_head', 'vector_post', 'vector_item',
                                  'dictionary', 'time', 'join', 'unknown_table'])
def test_mutable_volatile_and_unknown_reads_are_always_sent(dev, kind):
    mapping, client, cache = dev
    t = mapping.physical_table
    statement = {
        'pointer': 'SELECT 1 FROM ' + t('SRCH_CHNL'),
        'state': 'SELECT 1 FROM ' + t('EXEC_ST'),
        'agent': 'SELECT 1 FROM ' + t('AGT_REC') + ' r JOIN ' + t('AGT_BODY') + ' b ON 1=1',
        'ontology': 'SELECT 1 FROM ' + t('ONTL_HEAD') + ' h JOIN ' + t('ONTL_POST') + ' p ON 1=1',
        'vector_head': 'SELECT 1 FROM ' + t('VCTR_HEAD'),
        'vector_post': 'SELECT 1 FROM ' + t('VCTR_POST'),
        'vector_item': 'SELECT 1 FROM ' + t('VCTR_ITEM'),
        'dictionary': "SELECT COLUMN_NAME FROM ALL_TAB_COLUMNS WHERE OWNER='SIDDS'",
        'time': published(mapping) + ' AND SYSTIMESTAMP > TIMESTAMP \'2000-01-01 00:00:00\'',
        'join': published(mapping, 'DOC_BLK') + ' AND EXISTS (SELECT 1 FROM ' + t('SRCH_CHNL') + ')',
        'unknown_table': 'SELECT 1 FROM SIDDS.LGL_G19_SOMETHING_NEW',
    }[kind]
    assert not cache.cacheable(statement)
    for _ in range(2):
        sql = request_sql(client, cache)
        sql.pin_shared_cache(R1)
        sql.query(statement)
    assert len(client.sent) == 2


def test_active_pointer_is_read_every_request(dev):
    mapping, client, cache = dev
    client.rows = [{'RELEASE_ID': R1, 'REVISION': 3}]
    for _ in range(2):
        sql = request_sql(client, cache)
        sql.pin_shared_cache(R1)
        assert active(sql, 'main') == {'release_id': R1, 'revision': 3}
    assert len(client.sent) == 2


def test_nothing_is_reused_before_a_release_is_pinned(dev):
    mapping, client, cache = dev
    for _ in range(2):
        request_sql(client, cache).query(published(mapping))
    assert len(client.sent) == 2


def test_scope_is_the_pinned_release(dev):
    mapping, client, cache = dev
    for release in (R1, R2, R1):
        sql = request_sql(client, cache)
        sql.pin_shared_cache(release)
        sql.query(published(mapping))
    assert len(client.sent) == 2  # R1, R2 sent; second R1 reused
    other = SharedRows(client, 'another-connection', environ={})
    assert other.scope(R1) != cache.scope(R1)


def test_a_second_release_in_one_request_stops_reuse(dev):
    mapping, client, cache = dev
    sql = request_sql(client, cache)
    sql.pin_shared_cache(R1)
    sql.query(published(mapping))
    sql.pin_shared_cache(R2)
    assert sql.shared_scope is False
    sql.query(published(mapping))
    sql.query(published(mapping))
    assert len(client.sent) == 3


def test_read_release_pins_the_scope_and_reuses_the_manifest():
    mapping = DevelopmentMapping.load()
    value = {'schema_version': SCHEMA, 'status': 'COMPLETE', 'source_release_id': R1, 'dataset_version': R2}
    text = json.dumps(value)
    rid = digest(value)
    client = Client(mapping, rows=[{'VALUE': text, 'N': len(text)}])
    cache = SharedRows(client, 'env', environ={})
    for _ in range(2):
        sql = request_sql(client, cache)
        assert read_release(sql, rid) == value
        assert sql.shared_scope == cache.scope(rid)
    assert len(client.sent) == 1


def test_failed_reads_are_not_reused(dev):
    mapping, _, _ = dev
    client = Client(mapping, fail=True)
    cache = SharedRows(client, 'env', environ={})
    for _ in range(2):
        sql = request_sql(client, cache)
        sql.pin_shared_cache(R1)
        with pytest.raises(DPError, match='READ_FAILED'):
            sql.query(published(mapping))
    assert len(client.sent) == 2 and cache.status()['entries'] == 0


def test_expired_request_cannot_read_reused_rows(dev):
    mapping, client, cache = dev
    sql = request_sql(client, cache)
    sql.pin_shared_cache(R1)
    sql.query(published(mapping))
    late = request_sql(client, cache)
    late.pin_shared_cache(R1)
    late.deadline = time.monotonic() - 1
    with pytest.raises(BudgetPause, match='QUERY_DEADLINE'):
        late.query(published(mapping))


def test_switch_and_bounds():
    assert settings({})['mode'] == 'on' and settings({})['mib'] == 512
    client = Client(DevelopmentMapping.load())
    off = SharedRows(client, 'env', environ={'GENOS_ORACLE_SHARED_CACHE': 'off'})
    assert not off.enabled and not off.cacheable(published(client.schema_map))
    for bad in ({'GENOS_ORACLE_SHARED_CACHE': 'maybe'}, {'GENOS_ORACLE_SHARED_CACHE_MIB': '8'},
                {'GENOS_ORACLE_SHARED_CACHE_MIB': 'x'}, {'GENOS_ORACLE_SHARED_CACHE_ENTRIES': '0'}):
        with pytest.raises(DPError, match='DP_CONFIG'):
            settings(bad)


def test_byte_budget_evicts_oldest(dev):
    mapping, _, _ = dev
    client = Client(mapping, rows=lambda body: [{'v': 'x' * 400_000, 'k': body['binds'][0]['value']}])
    cache = SharedRows(client, 'env', environ={'GENOS_ORACLE_SHARED_CACHE_MIB': '16'})
    for k in range(60):
        sql = request_sql(client, cache)
        sql.pin_shared_cache(R1)
        sql.query(published(mapping), [('k', str(k), 'VARCHAR2')])
    status = cache.status()
    assert status['bytes'] <= 16 * 1024 * 1024 and status['evictions'] > 0


def test_gold_and_legacy_mappings():
    from semantic_runtime.oracle_gold_mapping import GoldMapping
    gold = GoldMapping.load(owner='GOLDX')
    cache = SharedRows(Client(gold), 'env', environ={})
    assert cache.cacheable('SELECT 1 FROM GOLDX.IDD_B003_LGL_SRCH_ROW r')
    assert not cache.cacheable('SELECT 1 FROM GOLDX.IDD_B003_LGL_SRCH_CHNL r')
    assert not cache.cacheable('SELECT 1 FROM ' + gold.physical_table('EXEC_ST'))
    legacy = SharedRows(Client(None), 'env', environ={})
    assert legacy.cacheable('SELECT 1 FROM SIDDA.LEGAL_SRC_BLOCK_PAYLOAD_A b')
    assert legacy.cacheable('SELECT 1 FROM SIDDA.LEGAL_RAG_QUERY_ROW_A r')
    assert not legacy.cacheable('SELECT 1 FROM SIDDA.LEGAL_RAG_QUERY_ACTIVE_A a')
    assert not legacy.cacheable('SELECT 1 FROM SIDDA.LEGAL_RAG_QUERY_STATE_A s')


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.rows = []

    def emit(self, record):
        self.rows.append((record.getMessage(), record.levelname, getattr(record, 'fields', {})))


def test_per_sql_lines_are_not_info_and_summary_counts(dev, monkeypatch):
    mapping, client, cache = dev
    capture = Capture()
    obs.configure()
    root = logging.getLogger(obs.ROOT)
    root.addHandler(capture)
    try:
        sql = request_sql(client, cache)
        sql.pin_shared_cache(R1)
        for _ in range(3):
            sql.query(published(mapping))
        sql.query('SELECT 1 FROM ' + mapping.physical_table('SRCH_CHNL'))
        assert [r for r in capture.rows if r[0].startswith('oracle.sql')] == []
        monkeypatch.setattr(oracle_query, 'SLOW_SQL_MS', 0)
        sql.query('SELECT 2 FROM ' + mapping.physical_table('SRCH_CHNL'))
        assert [(m, level) for m, level, _ in capture.rows] == [('oracle.sql.slow', 'INFO')]
        failing = request_sql(Client(mapping, fail=True), cache)
        with pytest.raises(DPError):
            failing.query('SELECT 3 FROM ' + mapping.physical_table('SRCH_CHNL'))
        assert capture.rows[-1][0] == 'oracle.sql' and capture.rows[-1][1] == 'WARNING'
        assert capture.rows[-1][2]['status'] == 'READ_FAILED'
    finally:
        root.removeHandler(capture)
    summary = sql.stats.summary()
    assert summary['sql_count'] == 3 and summary['sql_cache_hits'] == 2 and summary['sql_cache_misses'] == 1
    assert failing.stats.summary()['sql_failed_count'] == 1
    assert re.fullmatch(r'[A-Za-z0-9_.:-]{1,96}', summary['sql_top'])  # shown by the request live log


def test_summary_fields_reach_the_request_live_log():
    from semantic_runtime.request_report import _LIVE_FIELD_NAMES
    summary = oracle_query.SQLStats().summary()
    assert set(summary) <= _LIVE_FIELD_NAMES
    assert {'cache_entries', 'cache_bytes', 'cache_evictions', 'sql_family', 'duration_ms'} <= _LIVE_FIELD_NAMES
