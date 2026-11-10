"""SQL time breakdown on the serving SQL owner (2026-11-10, field cannot read V$SQLSTATS).

Every SQL records bytes sent, rows received and CPU while in flight; every PROBE_EVERY calls one
`SELECT 1 FROM DUAL` measures the bare ORDS round trip. The probe is measurement only.
"""
import time

import pytest

from semantic_runtime import oracle_query
from semantic_runtime.oracle_dp_io import DPError
from semantic_runtime.oracle_query import QuerySQL, size_bucket


class Client:
    SQL_PATH = '/_/sql'

    def __init__(self, fail_probe=False):
        self.sent, self.fail_probe = [], fail_probe

    def request(self, method, path, json):
        text = json['statementText']
        self.sent.append(text)
        if text == oracle_query.PROBE_SQL and self.fail_probe:
            raise OSError('probe transport down')
        if text.startswith('SELECT'):
            rows = [{'ONE': 1}] if text == oracle_query.PROBE_SQL else [{'A': 'x'}, {'A': 'y'}]
            return {'items': [{'resultSet': {'items': rows, 'hasMore': False, 'offset': 0}}]}
        return {'items': [{'result': 1}]}


def sql(client, monkeypatch, every=3):
    monkeypatch.setattr(oracle_query, 'PROBE_EVERY', every)
    return QuerySQL(client, binding='b', deadline=time.monotonic() + 60, max_calls=1000)


def test_reads_record_bytes_rows_cpu_and_probe(monkeypatch):
    client = Client(); s = sql(client, monkeypatch)
    for _ in range(7):
        assert s.query('SELECT A FROM T WHERE K=:k', [('k', 'v' * 10, 'VARCHAR2')]) == [{'A': 'x'}, {'A': 'y'}]
    summary = s.stats.summary()
    probes = [t for t in client.sent if t == oracle_query.PROBE_SQL]
    # The probe is not counted as an application SQL: 7 reads, plus probes at calls 3 and 7.
    assert summary['sql_count'] == 7 and len(probes) == 2 and len(client.sent) == 9
    assert summary['sql_probe']['count'] == 2 and summary['sql_probe']['failed'] == 0 and summary['sql_probe']['every'] == 3
    assert summary['sql_rows_in'] == 14 and summary['sql_bytes_out'] > 7 * 40
    assert summary['sql_thread_cpu_ms'] >= 0 and summary['sql_process_cpu_ms'] >= 0
    assert summary['sql_size_buckets'] == [{'write': False, 'size': '<4KB', 'count': 7,
                                            'ms': summary['sql_size_buckets'][0]['ms'], 'bytes': summary['sql_bytes_out']}]
    site = summary['sql_sites'][0]
    assert site['count'] == 7 and site['rows'] == 14 and site['bytes'] == summary['sql_bytes_out'] and 'cpu_ms' in site


def test_writes_bucket_by_size(monkeypatch):
    s = sql(Client(), monkeypatch, every=0)
    from semantic_runtime.oracle_dp_io import SQL
    SQL.request(s, 'BEGIN NULL; END;', [('p', 'x' * 100, 'CLOB')], write=True, limit=1)
    SQL.request(s, 'BEGIN NULL; END;', [('p', 'x' * 70_000, 'CLOB')], write=True, limit=1)
    buckets = {(b['write'], b['size']): b for b in s.stats.summary()['sql_size_buckets']}
    assert buckets[(True, '<4KB')]['count'] == 1 and buckets[(True, '64-512KB')]['count'] == 1
    assert buckets[(True, '64-512KB')]['bytes'] > 70_000
    assert s.stats.summary()['sql_probe']['count'] == 0  # PROBE_EVERY=0 turns the probe off


def test_failed_probe_never_fails_the_request(monkeypatch):
    client = Client(fail_probe=True); s = sql(client, monkeypatch, every=1)
    for _ in range(3):
        assert s.query('SELECT A FROM T', []) == [{'A': 'x'}, {'A': 'y'}]
    summary = s.stats.summary()
    assert summary['sql_probe']['failed'] >= 1 and summary['sql_probe']['count'] == 0
    assert summary['sql_failed_count'] == 0 and summary['sql_count'] == 3


def test_probe_respects_budget(monkeypatch):
    client = Client(); monkeypatch.setattr(oracle_query, 'PROBE_EVERY', 1)
    s = QuerySQL(client, binding='b', deadline=time.monotonic() + 60, max_calls=3)
    s.query('SELECT A FROM T', [])
    s.query('SELECT A FROM T', [])
    # Never spends the request's last calls on measurement.
    assert client.sent.count(oracle_query.PROBE_SQL) == 0
    with pytest.raises(DPError):
        s.query('SELECT A FROM T', []); s.query('SELECT A FROM T', [])


def test_size_bucket_edges():
    assert [size_bucket(n) for n in (0, 4095, 4096, 65535, 65536, 524287, 524288)] == [
        '<4KB', '<4KB', '4-64KB', '4-64KB', '64-512KB', '64-512KB', '>=512KB']
