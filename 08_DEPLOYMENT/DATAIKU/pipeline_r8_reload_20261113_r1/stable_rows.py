"""Gold 검색 행 번호(row_id)를 SQLite 안의 순서가 아니라 행 내용으로 정한다 (R8, 2026-11-13).

예전: 일반 표는 [몇 번째 행, 내용], 본문 검색 길이·위치 행은 SQLite 내부 번호(rowid).
     문서 하나가 빠지거나 들어오면 그 뒤 행 번호가 모두 바뀌어 같은 행을 알아볼 수 없었다.
지금: 내용이 같으면 세대가 달라도 같은 번호. 그래서 증분 때 안 바뀐 문서의 행을 Oracle 안에서 복사할 수 있다.

- 중복 없는 키(기본 키 또는 UNIQUE 색인)가 있는 표: ['v2', 내용]
- 키가 없는 표·뷰: 내용 순으로 읽고 같은 내용이 이어지면 순번을 붙임 ['v2', 내용, 순번]
- 본문 검색(unit_fts): 길이 행 ['v2', 단위 키], 위치 행 ['v2', 단위 키, 칸, 낱말]
  (단위 키가 없는 다른 FTS 표는 예전 그대로 rowid — 용어집 낱말 색인, 값 자체에 rowid가 들어 있음)
번호가 겹치면 적재 끝의 행 수 대조(FLOW_FINAL_ROW_COUNT)에서 멈춘다.
"""
ROW_KEY_VERSION = 'v2'


def _name(value):
    return '"' + value.replace('"', '""') + '"'


def has_unique_key(db, table):
    """기본 키 또는 UNIQUE 색인이 있으면 행 내용 전체도 겹치지 않는다(뷰는 없음으로 본다)."""
    kind = db.execute("SELECT type FROM sqlite_master WHERE name=?", (table,)).fetchone()
    if kind is None or kind[0] != 'table':
        return False
    if any(r[5] for r in db.execute('PRAGMA table_info(' + _name(table) + ')')):
        return True
    return any(r[2] for r in db.execute('PRAGMA index_list(' + _name(table) + ')'))


def plain_rows(db, table, columns):
    """(row_key, row) — 키 있는 표는 저장 순서 그대로, 없는 표·뷰는 내용 순."""
    unique = has_unique_key(db, table)
    select = 'SELECT ' + ','.join(_name(c) for c in columns) + ' FROM ' + _name(table)
    if not unique:
        select += ' ORDER BY ' + ','.join(_name(c) for c in columns)
    previous, repeat = None, 0
    for row in db.execute(select):
        if unique:
            yield None, row
            continue
        values = tuple(row)
        repeat = repeat + 1 if values == previous else 0
        previous = values
        yield repeat, row


def plain_key(value, repeat):
    return [ROW_KEY_VERSION, value] if repeat is None else [ROW_KEY_VERSION, value, repeat]


def length_key(unit_index, rowid, logical_id):
    return [ROW_KEY_VERSION, str(logical_id)] if unit_index else rowid


def posting_key(unit_index, doc, column, token, logical_id):
    return [ROW_KEY_VERSION, str(logical_id), column, token] if unit_index else [doc, column, token]
