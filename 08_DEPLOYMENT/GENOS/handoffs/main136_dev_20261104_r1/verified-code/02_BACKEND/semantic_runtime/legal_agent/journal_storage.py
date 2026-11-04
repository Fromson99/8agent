"""Lossless per-database content storage. No corpus mirror or cross-user cache.

Only explicitly stored TEXT values become BLOB references. Plain legacy TEXT
and arbitrary JSON are never mistaken for references. Logical hashes and the
immutable journal rows keep their original meaning. Blobs share transactions
with their references; rollback cannot leave a dangling committed reference.
"""
import hashlib
import json
import os
import re
import sqlite3
import zlib

from .errors import ContractError

MAGIC = b'{"genos_journal_blob_v1":"'
TOKEN = re.compile(rb'"(?:[^"\\]|\\.)*"')
MIN_SIZE = 512
MAX_NESTING = 4


def enabled():
    mode = os.environ.get('GENOS_JOURNAL_STORAGE', '').strip()
    if mode and mode not in ('compact', 'plain'):
        raise ContractError('GENOS_JOURNAL_STORAGE must be compact or plain')
    return mode == 'compact' or (not mode and bool(os.environ.get('GENOS_RUNTIME_DIR')))


class Connection(sqlite3.Connection):
    compact = False


def connect(*args, **kwargs):
    from ..oracle_runtime_paths import virtual
    if args and virtual(args[0]):
        from ..oracle_record_sqlite import connect as oracle_connect
        db = oracle_connect(*args, **kwargs)
        db.row_factory = row
        register(db)
        return db
    db = sqlite3.connect(*args, factory=Connection, **kwargs)
    db.row_factory = row
    register(db)
    return db


def register(db):
    db.create_function('journal_text', 1, lambda value: restore(db, value), deterministic=True)


def initialize(db):
    # Readers always understand both formats; disabling compact affects only
    # new writes. Existing records are never rewritten implicitly.
    requested = enabled()
    # Oracle BODY already provides content addressing and compression. Factoring
    # every string into SQLite blobs here creates extra durable row transactions.
    # Keep the empty compatibility table and old-blob reader, but write plain TEXT.
    db.compact = requested and not getattr(db, 'is_oracle_record', False)
    if requested:
        if not db.execute('SELECT json_valid(?)', (MAGIC + b'x"}',)).fetchone()[0]:
            raise ContractError('SQLite does not support JSON BLOB journal references')
        db.execute('''CREATE TABLE IF NOT EXISTS journal_blob_v1(
            hash TEXT PRIMARY KEY, size INTEGER NOT NULL, codec TEXT NOT NULL,
            data BLOB NOT NULL)''')


def row(cursor, values):
    return sqlite3.Row(cursor, tuple(restore(cursor.connection, v) for v in values))


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _put(db, raw, codec='zlib', packed=None):
    key = _hash(raw)
    # Do not decode compressed column data while reading the blob table.
    execute = db.execute if getattr(db, 'is_oracle_record', False) else lambda *a: sqlite3.Connection.execute(db, *a)
    execute('''INSERT OR IGNORE INTO journal_blob_v1
        VALUES(?,?,?,?)''', (key, len(raw), codec, zlib.compress(raw if packed is None else packed, 6)))
    return key


def store(db, value):
    if not db.compact or value is None:
        return value
    if not isinstance(value, str):
        raise ContractError('journal content must be text')
    raw = value.encode('utf-8')
    if len(raw) < MIN_SIZE:
        return value
    key = _intern(db, raw)
    return MAGIC + key.encode('ascii') + b'"}'


def _intern(db, raw, depth=0):
    key = _hash(raw)
    if db.execute('SELECT 1 FROM journal_blob_v1 WHERE hash=?', (key,)).fetchone() is None:
        # Share long JSON string values (originals, prompts, quotations) across
        # views, attempts and decisions. Other bytes remain exactly unchanged.
        parts = []; end = 0
        for token in TOKEN.finditer(raw) if depth < MAX_NESTING else ():
            if token.end() - token.start() < MIN_SIZE:
                continue
            if token.start() > end:
                parts.append(['literal', raw[end:token.start()].decode('utf-8')])
            text = json.loads(token.group())
            canonical = json.dumps(text, ensure_ascii=False, separators=(',', ':')).encode()
            if canonical == token.group():
                # The same original stored as evidence_span.text and embedded
                # in JSON must share the actual text, not two escaped copies.
                # Model messages often contain another serialized JSON view.
                # Factor that view too, so a changed turn number does not cause
                # another stored copy of every unchanged original inside it.
                parts.append(['json-string', _intern(db, text.encode('utf-8'), depth + 1)])
            else:
                parts.append(['hash', _put(db, token.group())])
            end = token.end()
        if parts:
            if end < len(raw):
                parts.append(['literal', raw[end:].decode('utf-8')])
            packed = json.dumps(parts, ensure_ascii=False, separators=(',', ':')).encode()
            _put(db, raw, 'parts-v1', packed)
        else:
            _put(db, raw)
    return key


def _get(db, key, ancestors=()):
    if key in ancestors or len(ancestors) > MAX_NESTING + 1:
        raise ContractError('journal content reference cycle')
    cursor = sqlite3.Connection.execute(db,
        'SELECT size,codec,data FROM journal_blob_v1 WHERE hash=?', (key,))
    cursor.row_factory = None
    found = cursor.fetchone()
    if found is None:
        raise ContractError('journal content missing: ' + key)
    size, codec, compressed = found
    try:
        packed = zlib.decompress(compressed)
        if codec == 'zlib':
            raw = packed
        elif codec == 'parts-v1':
            parts = json.loads(packed)
            restored = []
            for kind, value in parts:
                if kind == 'literal':
                    restored.append(value.encode('utf-8'))
                elif kind == 'hash':
                    restored.append(_get(db, value, (*ancestors, key)))
                elif kind == 'json-string':
                    text = _get(db, value, (*ancestors, key)).decode('utf-8')
                    restored.append(json.dumps(text, ensure_ascii=False, separators=(',', ':')).encode())
                else:
                    raise ValueError('invalid part')
            raw = b''.join(restored)
        else:
            raise ValueError('unknown codec')
    except (ValueError, TypeError, zlib.error, UnicodeError) as exc:
        raise ContractError('journal content corrupt: ' + key) from exc
    if len(raw) != size or _hash(raw) != key:
        raise ContractError('journal content hash mismatch: ' + key)
    return raw


def restore(db, value):
    if not isinstance(value, bytes) or not value.startswith(MAGIC):
        return value
    try:
        ref = json.loads(value)
        key = ref['genos_journal_blob_v1']
        if set(ref) != {'genos_journal_blob_v1'} or not re.fullmatch('[0-9a-f]{64}', key):
            raise ValueError('invalid reference')
        return _get(db, key).decode('utf-8')
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ContractError('invalid journal content reference') from exc
