"""Append-only review journal for reference-resolution observations and approvals."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
import uuid

from .contracts import digest
from .legal_agent.context import now
from .legal_agent.errors import BudgetExhausted, ContractError, ProposalError
from .legal_agent.repository import encoded


DDL = '''
PRAGMA user_version=1;
CREATE TABLE meta(key TEXT PRIMARY KEY,value_json TEXT NOT NULL CHECK(json_valid(value_json)));
CREATE TABLE case_record(
  case_id TEXT PRIMARY KEY,reference_id TEXT NOT NULL,binding_hash TEXT NOT NULL,
  source_json TEXT NOT NULL CHECK(json_valid(source_json)),parse_kind TEXT NOT NULL,reason TEXT,
  state TEXT NOT NULL,candidate_set_sha256 TEXT NOT NULL,observation_id TEXT,
  created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE candidate_record(
  case_id TEXT NOT NULL,candidate_id TEXT NOT NULL,ordinal INTEGER NOT NULL,target_json TEXT NOT NULL CHECK(json_valid(target_json)),
  basis TEXT NOT NULL,PRIMARY KEY(case_id,candidate_id),UNIQUE(case_id,ordinal),
  FOREIGN KEY(case_id) REFERENCES case_record(case_id));
CREATE TABLE evidence_record(
  case_id TEXT NOT NULL,evidence_id TEXT NOT NULL,json TEXT NOT NULL CHECK(json_valid(json)),
  PRIMARY KEY(case_id,evidence_id),FOREIGN KEY(case_id) REFERENCES case_record(case_id));
CREATE TABLE model_view(
  view_id TEXT PRIMARY KEY,case_ids_json TEXT NOT NULL CHECK(json_valid(case_ids_json)),body_json TEXT NOT NULL CHECK(json_valid(body_json)),
  body_hash TEXT NOT NULL,candidate_set_sha256 TEXT NOT NULL,state_revision INTEGER NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE model_attempt(
  attempt_id TEXT PRIMARY KEY,logical_call_id TEXT NOT NULL,attempt_no INTEGER NOT NULL,view_id TEXT NOT NULL,
  request_json TEXT NOT NULL CHECK(json_valid(request_json)),request_hash TEXT NOT NULL,status TEXT NOT NULL,
  response_json TEXT CHECK(response_json IS NULL OR json_valid(response_json)),response_hash TEXT,
  receipt_json TEXT CHECK(receipt_json IS NULL OR json_valid(receipt_json)),started_at TEXT NOT NULL,finished_at TEXT,
  FOREIGN KEY(view_id) REFERENCES model_view(view_id));
CREATE TABLE observation(
  observation_id TEXT PRIMARY KEY,case_id TEXT NOT NULL,view_id TEXT NOT NULL,selected_json TEXT NOT NULL CHECK(json_valid(selected_json)),
  evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)),explanation TEXT NOT NULL,abstain_reason TEXT,
  resolution_state TEXT NOT NULL,output_hash TEXT NOT NULL,validator_status TEXT NOT NULL,created_at TEXT NOT NULL,
  FOREIGN KEY(case_id) REFERENCES case_record(case_id),FOREIGN KEY(view_id) REFERENCES model_view(view_id));
CREATE TABLE review(
  review_id TEXT PRIMARY KEY,case_id TEXT NOT NULL,observation_hash TEXT,decision TEXT NOT NULL,
  reviewer TEXT NOT NULL,reason TEXT NOT NULL,reviewed_at TEXT NOT NULL,
  FOREIGN KEY(case_id) REFERENCES case_record(case_id));
CREATE TABLE event(
  seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,kind TEXT NOT NULL,payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
  payload_hash TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE budget(singleton INTEGER PRIMARY KEY CHECK(singleton=1),model_limit INTEGER NOT NULL,model_reserved INTEGER NOT NULL DEFAULT 0);
CREATE TABLE apply_receipt(receipt_id TEXT PRIMARY KEY,json TEXT NOT NULL CHECK(json_valid(json)),created_at TEXT NOT NULL);
'''


class ReferenceResolutionRepository:
    VERSION = 1

    def __init__(self, path, *, identity=None, max_model_attempts=0):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        create = not self.path.exists()
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA busy_timeout=5000')
        if create:
            if identity is None:
                self.close()
                raise ContractError('new reference journal requires an identity')
            self.db.executescript(DDL)
            with self.transaction():
                self.db.execute('INSERT INTO meta VALUES (?,?)', ('identity', encoded(identity)))
                self.db.execute('INSERT INTO meta VALUES (?,?)', ('state_revision', encoded(0)))
                self.db.execute('INSERT INTO budget VALUES (1,?,0)', (max_model_attempts,))
                self.event('JOURNAL_CREATED', {'identity_hash': digest(identity)})
        elif self.db.execute('PRAGMA user_version').fetchone()[0] != self.VERSION:
            self.close()
            raise ContractError('reference journal migration required')
        if identity is not None and self.identity() != identity:
            self.close()
            raise ContractError('reference journal identity mismatch')

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def identity(self):
        row = self.db.execute("SELECT value_json FROM meta WHERE key='identity'").fetchone()
        return json.loads(row[0])

    def revision(self):
        return json.loads(self.db.execute("SELECT value_json FROM meta WHERE key='state_revision'").fetchone()[0])

    def _advance(self):
        revision = self.revision() + 1
        self.db.execute("UPDATE meta SET value_json=? WHERE key='state_revision'", (encoded(revision),))
        return revision

    def event(self, kind, payload, **_):
        self.db.execute('INSERT INTO event(event_id,kind,payload_json,payload_hash,created_at) VALUES (?,?,?,?,?)',
                        (uuid.uuid4().hex, kind, encoded(payload), digest(payload), now()))

    def _insert_case(self, case, state, stamp):
        self.db.execute('''INSERT INTO case_record(case_id,reference_id,binding_hash,source_json,parse_kind,reason,
            state,candidate_set_sha256,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (case['case_id'], case['reference_id'], case['binding_hash'], encoded(case['source']),
             case['parse']['kind'], case['parse'].get('current_reason'), state,
             case['candidate_set_sha256'], stamp, stamp))
        self.db.executemany('INSERT INTO candidate_record VALUES (?,?,?,?,?)', [
            (case['case_id'], target['id'], ordinal, encoded({k: v for k, v in target.items() if k not in ('id', 'basis')}),
             target['basis']) for ordinal, target in enumerate(case['candidates'])])
        self.db.executemany('INSERT INTO evidence_record VALUES (?,?,?)', [
            (case['case_id'], evidence['id'], encoded(evidence)) for evidence in case['evidence']])

    def add_case(self, case, state):
        self.add_cases([(case, state)])

    def add_cases(self, cases):
        if not cases:
            return
        with self.transaction():
            stamp = now()
            counts = {}
            for case, state in cases:
                self._insert_case(case, state, stamp)
                counts[state] = counts.get(state, 0) + 1
            self._advance(); self.event('CASES_DETECTED', {'count': len(cases), 'states': counts})

    def cases(self, states=None, limit=None):
        sql, args = 'SELECT * FROM case_record', []
        if states:
            sql += ' WHERE state IN (' + ','.join('?' for _ in states) + ')'; args.extend(states)
        sql += ' ORDER BY case_id'
        if limit is not None:
            sql += ' LIMIT ?'; args.append(limit)
        return [dict(row) for row in self.db.execute(sql, args)]

    def case_view(self, case_id):
        row = self.db.execute('SELECT * FROM case_record WHERE case_id=?', (case_id,)).fetchone()
        if not row:
            raise ProposalError('unknown reference case: ' + case_id)
        candidates = []
        for candidate in self.db.execute('SELECT * FROM candidate_record WHERE case_id=? ORDER BY ordinal', (case_id,)):
            candidates.append({'id': candidate['candidate_id'], 'basis': candidate['basis'], **json.loads(candidate['target_json'])})
        evidence = [json.loads(item['json']) for item in self.db.execute(
            'SELECT json FROM evidence_record WHERE case_id=? ORDER BY evidence_id', (case_id,))]
        return {'case_id': case_id, 'reference_id': row['reference_id'], 'source': json.loads(row['source_json']),
                'parse': {'kind': row['parse_kind'], 'current_reason': row['reason']},
                'candidates': candidates, 'evidence': evidence,
                'candidate_set_sha256': row['candidate_set_sha256']}

    def save_view(self, cases):
        body = {'cases': cases}
        case_ids = [case['case_id'] for case in cases]
        combined = digest([case['candidate_set_sha256'] for case in cases])
        ident = 'V' + uuid.uuid4().hex
        with self.transaction():
            rows = self.db.execute('SELECT case_id,state,candidate_set_sha256 FROM case_record WHERE case_id IN ('
                                   + ','.join('?' for _ in case_ids) + ')', case_ids).fetchall()
            if len(rows) != len(case_ids) or any(row['state'] != 'CANDIDATES_READY' for row in rows):
                raise ProposalError('reference cases are not ready for a model view')
            if digest([self.case_view(case_id)['candidate_set_sha256'] for case_id in case_ids]) != combined:
                raise ContractError('candidate set changed while creating model view')
            revision = self.revision()
            self.db.execute('INSERT INTO model_view VALUES (?,?,?,?,?,?,?)',
                            (ident, encoded(case_ids), encoded(body), digest(body), combined, revision, now()))
            self.db.executemany("UPDATE case_record SET state='MODEL_PENDING',updated_at=? WHERE case_id=?",
                                [(now(), case_id) for case_id in case_ids])
            self._advance(); self.event('MODEL_VIEW', {'view_id': ident, 'case_ids': case_ids})
        return {**body, 'view_id': ident}

    def reserve_attempt(self, view, request, logical_call_id, attempt_no, phase):
        with self.transaction():
            budget = self.db.execute('SELECT * FROM budget WHERE singleton=1').fetchone()
            if budget['model_reserved'] >= budget['model_limit']:
                raise BudgetExhausted('reference-resolution model attempt limit')
            ident = 'M' + uuid.uuid4().hex
            self.db.execute('UPDATE budget SET model_reserved=model_reserved+1 WHERE singleton=1')
            self.db.execute('''INSERT INTO model_attempt(attempt_id,logical_call_id,attempt_no,view_id,request_json,
                request_hash,status,started_at) VALUES (?,?,?,?,?,?,'PREPARED',?)''',
                (ident, logical_call_id, attempt_no, view['view_id'], encoded(request), digest(request), now()))
            self.event('ATTEMPT_RESERVED', {'attempt_id': ident, 'phase': phase})
        return ident

    def attempt_sent(self, ident):
        with self.transaction():
            if self.db.execute("UPDATE model_attempt SET status='SENT' WHERE attempt_id=? AND status='PREPARED'", (ident,)).rowcount != 1:
                raise ContractError('reference attempt already sent')
            self.event('ATTEMPT_SENT', {'attempt_id': ident})

    def finish_attempt(self, ident, status, response, receipt):
        with self.transaction():
            attempt = self.db.execute('SELECT * FROM model_attempt WHERE attempt_id=?', (ident,)).fetchone()
            view = self.db.execute('SELECT * FROM model_view WHERE view_id=?', (attempt['view_id'],)).fetchone()
            case_ids = json.loads(view['case_ids_json'])
            if status == 'SUCCEEDED':
                current = self.db.execute('SELECT state,candidate_set_sha256 FROM case_record WHERE case_id IN ('
                    + ','.join('?' for _ in case_ids) + ') ORDER BY case_id', case_ids).fetchall()
                if any(row['state'] != 'MODEL_PENDING' for row in current):
                    status = 'IGNORED_LATE'
            updated = self.db.execute('''UPDATE model_attempt SET status=?,response_json=?,response_hash=?,receipt_json=?,finished_at=?
                WHERE attempt_id=? AND status='SENT' ''',
                (status, encoded(response) if response is not None else None,
                 digest(response) if response is not None else None, encoded(receipt), now(), ident)).rowcount
            if updated != 1:
                raise ContractError('reference attempt was not sent')
            self.event('ATTEMPT_FINISHED', {'attempt_id': ident, 'status': status})
        return status

    def store_observations(self, view_id, rows):
        view = self.db.execute('SELECT * FROM model_view WHERE view_id=?', (view_id,)).fetchone()
        if not view:
            raise ProposalError('unknown reference model view')
        if not self.db.execute("SELECT 1 FROM model_attempt WHERE view_id=? AND status='SUCCEEDED'", (view_id,)).fetchone():
            raise ProposalError('reference model view has no successful physical attempt')
        case_ids = json.loads(view['case_ids_json'])
        if set(case_ids) != {row['case_id'] for row in rows}:
            raise ProposalError('observation batch does not match model view')
        with self.transaction():
            for row in rows:
                current = self.db.execute('SELECT state FROM case_record WHERE case_id=?', (row['case_id'],)).fetchone()
                if not current or current['state'] != 'MODEL_PENDING':
                    raise ProposalError('stale reference observation')
                ident = 'O' + uuid.uuid4().hex
                payload = {k: row[k] for k in ('case_id', 'selected_candidate_ids', 'evidence_ids',
                                                'abstain_reason', 'explanation', 'resolution_state')}
                output_hash = digest(payload)
                self.db.execute('INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (ident, row['case_id'], view_id, encoded(row['selected_candidate_ids']), encoded(row['evidence_ids']),
                     row['explanation'], row['abstain_reason'], row['resolution_state'], output_hash,
                     'VALIDATED', now()))
                self.db.execute("UPDATE case_record SET state='VALIDATED',observation_id=?,updated_at=? WHERE case_id=?",
                                (ident, now(), row['case_id']))
                self.event('MODEL_OBSERVED', {'case_id': row['case_id'], 'observation_id': ident,
                                               'resolution_state': row['resolution_state']})
            self._advance()

    def fail_view(self, view_id, state):
        if state not in ('MODEL_FAILED', 'MODEL_UNKNOWN'):
            raise ValueError('invalid model failure state')
        with self.transaction():
            view = self.db.execute('SELECT case_ids_json FROM model_view WHERE view_id=?', (view_id,)).fetchone()
            if not view:
                return
            case_ids = json.loads(view[0])
            self.db.executemany("UPDATE case_record SET state=?,updated_at=? WHERE case_id=? AND state='MODEL_PENDING'",
                                [(state, now(), case_id) for case_id in case_ids])
            self._advance(); self.event(state, {'view_id': view_id, 'case_ids': case_ids})

    def review_case(self, case_id, decision, reviewer, reason):
        if decision not in ('APPROVE', 'REJECT', 'UNKNOWN'):
            raise ValueError('invalid review decision')
        with self.transaction():
            case = self.db.execute('SELECT * FROM case_record WHERE case_id=?', (case_id,)).fetchone()
            if not case:
                raise ProposalError('unknown reference case')
            observation_hash = None
            if decision == 'APPROVE':
                if case['state'] != 'VALIDATED' or not case['observation_id']:
                    raise ProposalError('only a validated observation can be approved')
                observation = self.db.execute(
                    'SELECT output_hash,selected_json FROM observation WHERE observation_id=?',
                    (case['observation_id'],)).fetchone()
                if not json.loads(observation['selected_json']):
                    raise ProposalError('an abstained observation cannot be approved')
                observation_hash = observation['output_hash']
                state = 'APPROVED'
            elif decision == 'REJECT':
                state = 'REJECTED'
            else:
                state = 'UNKNOWN'
            ident = 'R' + uuid.uuid4().hex
            self.db.execute('INSERT INTO review VALUES (?,?,?,?,?,?,?)',
                            (ident, case_id, observation_hash, decision, reviewer, reason, now()))
            self.db.execute('UPDATE case_record SET state=?,updated_at=? WHERE case_id=?', (state, now(), case_id))
            self._advance(); self.event('REVIEWED', {'case_id': case_id, 'decision': decision})

    def observation(self, case_id):
        row = self.db.execute('''SELECT o.* FROM case_record c JOIN observation o ON o.observation_id=c.observation_id
            WHERE c.case_id=?''', (case_id,)).fetchone()
        if not row:
            return None
        value = dict(row)
        value['selected_candidate_ids'] = json.loads(value.pop('selected_json'))
        value['evidence_ids'] = json.loads(value.pop('evidence_json'))
        return value

    def summary(self):
        return {'schema_version': 'reference-review-v1',
                'cases': dict(self.db.execute('SELECT state,count(*) FROM case_record GROUP BY state')),
                'attempts': dict(self.db.execute('SELECT status,count(*) FROM model_attempt GROUP BY status')),
                'reviews': dict(self.db.execute('SELECT decision,count(*) FROM review GROUP BY decision')),
                'budget': dict(self.db.execute('SELECT * FROM budget WHERE singleton=1').fetchone()),
                'state_revision': self.revision(), 'canonical_approval': False, 'runtime_promoted': False}
