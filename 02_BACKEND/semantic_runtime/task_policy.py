"""Reviewed, immutable task definitions and local append-only execution records."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from .contracts import digest, sha
from .navigation_loop import TOOLS

VERSION = 'definition-scope-harness-v1'
EXTRA_TOOLS = {
    'CONCEPT': '{term_id,status:"selected"|"rejected"|"uncertain"}: 개념 후보 검토. 행동 reason 필수',
    'ASK_USER': '{question}: 개념 또는 요청이 모호하면 사용자 확인으로 종료',
}
ALL_TOOLS = {**TOOLS, **EXTRA_TOOLS}
DEFAULT = {
    'schema_version': VERSION, 'id': 'definition_scope', 'version': 1,
    'obligations': [
        {'id': 'definition', 'text': '개념의 정의와 정의가 성립하는 문서·버전·범위'},
        {'id': 'requirements', 'text': '개념에 포함되는 요건과 적용 범위'},
        {'id': 'exceptions', 'text': '제외·예외와 적용 한계; 확인되지 않은 사항은 미확인으로 유지'},
    ],
    'tools': ALL_TOOLS,
    'transitions': {'EXPLORING': list(ALL_TOOLS)},
    'limits': {'max_calls': 20, 'max_actions': 56, 'wall_seconds': 300,
               'active_segments': 6, 'active_chars': 18000, 'context_chars': 60000,
               'max_errors': 3, 'max_no_progress': 4},
    'completion': 'reviewed_evidence_for_every_obligation_v1',
}


def validate_definition(value):
    if set(value) != set(DEFAULT) or value['schema_version'] != VERSION:
        raise ValueError('unsupported task definition contract')
    if value['id'] != 'definition_scope' or type(value['version']) is not int or value['version'] < 1:
        raise ValueError('unsupported task type/version')
    obligations = value['obligations']
    if (not isinstance(obligations, list) or len(obligations) != 3
            or {x['id'] for x in obligations} != {'definition', 'requirements', 'exceptions'}):
        raise ValueError('definition/scope obligations required')
    for item in obligations:
        if set(item) != {'id', 'text'} or not isinstance(item['text'], str) or not item['text'].strip():
            raise ValueError('invalid obligation')
    if value['tools'] != ALL_TOOLS or value['completion'] != DEFAULT['completion']:
        raise ValueError('unsupported tool contract or completion operator')
    transitions = value['transitions']
    if (set(transitions) != {'EXPLORING'} or not isinstance(transitions['EXPLORING'], list)
            or set(transitions['EXPLORING']) - ALL_TOOLS.keys()
            or not {'STOP', 'ASK_USER'} <= set(transitions['EXPLORING'])):
        raise ValueError('unsupported transition')
    if set(value['limits']) != set(DEFAULT['limits']):
        raise ValueError('invalid budget fields')
    for key, count in value['limits'].items():
        if type(count) is not int or not 1 <= count <= DEFAULT['limits'][key]:
            raise ValueError('budget exceeds supported ceiling: ' + key)
    return deepcopy(value)


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.executescript('''
        CREATE TABLE IF NOT EXISTS definition(id TEXT, version INTEGER, hash TEXT, payload TEXT,
                                              PRIMARY KEY(id,version));
        CREATE TABLE IF NOT EXISTS review(hash TEXT PRIMARY KEY, definition_hash TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS checkpoint(run_id TEXT, seq INTEGER, hash TEXT, payload TEXT,
                                              PRIMARY KEY(run_id,seq));
        CREATE TABLE IF NOT EXISTS proposal(id TEXT PRIMARY KEY, run_id TEXT, payload TEXT);
    ''')
    return db


def propose_definition(path, definition):
    value = validate_definition(definition)
    with closing(connect(path)) as db, db:
        db.execute('INSERT INTO definition VALUES (?,?,?,?)',
                   (value['id'], value['version'], digest(value), json.dumps(value, ensure_ascii=False)))
    return {'id': value['id'], 'version': value['version'], 'definition_sha256': digest(value),
            'status': 'PROPOSED'}


def review_definition(path, ident, version, reviewer, reason):
    if not reviewer.strip() or not reason.strip():
        raise ValueError('reviewer and review basis required')
    with closing(connect(path)) as db, db:
        row = db.execute('SELECT hash,payload FROM definition WHERE id=? AND version=?',
                         (ident, version)).fetchone()
        if row is None or digest(validate_definition(json.loads(row[1]))) != row[0]:
            raise ValueError('missing or altered definition')
        receipt = {'definition_sha256': row[0], 'reviewer': reviewer, 'reason': reason,
                   'status': 'APPROVED', 'at': datetime.now(timezone.utc).isoformat()}
        db.execute('INSERT INTO review VALUES (?,?,?)',
                   (digest(receipt), row[0], json.dumps(receipt, ensure_ascii=False)))
    return {**receipt, 'review_sha256': digest(receipt)}


def load_definition(path, binding):
    path = Path(path)
    if sha(path) != binding['sha256']:
        raise ValueError('task policy DB hash mismatch')
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        row = db.execute('SELECT hash,payload FROM definition WHERE id=? AND version=?',
                         (binding['id'], binding['version'])).fetchone()
        review = db.execute('SELECT definition_hash,payload FROM review WHERE hash=?',
                            (binding['review_sha256'],)).fetchone()
    if row is None or review is None:
        raise ValueError('task definition is not explicitly reviewed')
    value = validate_definition(json.loads(row[1]))
    receipt = json.loads(review[1])
    if (digest(value) != row[0] or row[0] != binding['definition_sha256']
            or review[0] != row[0] or receipt['definition_sha256'] != row[0]
            or digest(receipt) != binding['review_sha256'] or receipt['status'] != 'APPROVED'):
        raise ValueError('task definition/review binding mismatch')
    if sha(path) != binding['sha256']:
        raise ValueError('task policy changed while loading')
    return value


def load_bound_definition(generation, binding):
    base = Path(generation).resolve()
    path = (base / binding['path']).resolve()
    path.relative_to(base)
    return load_definition(path, binding)


def checkpoint(path, run_id, state, proposals=()):
    """Commit state and unapproved improvement candidates together; no execution rights."""
    with closing(connect(path)) as db, db:
        seq = db.execute('SELECT coalesce(max(seq),0)+1 FROM checkpoint WHERE run_id=?',
                         (run_id,)).fetchone()[0]
        db.execute('INSERT INTO checkpoint VALUES (?,?,?,?)',
                   (run_id, seq, digest(state), json.dumps(state, ensure_ascii=False)))
        for item in proposals:
            payload = {**item, 'run_id': run_id, 'status': 'PROPOSED', 'canonical_approval': False}
            db.execute('INSERT OR IGNORE INTO proposal VALUES (?,?,?)',
                       ('proposal:' + digest(payload), run_id, json.dumps(payload, ensure_ascii=False)))
    return seq
