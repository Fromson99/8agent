"""Compatibility helpers after rollback of verbose GENOS DB latency logging.

Keep search callers and their result contracts intact. Diagnostic spans, CPU
pressure sampling and SQL timers are disabled, including when the old
GENOS_QUERY_LATENCY environment variable is still set to 1.
"""
from contextlib import contextmanager
from . import observability as obs  # Existing resident-cache mount policy uses this module.

REVISION = 'query-latency-rollback-20261007-r1'


@contextmanager
def span(name, *, pressure=False, **fields):
    yield dict(fields)


def timed(name, *, pressure=False):
    def decorate(function):
        return function
    return decorate


def rows(db, sql, params, operation):
    """Run the same SQL and release its cursor without diagnostic logging."""
    cursor = db.execute(sql, params)
    try:
        return cursor.fetchall()
    finally:
        cursor.close()
