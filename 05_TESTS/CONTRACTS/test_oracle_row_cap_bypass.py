"""2026-11-11 field 500 (MAIN212): a named large document's block list hit the 10,000-row result budget
(QUERY_SQL_RESULT_BUDGET) and failed the question. Past 10,000 rows the read keeps paging with one warning;
the 64 MiB guard still stops a read."""
import json, re
import pytest
from semantic_runtime import oracle_query_db as qdb
from semantic_runtime.oracle_dp_io import DPError


class FakeSQL:
    def __init__(self, total, size=1):
        self.total, self.size = total, size

    def query(self, statement, binds, limit=None):
        offset = int(re.search(r'OFFSET (\d+) ROWS', statement).group(1))
        count = int(re.search(r'FETCH NEXT (\d+) ROWS', statement).group(1))
        body = json.dumps(['x' * self.size])
        return [{'BODY': body, 'N': len(body)} for _ in range(max(0, min(count, self.total - offset)))]


def connection(total, size=1):
    c = object.__new__(qdb.Connection)
    c.sql = FakeSQL(total, size)
    c._progress = lambda: None
    return c


def test_more_than_ten_thousand_rows_are_read_not_refused():
    rows = list(connection(12345)._pages('SELECT body FROM t', []))
    assert len(rows) == 12345


def test_memory_guard_still_stops_a_huge_read():
    with pytest.raises(DPError, match='QUERY_SQL_RESULT_BUDGET'):
        list(connection(20000, size=8000)._pages('SELECT body FROM t', []))
