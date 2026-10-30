"""Local append-only review queue. Capturing a phrase is not concept approval."""
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import uuid

from .contracts import digest, sha
from .navigation_learning import VERSION, string, validate_item, validate_bundle


def connect(path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE IF NOT EXISTS candidate(id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS review_event(
            seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
            candidate_id TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS review_candidate ON review_event(candidate_id, seq);
    ''')
    return db


def propose(path, kind, payload):
    if kind not in ('expression', 'recipe'):
        raise ValueError('invalid candidate kind')
    ident = 'candidate:' + digest({'kind': kind, 'payload': payload})
    with closing(connect(path)) as db, db:
        db.execute('INSERT OR IGNORE INTO candidate VALUES (?,?,?)',
                   (ident, kind, json.dumps(payload, ensure_ascii=False, sort_keys=True)))
    return ident


def collect_run(path, run_path):
    """Conservative gap proposals with exact offsets; replay is idempotent.

    Unmatched chunks are deliberately noisy review candidates, not extracted facts.
    No question text is sent to an external service by this function.
    """
    run_path = Path(run_path)
    raw = run_path.read_bytes()
    import hashlib
    run_hash = hashlib.sha256(raw).hexdigest()
    run = json.loads(raw); query = run['query']; question = query['question']
    string(question, 10000)
    state = run['retrieval']['term_agent']
    if 'matched_question_spans' not in state:
        raise ValueError('run lacks complete matcher coverage; recollect with learning-capable runtime')
    masked = list(question)
    for span in state['matched_question_spans']:
        start, end = span['start'], span['end']
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(question):
            raise ValueError('invalid captured question span')
        if question[start:end] != span['text']:
            raise ValueError('captured span text mismatch')
        masked[start:end] = '\n' * (end-start)
    result = []
    for match in re.finditer(r'[^\n\r,.!?;:，。！？]+', ''.join(masked)):
        chunk = match.group(); start = match.start() + len(chunk)-len(chunk.lstrip())
        end = match.end() - (len(chunk)-len(chunk.rstrip()))
        expression = question[start:end]
        if not 2 <= len(expression) <= 120 or expression in {'알려줘', '알려주세요', '설명해줘', '무엇인가요'}:
            continue
        payload = {'generation_id': query['generation_id'],
                   'document_version_ids': query['scope']['document_version_ids'],
                   'expression': expression, 'span': {'start': start, 'end': end},
                   'query_id': query['id'], 'run_sha256': run_hash,
                   'source_store_sha256': run['answer']['source_store_sha256'],
                   'origin': 'UNMATCHED_QUESTION_SPAN', 'canonical_approval': False}
        result.append(propose(path, 'expression', payload))
        if len(result) == 8:
            break
    return result


def candidates(path):
    with closing(connect(path)) as db:
        rows = db.execute('''SELECT c.*, e.status, e.payload AS review FROM candidate c
            LEFT JOIN review_event e ON e.seq=(SELECT max(seq) FROM review_event WHERE candidate_id=c.id)
            ORDER BY c.id''').fetchall()
    return [{'id': r['id'], 'kind': r['kind'], 'payload': json.loads(r['payload']),
             'status': r['status'] or 'PROPOSED',
             'review': json.loads(r['review']) if r['review'] else None} for r in rows]


def resubmit(path, candidate_id, reason):
    """Fork rejected/revoked observations without losing their original run evidence."""
    string(reason, 1000)
    with closing(connect(path)) as db:
        row = db.execute('SELECT kind,payload FROM candidate WHERE id=?', (candidate_id,)).fetchone()
        last = db.execute('SELECT status FROM review_event WHERE candidate_id=? ORDER BY seq DESC LIMIT 1',
                          (candidate_id,)).fetchone()
    if row is None or last is None or last['status'] not in ('REJECTED', 'REVOKED'):
        raise ValueError('resubmit requires a rejected or revoked candidate')
    payload = json.loads(row['payload'])
    payload['revision'] = {'parent_candidate_id': candidate_id, 'reason': reason}
    return propose(path, row['kind'], payload)


def review(path, candidate_id, status, reviewer, reason, term_id=None):
    if status not in ('APPROVED', 'REJECTED', 'REVOKED'):
        raise ValueError('invalid review status')
    string(reviewer, 200); string(reason, 1000)
    with closing(connect(path)) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            row = db.execute('SELECT * FROM candidate WHERE id=?', (candidate_id,)).fetchone()
            if row is None:
                raise ValueError('unknown learning candidate')
            last = db.execute('SELECT status FROM review_event WHERE candidate_id=? ORDER BY seq DESC LIMIT 1', (candidate_id,)).fetchone()
            previous = last['status'] if last else 'PROPOSED'
            allowed = {'PROPOSED': {'APPROVED', 'REJECTED'}, 'APPROVED': {'REVOKED'}}
            if status not in allowed.get(previous, set()):
                raise ValueError('invalid review transition; submit a new candidate for revision')
            payload = json.loads(row['payload']); item = None
            event_id = 'review:' + uuid.uuid4().hex
            if status == 'APPROVED':
                if row['kind'] == 'expression':
                    string(term_id)
                    item = {'id': candidate_id, 'expression': payload['expression'],
                            'term_id': term_id, 'document_version_ids': payload['document_version_ids']}
                else:
                    item = payload['item']
                item = {**item, 'review': {'reviewer': reviewer, 'reason': reason,
                        'event_id': event_id, 'candidate_sha256': digest(payload),
                        'evidence': payload.get('run_sha256') or payload.get('evidence', '')}}
                validate_item(item, row['kind'])
            event = {'id': event_id, 'candidate_id': candidate_id, 'status': status,
                     'reviewer': reviewer, 'reason': reason, 'item': item,
                     'at': datetime.now(timezone.utc).isoformat()}
            db.execute('INSERT INTO review_event(id,candidate_id,status,payload) VALUES (?,?,?,?)',
                       (event_id, candidate_id, status, json.dumps(event, ensure_ascii=False)))
            db.commit()
        except BaseException:
            db.rollback(); raise
    return event


def publish(path, output, generation_id, manifest_sha256, source_store_sha256, terms, documents):
    bundle = {'schema_version': VERSION, 'id': 'learning:' + uuid.uuid4().hex,
              'generation_id': generation_id, 'generation_manifest_sha256': manifest_sha256,
              'expressions': [], 'recipes': []}
    for row in candidates(path):
        if row['status'] != 'APPROVED' or row['payload']['generation_id'] != generation_id:
            continue
        if row['payload']['source_store_sha256'] != source_store_sha256:
            raise ValueError('candidate source store changed; re-review required')
        key = 'expressions' if row['kind'] == 'expression' else 'recipes'
        bundle[key].append(row['review']['item'])
    validate_bundle(bundle, generation_id, manifest_sha256, terms, documents)
    # Hard-link publication provides atomic, no-overwrite visibility on the same filesystem.
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.learning-', dir=output.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(bundle, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {'path': str(output), 'sha256': sha(output), 'bundle_id': bundle['id'],
            'expressions': len(bundle['expressions']), 'recipes': len(bundle['recipes']),
            'activated': False}
