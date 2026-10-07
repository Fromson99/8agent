"""V3 durable purposes, relation versions, tasks and exact delivery receipts."""
from contextlib import contextmanager
import json
import uuid
from ..contracts import digest
from .tools_repository import ToolsRepository
from .repository import encoded
from .errors import ContractError, ProposalError


class RelationsRepository(ToolsRepository):
    VERSION = 3
    DDL = 'journal-v3.sql'

    @contextmanager
    def transaction(self):
        # Existing evidence/entity primitives participate in the caller's atomic commit.
        if not self.db.in_transaction:
            with super().transaction():
                yield
            return
        name = 's'+uuid.uuid4().hex
        self.db.execute('SAVEPOINT '+name)
        try:
            yield
            self.db.execute('RELEASE '+name)
        except BaseException:
            self.db.execute('ROLLBACK TO '+name)
            self.db.execute('RELEASE '+name)
            raise

    @staticmethod
    def assessment_id(evidence, question):
        return 'A'+digest([evidence, question])[:28]

    def notice(self, relation):
        return self.head('relation', relation)['payload']

    def notices(self):
        return [h['payload'] for h in self.heads('relation', current=True)]

    def record_notice(self, notice):
        ident = notice['relation_id']
        old = next((h for h in self.heads('relation', current=True) if h['entity_id']==ident), None)
        if old and old['payload']==notice:
            return
        seq = self.event('RELATION_NOTICE', {'relation_id': ident, 'hash': digest(notice)}, advance=True)
        self.put('relation', ident, notice, seq)
        for e in notice.get('source_evidence', []):
            relations = sorted(n['relation_id'] for n in self.notices() if e in n.get('source_evidence', []))
            head = next((h for h in self.heads('relation_set', current=True) if h['entity_id']==e), None)
            payload = {'evidence': e, 'relations': relations}
            if not head or head['payload'] != payload:
                self.put('relation_set', e, payload, seq)
        self.db.execute('UPDATE stage_artifact SET valid=0')

    def enqueue_system(self, parent, evidence, operation, depth):
        ident = 'SYS'+digest([self.run()['run_id'], parent, self.binding['profile_sha256'], operation])[:28]
        if not self.db.execute('SELECT 1 FROM system_task WHERE task_id=?', (ident,)).fetchone():
            seq = self.event('SYSTEM_TASK_QUEUED', {'task_id': ident, 'operation': operation})
            self.db.execute('INSERT INTO system_task VALUES(?,?,?,?,?,?,?,?)',
                (ident, parent, evidence, encoded(operation), depth, 'PENDING', None, seq))
        return ident

    def save_view(self, phase, body, evidence_ids):
        exact=body.get('exact_evidence',[])
        if {e['evidence'] for e in exact}!=set(evidence_ids):
            raise ContractError('view exact evidence IDs differ from presentation')
        for e in exact:
            raw=self.evidence(e['evidence'])
            if e.get('text')!=raw['text'] or e.get('spans')!=raw['spans']:
                raise ContractError('view exact evidence text differs from stored source')
        with self.transaction():
            view = super().save_view(phase, body, evidence_ids)
            for n in view.get('relation_notices',[]):
                stored=self.notice(n['relation_id'])
                if any(n.get(k)!=v for k,v in stored.items()):
                    raise ContractError('view relation differs from stored notice')
                self.db.execute('INSERT INTO item_presentation VALUES(?,?,?,?)',
                    (view['view_id'],'relation',n['relation_id'],stored['notice_hash']))
            def visit(value):
                if isinstance(value, dict):
                    if value.get('preview_spans') and value.get('preview_hash'):
                        self.db.execute('INSERT OR IGNORE INTO item_presentation VALUES(?,?,?,?)',
                            (view['view_id'], 'preview', value['preview_hash'], digest(value['preview_spans'])))
                    for x in value.values(): visit(x)
                elif isinstance(value, list):
                    for x in value: visit(x)
            visit(view)
            return view

    def reserve_attempt(self, view, request, *args, numbered_references=None, wire_projection=None):
        # The receipt names what went onto the wire, not an untransmitted saved view.
        try:
            wire = json.loads(request['messages'][1]['content'])['view']
            stored = json.loads(self.db.execute('SELECT body_json FROM model_view WHERE view_id=?', (view['view_id'],)).fetchone()[0])
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise ContractError('v3 attempt requires exact wire view') from exc
        expected = stored
        if numbered_references is not None:
            from .numbered_references import NumberedReferences
            verified = NumberedReferences(stored)
            if numbered_references.receipt(view) != verified.receipt(stored):
                raise ContractError('numbered references differ from stored presentation')
            expected = verified.view(stored)
        if wire_projection is not None:
            from .gateway import WIRE_PROJECTION, compact_wire_view
            if self.VERSION != 5 or wire_projection != WIRE_PROJECTION:
                raise ContractError('unsupported wire projection')
            expected = compact_wire_view(expected, stored['phase'])
        if wire != expected or view != stored:
            raise ContractError('wire view differs from stored presentation')
        with self.transaction():
            ident = super().reserve_attempt(view, request, *args)
            if numbered_references is not None:
                self.event('NUMBERED_REFERENCES', {'attempt_id': ident, 'wire_view_hash': digest(wire),
                    **numbered_references.receipt(stored)})
            if wire_projection is not None:
                self.event('WIRE_PROJECTION', {'attempt_id': ident, 'projection': wire_projection,
                    'stored_view_hash': digest(stored), 'wire_view_hash': digest(wire)})
            return ident

    def item_visible(self, view_id, kind, ident, content_hash):
        if not self.db.execute('''SELECT 1 FROM item_presentation p JOIN model_attempt a USING(view_id)
             WHERE p.view_id=? AND p.kind=? AND p.item_id=? AND p.content_hash=? AND a.status='SUCCEEDED' ''',
             (view_id, kind, ident, content_hash)).fetchone():
            raise ProposalError(kind+' not presented in this successful view: '+ident)

    def coverage(self, *, final=False):
        out = []
        for e in self.evidence():
            ident = e['evidence_id']
            shown = bool(self.db.execute('''SELECT 1 FROM presentation p JOIN model_attempt a USING(view_id)
                WHERE p.evidence_id=? AND a.status='SUCCEEDED' ''', (ident,)).fetchone())
            assessments = [h for h in self.heads('assessment') if h['payload']['evidence']==ident]
            current = [h for h in assessments if h['validity']=='CURRENT']
            status = 'ASSESSED' if current else 'STALE' if assessments else 'PRESENTED_UNASSESSED' if shown else 'READ_STORED_NOT_PRESENTED'
            out.append({'evidence': ident, 'status': 'UNASSESSED_AT_STOP' if final and not current else status,
                'last_state': status, 'presented': shown, 'assessments': [
                    {'assessment_id': h['entity_id'], 'version': h['version'], 'validity': h['validity'], **h['payload']} for h in assessments]})
        return out

    def stop_pending(self, reason):
        with self.transaction():
            for task in self.db.execute("SELECT task_id FROM system_task WHERE status IN ('PENDING','RUNNING')").fetchall():
                self.db.execute("UPDATE system_task SET status='INTERRUPTED',result_json=? WHERE task_id=?", (encoded({'reason': reason}), task[0]))
            for action in self.db.execute("SELECT action_id,status FROM action_context WHERE status IN ('PROPOSED','RUNNING')").fetchall():
                result={'action_id':action[0],'status':'INTERRUPTED','server_reason':reason,'evidence_ids':[]}
                self.db.execute("UPDATE action_context SET status='INTERRUPTED',result_json=? WHERE action_id=?",(encoded(result),action[0]))
                self.event('ACTION_INTERRUPTED',result)
            self.event('UNASSESSED_AT_STOP', {'reason': reason, 'coverage': self.coverage(final=True)})

    def fail(self, code, *, interrupted=False):
        if self.run()['status']=='RUNNING':
            self.stop_pending(code)
        return super().fail(code, interrupted=interrupted)

    def dependency_hash(self):
        return digest({'v2': super().dependency_hash(), 'relations': self.heads('relation'),
                       'relation_sets': self.heads('relation_set'), 'assessments': self.heads('relation_assessment')})
