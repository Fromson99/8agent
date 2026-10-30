"""Append-only ledger of relations the model rejected while answering.

A rejection holds only inside its request (work_navigation demotes and re-searches); here
it is kept so the source of the relation - a bridge code policy, a reference resolution -
can be fixed for the next generation. This is a clean-up list, not an approval queue:
nothing reads it back into serving.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

SCHEMA = '''CREATE TABLE IF NOT EXISTS rejection(
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, generation_id TEXT NOT NULL, index_sha256 TEXT NOT NULL,
  relation_id TEXT NOT NULL, kind TEXT NOT NULL, relation TEXT NOT NULL,
  question TEXT NOT NULL, reason TEXT NOT NULL, quote TEXT, run_id TEXT)'''


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute(SCHEMA)
    return db


def record(path, rejections, *, generation_id, index_sha256, question, run_id=None):
    if not rejections:
        return 0
    at = datetime.now(timezone.utc).isoformat()
    with connect(path) as db:
        db.executemany('INSERT INTO rejection(at,generation_id,index_sha256,relation_id,kind,relation,question,reason,quote,run_id) '
                       'VALUES(?,?,?,?,?,?,?,?,?,?)',
                       [(at, generation_id, index_sha256, r['relation_id'], r['relation']['kind'],
                         json.dumps(r['relation'], ensure_ascii=False, sort_keys=True), question, r['reason'],
                         r.get('quote'), run_id) for r in rejections])
    return len(rejections)


def summary(path, kind=None, limit=50):
    """Relations by how often they were rejected, most first; the fix list for the next build."""
    if not Path(path).is_file():
        return []
    with connect(path) as db:
        rows = db.execute('SELECT relation_id,kind,relation,count(*),count(DISTINCT question),max(at),'
                          'group_concat(reason,"\n") FROM rejection WHERE ? IS NULL OR kind=? '
                          'GROUP BY generation_id,relation_id ORDER BY count(*) DESC,relation_id LIMIT ?',
                          (kind, kind, limit)).fetchall()
    return [{'relation_id': r[0], 'kind': r[1], 'relation': json.loads(r[2]), 'rejections': r[3],
             'questions': r[4], 'last_at': r[5], 'reasons': r[6].split('\n')[:5]} for r in rows]
