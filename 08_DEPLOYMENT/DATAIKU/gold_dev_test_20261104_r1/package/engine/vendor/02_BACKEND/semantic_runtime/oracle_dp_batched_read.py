"""Bounded scalar CLOB continuation reads; original row comparison stays upstream."""
from collections import deque

from . import oracle_dp_io as io
from .physical_mapping import names


def complete_rows(sql, kind, rows, *, batch_size):
    if type(batch_size) is not int or not 2 <= batch_size <= 32:
        raise io.DPError('CLOB_BATCH_SIZE: expected integer 2..32')
    n = names(sql, kind, io.OWNER + '.' + io.TABLES[kind])
    pending, values = deque(), []
    for row in rows:
        for col in io.COLUMNS[kind]:
            if col not in io.CLOBS:
                continue
            length = row.pop(col + '__TOTAL')
            first = row[col]
            if length is None:
                if first is not None:
                    raise io.DPError('CLOB_NULL: inconsistent response')
                continue
            if type(length) is not int or not 0 <= length <= io.MAX_VALUE_BYTES:
                raise io.DPError('CLOB_LENGTH: invalid length')
            if first is not None and not isinstance(first, str):
                raise io.DPError('CLOB_PIECE: expected text')
            first = first or ''
            consumed, size = io.units(first), len(first.encode('utf-8'))
            if consumed > length or consumed > io.LOB_UNITS or (length and not consumed):
                raise io.DPError('CLOB_LENGTH: inconsistent first piece')
            item = dict(row=row, col=col, length=length, consumed=consumed,
                        size=size, parts=[first])
            values.append(item)
            if consumed < length:
                pending.append(item)

    while pending:
        current = [pending.popleft() for _ in range(min(batch_size, len(pending)))]
        statements, binds = [], []
        for slot, item in enumerate(current):
            prefix = 'b' + str(slot)
            terms = []
            for index, col in enumerate(io.KEYS[kind]):
                name = prefix + '_k' + str(index)
                terms.append(n.c(col) + '=:' + name)
                binds.append((name, item['row'][col], 'VARCHAR2'))
            binds += [(prefix + '_slot', slot, 'NUMBER'),
                      (prefix + '_pos', item['consumed'] + 1, 'NUMBER')]
            physical = n.c(item['col'])
            statements.append(
                f'SELECT :{prefix}_slot AS CLOB_SLOT, '
                f'DBMS_LOB.SUBSTR({physical},{io.LOB_UNITS},:{prefix}_pos) AS PIECE, '
                f'DBMS_LOB.GETLENGTH({physical}) AS TOTAL FROM {n.table} WHERE '
                + ' AND '.join(terms))
        received = sql.query(' UNION ALL '.join(statements), binds, limit=len(current))
        indexed = {}
        for part in received:
            if set(part) != {'CLOB_SLOT', 'PIECE', 'TOTAL'}:
                raise io.DPError('CLOB_BATCH_RESPONSE: unexpected columns')
            slot = part['CLOB_SLOT']
            if type(slot) is not int or not 0 <= slot < len(current) or slot in indexed:
                raise io.DPError('CLOB_BATCH_RESPONSE: duplicate/unexpected slot')
            indexed[slot] = part
        if len(indexed) != len(current):
            raise io.DPError('CLOB_INCOMPLETE: missing chunk row')
        for slot, item in enumerate(current):
            part = indexed[slot]
            piece = part['PIECE']
            if (type(part['TOTAL']) is not int or part['TOTAL'] != item['length']
                    or not isinstance(piece, str) or not piece):
                raise io.DPError('CLOB_INCOMPLETE: missing/changed chunk')
            size = len(piece.encode('utf-8'))
            consumed = io.units(piece)
            if consumed > io.LOB_UNITS or item['consumed'] + consumed > item['length']:
                raise io.DPError('CLOB_LENGTH: oversized/duplicated piece')
            if item['size'] + size > io.MAX_VALUE_BYTES:
                raise io.DPError('CLOB_SIZE: exceeds configured bound')
            item['parts'].append(piece)
            item['size'] += size
            item['consumed'] += consumed
            if item['consumed'] < item['length']:
                pending.append(item)

    for item in values:
        item['row'][item['col']] = ''.join(item['parts'])
    for row in rows:
        io.validate_row(kind, row)
    return rows
