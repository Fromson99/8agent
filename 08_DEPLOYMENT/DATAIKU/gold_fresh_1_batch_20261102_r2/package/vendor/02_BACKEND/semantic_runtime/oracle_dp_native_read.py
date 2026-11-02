"""Bounded full-value JDBC reads for immutable source-transfer comparisons.

No hashes substitute for content. The caller still uses compare_batch on every
field. Drivers that truncate CLOB text are disabled for the remainder of the
invocation, then the original piece reader handles the complete batch.
"""
from . import oracle_dp_io as io
from .physical_mapping import names

MAX_RESULT_BYTES = 8 * 1024 * 1024


def _fallback(sql, reason):
    sql.client.source_native_clob_disabled = True
    sql.event('SOURCE_NATIVE_CLOB_FALLBACK', reason=reason)
    print('SOURCE_NATIVE_CLOB_FALLBACK=' + reason, flush=True)
    return None


def read_expected(sql, kind, expected):
    if not expected or len(expected) > 100:
        raise io.DPError('NATIVE_BATCH: expected 1..100 rows')
    columns = io.COLUMNS[kind]
    caps = {c: max((io.units(r[c]) for r in expected if r[c] is not None), default=0)
            for c in columns if c in io.CLOBS}
    # Bound even unexpected longer values in the target at the SQL projection.
    # Four UTF-8 bytes per UTF-16 unit is deliberately conservative.
    if len(expected) * (sum(caps.values()) * 4 + 16384) > MAX_RESULT_BYTES:
        return None
    n = names(sql, kind, io.OWNER + '.' + io.TABLES[kind])
    projection = []
    for col in columns:
        if col in caps:
            physical = n.c(col)
            projection.extend([
                f'CASE WHEN DBMS_LOB.GETLENGTH({physical})<={caps[col]} '
                f'THEN {physical} ELSE NULL END AS {col}',
                f'DBMS_LOB.GETLENGTH({physical}) AS {col}__TOTAL',
            ])
        else:
            projection.append(n.select(col))
    predicates, binds = [], []
    for i, row in enumerate(expected):
        terms = []
        for j, col in enumerate(io.KEYS[kind]):
            name = f'k{i}_{j}'
            binds.append((name, row[col], 'VARCHAR2'))
            terms.append(f'{n.c(col)}=:{name}')
        predicates.append('(' + ' AND '.join(terms) + ')')
    statement = f'SELECT {",".join(projection)} FROM {n.table} WHERE ' + ' OR '.join(predicates)
    try:
        rows = sql.query(statement, binds, limit=len(expected))
    except io.BudgetPause:
        raise
    except io.DPError:
        # Read-only compatibility fallback; its failed request is already in the
        # original SQL journal/cumulative budget. Never used for a write.
        return _fallback(sql, 'JDBC_FULL_VALUE_READ_UNAVAILABLE')
    fields = set(columns) | {c + '__TOTAL' for c in caps}
    for row in rows:
        if set(row) != fields:
            raise io.DPError('NATIVE_COLUMNS: missing/unexpected fields')
        for col, cap in caps.items():
            length = row.pop(col + '__TOTAL')
            value = row[col]
            if length is None:
                if value is not None:
                    raise io.DPError('CLOB_NULL: inconsistent full value')
                continue
            if type(length) is not int or length < 0 or length > cap:
                raise io.DPError('ROW_CONFLICT: target CLOB exceeds expected bound')
            # Some JDBC/CSV paths conflate empty text with None. Oracle length
            # distinguishes an EMPTY_CLOB from SQL NULL without guessing.
            if length == 0 and value in ('', None):
                row[col] = ''
                continue
            if not isinstance(value, str) or io.units(value) != length:
                return _fallback(sql, 'JDBC_FULL_VALUE_LENGTH_OR_TYPE')
            if len(value.encode('utf-8')) > io.MAX_VALUE_BYTES:
                raise io.DPError('CLOB_SIZE: exceeds configured bound')
        io.validate_row(kind, row)
    # This also rejects duplicated/unexpected keys (row order may differ) and same-length
    # corruption. Missing rows remain missing, so transfer can insert them and
    # verification can reject them through its unchanged existing path.
    io.compare_batch(kind, expected, rows, require_all=False)
    if rows and not getattr(sql.client, 'source_native_clob_confirmed', False):
        sql.event('SOURCE_NATIVE_CLOB_CONFIRMED', rows=len(rows))
        sql.client.source_native_clob_confirmed = True
        print('SOURCE_NATIVE_CLOB_CONFIRMED rows=' + str(len(rows)), flush=True)
    return rows
