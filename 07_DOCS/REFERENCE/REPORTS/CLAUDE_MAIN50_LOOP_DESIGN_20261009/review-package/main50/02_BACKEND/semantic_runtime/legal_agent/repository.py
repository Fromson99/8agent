"""Transactional, versioned work state and immutable evidence/presentation ledger."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid

from ..contracts import digest
from .. import observability as obs
log=obs.get_logger('journal')
from .context import now
from .errors import BudgetExhausted, ContractError, ProposalError, StaleProposal
from . import protocol


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def text_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


class WorkRepository:
    VERSION = 1
    DDL = 'journal.sql'

    def __init__(self, path, context=None, profile=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        create = not self.path.exists()
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA busy_timeout=5000')
        self.context = context
        if create:
            if context is None or profile is None:
                self.close()
                raise ContractError('new journal requires request binding and profile')
            script = Path(__file__).with_name(self.DDL).read_text()
            pragmas, marker, schema = script.partition('PRAGMA user_version')
            if not marker:
                self.close()
                raise ContractError('journal schema version declaration missing')
            # Connection PRAGMAs stay outside the transaction. Schema, version,
            # seed rows and request binding become durable together, avoiding
            # an autocommit/fsync for every CREATE TABLE/INDEX/TRIGGER on NFS.
            try:
                self.db.executescript(pragmas+'BEGIN IMMEDIATE;\n'+marker+schema)
                self.db.execute('''INSERT INTO run(singleton,run_id,query_id,binding_hash,binding_json,request_json,
                    status,phase,owner_boot_id,started_at,deadline_at) VALUES(1,?,?,?,?,?,'RUNNING','INVESTIGATE',?,?,?)''',
                    (context.run_id, context.query['id'], context.binding_hash, encoded(context.binding),
                     encoded(context.request), uuid.uuid4().hex, now(), context.deadline_at))
                self.db.execute('INSERT INTO budget(singleton,model_limit,finalization_reserve,tool_limit) VALUES(1,?,?,?)',
                                (profile['max_model_attempts'], profile['finalization_reserve'], profile['max_tool_actions']))
                self.db.execute('COMMIT')
            except BaseException:
                if self.db.in_transaction:
                    self.db.execute('ROLLBACK')
                self.close()
                raise
        elif self.db.execute('PRAGMA user_version').fetchone()[0] != self.VERSION:
            self.close()
            raise ContractError('journal migration required')
        self.binding = json.loads(self.run()['binding_json'])
        if digest(self.binding) != self.run()['binding_hash']:
            self.close()
            raise ContractError('journal binding hash mismatch')
        if context and context.binding_hash != self.run()['binding_hash']:
            self.close()
            raise ContractError('request binding mismatch')
        self._changed = False

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        started=time.perf_counter();cpu=time.thread_time();entered=committing=finished=None
        try:
            self.db.execute('BEGIN IMMEDIATE')
            entered=time.perf_counter()
            yield
            committing=time.perf_counter()
            self.db.execute('COMMIT')
            finished=time.perf_counter()
        except BaseException:
            if self.db.in_transaction:self.db.execute('ROLLBACK')
            raise
        finally:
            ended=time.perf_counter()
            obs.event(log,'journal.transaction.timings',
                      begin_ms=round(((entered or ended)-started)*1000,3),
                      body_ms=round(((committing or ended)-entered)*1000,3) if entered else 0,
                      commit_ms=round(((finished or ended)-committing)*1000,3) if committing else 0,
                      thread_cpu_ms=round((time.thread_time()-cpu)*1000,3),committed=finished is not None)

    @contextmanager
    def navigation_batch(self):
        """Stage only handles/cursors in memory; commit before exposing the result."""
        if getattr(self, '_navigation_pending', None) is not None:
            yield
            return
        self._navigation_pending = {'navigation_handle': {}, 'navigation_cursor': {}}
        try:
            yield
            if any(self._navigation_pending.values()):
                with self.transaction():
                    self.flush_navigation()
        finally:
            self._navigation_pending = None

    def navigation_row(self, table, key):
        columns = {'navigation_handle': ('handle','kind','identity_json','binding_hash'),
                   'navigation_cursor': ('cursor','operation_hash','position_json','binding_hash')}
        names = columns[table]
        pending = getattr(self, '_navigation_pending', None)
        if pending is not None and key in pending[table]:
            return dict(zip(names, pending[table][key]))
        return self.db.execute('SELECT * FROM '+table+' WHERE '+names[0]+'=?',(key,)).fetchone()

    def navigation_save(self, table, row):
        if table not in {'navigation_handle','navigation_cursor'}:
            raise ContractError('invalid navigation journal table')
        pending = getattr(self, '_navigation_pending', None)
        if pending is None:
            self.db.execute('INSERT OR IGNORE INTO '+table+' VALUES(?,?,?,?)',row)
        else:
            previous = self.navigation_row(table, row[0])
            if previous is not None:
                if tuple(previous.values() if isinstance(previous,dict) else previous) != tuple(row):
                    raise ContractError('navigation identity collision')
                return
            pending[table][row[0]] = tuple(row)

    def navigation_handle(self, kind, raw, binding):
        pending = getattr(self, '_navigation_pending', None)
        staged = pending['navigation_handle'] if pending is not None else {}
        for row in staged.values():
            if row[1:] == (kind,raw,binding): return row[0]
        row = self.db.execute('SELECT handle FROM navigation_handle WHERE kind=? AND identity_json=? AND binding_hash=?',
                              (kind,raw,binding)).fetchone()
        if row: return row[0]
        count = self.db.execute('SELECT count(*) FROM navigation_handle WHERE kind=?',(kind,)).fetchone()[0]
        count += sum(r[1]==kind for r in staged.values())
        ident = kind+str(count+1)
        self.navigation_save('navigation_handle',(ident,kind,raw,binding))
        return ident

    def flush_navigation(self):
        pending = getattr(self, '_navigation_pending', None)
        if pending is None: return
        if not self.db.in_transaction:
            raise ContractError('navigation flush requires a transaction')
        for table, rows in pending.items():
            self.db.executemany('INSERT OR IGNORE INTO '+table+' VALUES(?,?,?,?)',rows.values())
        for rows in pending.values(): rows.clear()

    def run(self):
        return dict(self.db.execute('SELECT * FROM run WHERE singleton=1').fetchone())

    def budget(self):
        return dict(self.db.execute('SELECT * FROM budget WHERE singleton=1').fetchone())

    def event(self, kind, payload, *, event_id=None, advance=False, evidence=False):
        r = self.run()
        after = r['state_revision']+int(advance)
        seq = r['next_event_seq']
        self.db.execute('INSERT INTO event VALUES(?,?,?,?,?,?,?,?)',
                        (seq, event_id or uuid.uuid4().hex, kind, r['state_revision'], after,
                         encoded(payload), digest(payload), now()))
        self.db.execute('UPDATE run SET state_revision=?,evidence_revision=evidence_revision+?,next_event_seq=? WHERE singleton=1',
                        (after, int(evidence), seq+1))
        from .readable_log import is_error_event
        if is_error_event(kind):
            obs.event(log,'agent.error',level=40,run_id=r['run_id'],
                journal_seq=seq,error_event=kind,error_diagnostics=payload,
                error_record=encoded(payload))
        return seq

    def head(self, kind, ident, *, current=True, expected=None):
        row = self.db.execute('''SELECT h.*,v.payload_json FROM entity_head h JOIN entity_version v
            USING(kind,entity_id,version) WHERE h.kind=? AND h.entity_id=?''', (kind, ident)).fetchone()
        if not row or (current and row['validity'] != 'CURRENT'):
            raise ProposalError('missing or non-current '+kind+': '+str(ident))
        if expected is not None and row['version'] != expected:
            raise StaleProposal('entity version changed')
        return {**dict(row), 'payload': json.loads(row['payload_json'])}

    def heads(self, kind=None, *, current=False):
        sql = 'SELECT h.*,v.payload_json FROM entity_head h JOIN entity_version v USING(kind,entity_id,version)'
        rows = self.db.execute(sql+' ORDER BY h.kind,h.entity_id')
        return [{k: r[k] for k in ('kind', 'entity_id', 'version', 'validity')} | {'payload': json.loads(r['payload_json'])}
                for r in rows if (kind is None or r['kind'] == kind) and (not current or r['validity'] == 'CURRENT')]

    def invalidate(self, kind, ident, version):
        rows = self.db.execute('''WITH RECURSIVE affected(kind,entity_id,version) AS (
          SELECT ?,?,? UNION SELECT d.dependent_kind,d.dependent_id,d.dependent_version
          FROM dependency d JOIN affected a ON d.prerequisite_kind=a.kind
          AND d.prerequisite_id=a.entity_id AND d.prerequisite_version=a.version)
          SELECT * FROM affected''', (kind, ident, version)).fetchall()
        for r in rows:
            self.db.execute("UPDATE entity_head SET validity='STALE' WHERE kind=? AND entity_id=? AND version=? AND validity='CURRENT'", tuple(r))
        if kind in ('issue', 'fact', 'assessment', 'finding'):
            self.db.execute('UPDATE stage_artifact SET valid=0')
        else:
            self.db.execute("UPDATE stage_artifact SET valid=0 WHERE stage='answer'")

    def put(self, kind, ident, payload, seq, *, dependencies=(), evidence_ids=(), validity='CURRENT'):
        old = self.db.execute('SELECT version FROM entity_head WHERE kind=? AND entity_id=?', (kind, ident)).fetchone()
        version = old[0]+1 if old else 1
        deps = []
        for dep_kind, dep_id in dependencies:
            if dep_kind == kind and dep_id == ident:
                raise ProposalError('cyclic dependency')
            head = self.head(dep_kind, dep_id)
            # Versions form a DAG because every prerequisite must already exist.
            # Reject logical cycles too, even when they pass through an older version.
            cycle = self.db.execute('''WITH RECURSIVE ancestors(k,i,v) AS (
              SELECT ?,?,? UNION SELECT d.prerequisite_kind,d.prerequisite_id,d.prerequisite_version
              FROM dependency d JOIN ancestors a ON d.dependent_kind=a.k AND d.dependent_id=a.i
              AND d.dependent_version=a.v) SELECT 1 FROM ancestors WHERE k=? AND i=? LIMIT 1''',
              (dep_kind, dep_id, head['version'], kind, ident)).fetchone()
            if cycle:
                raise ProposalError('cyclic entity dependency')
            deps.append((dep_kind, dep_id, head['version']))
        if old:
            self.invalidate(kind, ident, old[0])
        self.db.execute('INSERT INTO entity_version VALUES(?,?,?,?,?,?)',
                        (kind, ident, version, encoded(payload), digest(payload), seq))
        self.db.execute('INSERT INTO entity_head VALUES(?,?,?,?) ON CONFLICT(kind,entity_id) DO UPDATE SET version=excluded.version,validity=excluded.validity',
                        (kind, ident, version, validity))
        self.db.executemany('INSERT INTO dependency VALUES(?,?,?,?,?,?)',
                            [(kind, ident, version, *dep) for dep in sorted(set(deps))])
        self.db.executemany('INSERT INTO evidence_dependency VALUES(?,?,?,?)',
                            [(kind, ident, version, e) for e in sorted(set(evidence_ids))])
        self._changed = True
        return ident

    def evidence(self, ident=None):
        rows = self.db.execute('SELECT * FROM evidence_unit'+(' WHERE evidence_id=?' if ident else '')+' ORDER BY evidence_id',
                               (ident,) if ident else ())
        result = []
        for row in rows:
            spans = [dict(s) for s in self.db.execute('SELECT * FROM evidence_span WHERE evidence_id=? ORDER BY ordinal', (row['evidence_id'],))]
            text = '\n'.join(s['text'] for s in spans)
            if text_hash(text) != row['text_hash']:
                raise ContractError('stored evidence hash mismatch')
            result.append({**dict(row), 'metadata': json.loads(row['metadata_json']), 'spans': spans, 'text': text})
        if ident:
            if not result:
                raise ProposalError('unknown evidence: '+str(ident))
            return result[0]
        return result

    def visible(self, view_id, evidence_ids):
        for ident in evidence_ids:
            e = self.evidence(ident)
            row = self.db.execute('''SELECT 1 FROM presentation p JOIN model_attempt a ON a.view_id=p.view_id
                WHERE p.evidence_id=? AND p.delivered_text_hash=? AND a.status='SUCCEEDED'
                AND (p.view_id=? OR a.created_seq < (SELECT created_seq FROM model_view WHERE view_id=?)) LIMIT 1''',
                (ident, e['text_hash'], view_id, view_id)).fetchone()
            if not row:
                raise ProposalError('evidence was not presented in a successful model call: '+ident)

    def check_view(self, view_id, phase):
        row = self.db.execute('SELECT * FROM model_view WHERE view_id=?', (view_id,)).fetchone()
        if not row or row['phase'] != phase:
            raise ProposalError('unknown or wrong-phase view')
        r = self.run()
        if r['status'] != 'RUNNING' or row['base_state_revision'] != r['state_revision']:
            raise StaleProposal('work changed since model view')
        if not self.db.execute("SELECT 1 FROM model_attempt WHERE view_id=? AND status='SUCCEEDED'", (view_id,)).fetchone():
            raise ProposalError('model view has no successful response')
        return json.loads(row['body_json'])

    def save_view(self, phase, body, evidence_ids):
        with obs.step(log,'model.view_save',phase=phase):
            ident = 'V'+uuid.uuid4().hex
            r = self.run()
            body = {**body, 'view_id': ident, 'phase': phase, 'base_state_revision': r['state_revision'], 'evidence_revision': r['evidence_revision']}
            with self.transaction():
                seq = self.event('MODEL_VIEW', {'view_id': ident, 'hash': digest(body)})
                self.db.execute('INSERT INTO model_view VALUES(?,?,?,?,?,?,?)',
                                (ident, phase, r['state_revision'], r['evidence_revision'], encoded(body), digest(body), seq))
                for e in evidence_ids:
                    self.db.execute('INSERT INTO presentation VALUES(?,?,?)', (ident, e, self.evidence(e)['text_hash']))
            return body

    def reserve_attempt(self, view, request, logical_call_id, attempt_no, phase):
        with self.transaction():
            budget = self.budget()
            budget_class = view.get('budget_class')
            if budget_class is not None:
                final = view.get('source_stage') in ('memory-assess','memory-assess-repair','memory-compose','memory-compose-repair')
                if budget_class != ('FINALIZE' if final else 'INVESTIGATE') or phase != ('compose' if final else 'investigate'):
                    raise ContractError('invalid host budget classification')
            cap = budget['model_limit']-(budget['finalization_reserve'] if phase == 'investigate' else 0)
            if self.run()['status'] != 'RUNNING' or budget['model_reserved'] >= cap:
                raise BudgetExhausted('model attempt limit; finalization reserve preserved')
            ident = 'M'+uuid.uuid4().hex
            seq = self.event('ATTEMPT_RESERVED', {'attempt_id': ident})
            self.db.execute('UPDATE budget SET model_reserved=model_reserved+1 WHERE singleton=1')
            self.db.execute('''INSERT INTO model_attempt(attempt_id,logical_call_id,attempt_no,view_id,request_json,
                request_hash,status,started_at,created_seq) VALUES(?,?,?,?,?,?,'PREPARED',?,?)''',
                (ident, logical_call_id, attempt_no, view['view_id'], encoded(request), digest(request), now(), seq))
        return ident

    def attempt_sent(self, ident):
        with self.transaction():
            if self.db.execute("UPDATE model_attempt SET status='SENT' WHERE attempt_id=? AND status='PREPARED'", (ident,)).rowcount != 1:
                raise ContractError('attempt already sent')
            self.event('ATTEMPT_SENT', {'attempt_id': ident})

    def finish_attempt(self, ident, status, response, receipt):
        usage = receipt.get('usage') or {}
        with self.transaction():
            row = self.db.execute('SELECT v.base_state_revision FROM model_attempt a JOIN model_view v USING(view_id) WHERE a.attempt_id=?', (ident,)).fetchone()
            if status == 'SUCCEEDED' and (self.run()['status'] != 'RUNNING' or row[0] != self.run()['state_revision']
                                         or (self.context is not None and time.monotonic() >= self.context.deadline)):
                status = 'IGNORED_LATE'
            self.db.execute('''UPDATE model_attempt SET status=?,response_json=?,response_hash=?,receipt_json=?,
                input_tokens=?,output_tokens=?,finished_at=? WHERE attempt_id=? AND status='SENT' ''',
                (status, encoded(response) if response is not None else None, digest(response) if response is not None else None,
                 encoded(receipt), usage.get('prompt_tokens'), usage.get('completion_tokens'), now(), ident))
            self.event('ATTEMPT_FINISHED', {'attempt_id': ident, 'status': status})
        return status

    def reserve_tool(self):
        with self.transaction():
            if self.db.execute('UPDATE budget SET tool_used=tool_used+1 WHERE singleton=1 AND tool_used<tool_limit').rowcount != 1:
                raise BudgetExhausted('tool action limit')
            self.event('TOOL_RESERVED', {})

    def record_observation(self, action, result, evidence=(), *, verify):
        # Exact source validation is performed against the request's read-only Store.
        for item in evidence:
            verify(item)
        ident = 'O'+uuid.uuid4().hex
        key = digest({'action': {k: action[k] for k in ('tool', 'args')}, 'binding': self.run()['binding_hash']})
        with self.transaction():
            novel = not self.db.execute('SELECT 1 FROM observation WHERE request_key=? AND result_hash=?', (key, digest(result))).fetchone()
            new_evidence = [e for e in evidence if not self.db.execute('SELECT 1 FROM evidence_unit WHERE evidence_id=?', (e['evidence_id'],)).fetchone()]
            seq = self.event('OBSERVATION', {'observation_id': ident, 'request_key': key}, advance=novel, evidence=bool(new_evidence))
            for e in new_evidence:
                self.db.execute('INSERT INTO evidence_unit VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    tuple(e[k] for k in ('evidence_id', 'source_id', 'document_id', 'unit_id', 'generation_id', 'source_artifact_hash', 'text_hash', 'role', 'temporal_status'))+
                    (encoded(e['metadata']), seq))
                for n, s in enumerate(e['spans']):
                    self.db.execute('INSERT INTO evidence_span VALUES(?,?,?,?,?,?,?,?)',
                        (e['evidence_id'], n, s['block_id'], s['start_cp'], s['end_cp'], s['text'], s['block_hash'], s['span_hash']))
            self.db.execute('INSERT INTO observation VALUES(?,?,?,?,?,?,?,?)',
                            (ident, action['tool'], key, encoded(action), encoded(result), digest(result), result['status'], seq))
            self.db.executemany('INSERT INTO observation_evidence VALUES(?,?)', [(ident, e['evidence_id']) for e in evidence])
            if new_evidence:
                self.db.execute('UPDATE stage_artifact SET valid=0')
        return {**result, 'observation_id': ident, 'request_key': key}

    def observations(self, limit=8):
        rows = self.db.execute('SELECT * FROM observation ORDER BY created_seq DESC LIMIT ?', (limit,)).fetchall()
        return [{'observation_id': r['observation_id'], 'action': json.loads(r['request_json']),
                 **json.loads(r['result_json'])} for r in reversed(rows)]

    def snapshot(self):
        return {'state_revision': self.run()['state_revision'], 'evidence_revision': self.run()['evidence_revision'],
                'entities': self.heads(), 'frontier': self.frontier(), 'budget': self.budget()}

    def frontier(self):
        return [{**dict(r), 'action': json.loads(r['operation_json'])} for r in self.db.execute('SELECT * FROM frontier ORDER BY priority DESC,item_id')]

    def enqueue(self, action, reason, seq, issue_id=None):
        protocol.validate('ToolAction', action)
        key = digest({'action': {k: action[k] for k in ('tool', 'args')}, 'binding': self.run()['binding_hash'],
                      'issue': self.head('issue', issue_id)['payload'] if issue_id else None})
        if self.db.execute('SELECT 1 FROM frontier WHERE dedupe_key=?', (key,)).fetchone():
            return
        self.db.execute("INSERT INTO frontier VALUES(?,?,?,?,'PENDING',?,?,NULL,?)",
                        ('T'+uuid.uuid4().hex, issue_id, encoded(action), key, 1, reason, seq))

    def finish_frontier(self, ident, observation):
        with self.transaction():
            status = 'DONE' if observation['status'] in ('OK', 'TRUNCATED') else 'EXHAUSTED'
            self.db.execute('UPDATE frontier SET status=?,last_observation_id=? WHERE item_id=?',
                            (status, observation['observation_id'], ident))
            self.event('FRONTIER_FINISHED', {'item_id': ident, 'status': status})

    def save_artifact(self, stage, payload):
        with self.transaction():
            revision = self.db.execute('SELECT coalesce(max(artifact_revision),0)+1 FROM stage_artifact WHERE stage=?', (stage,)).fetchone()[0]
            seq = self.event('STAGE_ARTIFACT', {'stage': stage, 'revision': revision})
            self.db.execute('UPDATE stage_artifact SET valid=0 WHERE stage=?', (stage,))
            self.db.execute('INSERT INTO stage_artifact VALUES(?,?,?,?,?,?,?,1,?)',
                            ('ART'+uuid.uuid4().hex, stage, revision, self.run()['evidence_revision'],
                             self.dependency_hash(), encoded(payload), digest(payload), seq))

    def dependency_hash(self):
        return digest({'heads': [h for h in self.heads() if h['kind'] in ('issue', 'fact', 'assessment', 'finding')],
                       'evidence_revision': self.run()['evidence_revision']})

    def assert_assembly_current(self):
        row = self.db.execute("SELECT * FROM stage_artifact WHERE stage='assemble' AND valid=1").fetchone()
        if not row or row['dependency_hash'] != self.dependency_hash():
            raise ContractError('stale assembly cannot be recomposed')

    def apply_proposal(self, view, proposal, *, event_id):
        from .updates import apply_updates
        protocol.validate('InvestigateDecision', proposal)
        payload_hash = digest({'view_id': view['view_id'], 'proposal': proposal})
        with self.transaction():
            old = self.db.execute('SELECT payload_json FROM event WHERE event_id=?', (event_id,)).fetchone()
            if old:
                value = json.loads(old[0])
                if value['proposal_hash'] != payload_hash:
                    raise ProposalError('event ID reused for different proposal')
                return value['id_map']
            self.check_view(view['view_id'], 'investigate')
            before = self.run()
            self._changed = False
            # Reserve event first for FK references; rollback removes it on any failure.
            seq = before['next_event_seq']
            id_map = apply_updates(self, view, proposal['updates'], seq, dry_ids=True)
            advanced = bool(proposal['updates'])
            self.event('PROPOSAL', {'proposal_hash': payload_hash, 'id_map': id_map, 'proposal': proposal}, event_id=event_id, advance=advanced)
            apply_updates(self, view, proposal['updates'], seq, id_map=id_map)
            after = before['state_revision']+int(advanced)
            if self.db.execute('''UPDATE run SET state_revision=?, evidence_revision=evidence_revision+?
                WHERE singleton=1 AND status='RUNNING' AND state_revision=? AND binding_hash=?''',
                (after, int(self._changed), after, before['binding_hash'])).rowcount != 1:
                raise StaleProposal('proposal CAS failed')
            if self._changed:
                self.db.execute('UPDATE stage_artifact SET valid=0')
        return id_map

    def fail(self, code, *, interrupted=False, diagnostics=None):
        with self.transaction():
            if self.run()['status'] == 'RUNNING':
                self.event('RUN_FAILED', {'code': code, 'diagnostics': diagnostics,
                    'phase_at_failure': self.run()['phase'], 'interrupted': interrupted})
                self.db.execute("UPDATE run SET status=?,phase='END' WHERE singleton=1", ('INTERRUPTED' if interrupted else 'FAILED',))
