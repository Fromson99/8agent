"""Small lexical scanner for maintained SQL, with no SQL dialect dependency.

This does not parse/translate SQL. Quoted text, comments and bind names remain
distinct so physical identifiers cannot be replaced inside data or parameters.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .oracle_dp_io import DPError


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    start: int
    end: int  # exclusive


def tokens(sql):
    result = []
    i = 0
    while i < len(sql):
        start = i
        char = sql[i]
        if char.isspace():
            i += 1
            continue
        if sql.startswith('--', i):
            end = sql.find('\n', i + 2)
            i = len(sql) if end < 0 else end + 1
            continue
        if sql.startswith('/*', i):
            end = sql.find('*/', i + 2)
            if end < 0:
                raise DPError('QUERY_SQL_TOKEN: unterminated comment')
            i = end + 2
            continue
        if char in 'qQ' and sql[i:i+2].lower() == "q'" and i + 2 < len(sql):
            closing = {'[': ']', '{': '}', '(': ')', '<': '>'}.get(sql[i+2], sql[i+2])
            end = sql.find(closing + "'", i + 3)
            if end < 0:
                raise DPError('QUERY_SQL_TOKEN: unterminated alternative literal')
            i = end + 2
            result.append(Token('string', sql[start:i], start, i))
            continue
        if char in "'\"`[":
            closing = ']' if char == '[' else char
            i += 1
            while i < len(sql):
                if sql[i] == closing:
                    if i + 1 < len(sql) and sql[i+1] == closing:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            else:
                raise DPError('QUERY_SQL_TOKEN: unterminated quoted token')
            raw = sql[start:i]
            result.append(Token('string' if char == "'" else 'identifier',
                                raw if char == "'" else raw[1:-1].replace(closing * 2, closing), start, i))
            continue
        if char == ':' and i + 1 < len(sql) and (sql[i+1].isalnum() or sql[i+1] == '_'):
            i += 2
            while i < len(sql) and (sql[i].isalnum() or sql[i] in '_$#'):
                i += 1
            result.append(Token('bind', sql[start:i], start, i))
            continue
        match = re.match(r'[A-Za-z_][A-Za-z_0-9$#]*|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', sql[i:])
        if match:
            i += len(match[0])
            result.append(Token('word' if char.isalpha() or char == '_' else 'number', match[0], start, i))
            continue
        pair = sql[i:i+2]
        i += 2 if pair in ('<=', '>=', '<>', '!=', '||', '==', '->') else 1
        result.append(Token('symbol', sql[start:i], start, i))
    return result


def mapped_columns(sql, names, declared):
    changes = [(t.start, t.end, names.c(t.text.upper())) for t in tokens(sql)
               if t.kind in ('word', 'identifier') and t.text.upper() in declared]
    for start, end, value in reversed(changes):
        sql = sql[:start] + value + sql[end:]
    return sql
