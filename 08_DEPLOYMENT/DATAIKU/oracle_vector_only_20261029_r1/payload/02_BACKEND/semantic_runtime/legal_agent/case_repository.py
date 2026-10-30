"""Current case authority; immutable native judgment refs and transactional outbox.

The v3 store is deliberately separate from legacy memory-v2. Work journals own
model/evidence records. This store accepts their refs, never rewrites them.
"""
import json
from contextlib import contextmanager
from pathlib import Path
from .corrected_memory import Memory, MemoryError, Conflict, STAGES, digest, encoded
from .publication import owner_lock


class CaseRepository(Memory):
    VERSION = 3
    conditional_reuse = True
    resume_requests = True

    def __init__(self,path,executor,invoke):
        Path(path).parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        super().__init__(path,executor,invoke)
        Path(path).chmod(0o600)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS judgment_ref(node INTEGER PRIMARY KEY REFERENCES node(id),ref TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,kind TEXT NOT NULL,aggregate_id TEXT NOT NULL,
          revision INTEGER NOT NULL,payload TEXT NOT NULL,hash TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING');
        CREATE TABLE IF NOT EXISTS import_receipt(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS experience_dependency(question_id TEXT NOT NULL,experience_id TEXT NOT NULL,
          PRIMARY KEY(question_id,experience_id));
        CREATE TABLE IF NOT EXISTS session_export(session_id TEXT PRIMARY KEY,public_only INTEGER NOT NULL);
        CREATE TRIGGER IF NOT EXISTS ref_no_update BEFORE UPDATE ON judgment_ref BEGIN SELECT RAISE(ABORT,'immutable ref'); END;
        CREATE TRIGGER IF NOT EXISTS ref_no_delete BEFORE DELETE ON judgment_ref BEGIN SELECT RAISE(ABORT,'immutable ref'); END;
        CREATE TRIGGER IF NOT EXISTS event_no_update BEFORE UPDATE ON event BEGIN SELECT RAISE(ABORT,'immutable event'); END;
        CREATE TRIGGER IF NOT EXISTS event_no_delete BEFORE DELETE ON event BEGIN SELECT RAISE(ABORT,'immutable event'); END;
        ''')

    def request_key(self,body,principal):
        return digest([principal['user_id'],principal['team_id'],body['session_id'],body['request_id']])

    @contextmanager
    def owner(self,body,principal):
        lock=Path(self.path).parent/'owners'/digest([principal['user_id'],principal['team_id'],body['session_id']])
        try:
            with owner_lock(lock):
                self.owner_held=True
                try:yield
                finally:self.owner_held=False
        except BlockingIOError as exc:
            raise Conflict('case session is being updated; retry after the active request') from exc

    def execute(self,body,principal):
        if not getattr(self,'owner_held',False):
            with self.owner(body,principal):return self.execute(body,principal)
        self.__dict__.pop('request_routing',None)
        self.executor.__dict__.pop('request_entry',None)
        self._entry_body=body
        self._entry_principal=principal
        self.identity(body['session_id'],principal)
        old=self.db.execute('SELECT status,input_hash FROM request WHERE id=?',(self.request_key(body,principal),)).fetchone()
        recovered=False
        if old and old['status']=='RUNNING':
            from .workflow_execution import recover_abandoned_request
            if recover_abandoned_request(self,body,principal,old):
                with self.transaction():
                    self.db.execute("UPDATE request SET status='FAILED' WHERE id=? AND status='RUNNING' AND response IS NULL",
                                    (self.request_key(body,principal),))
                old=self.db.execute('SELECT status,input_hash FROM request WHERE id=?',(self.request_key(body,principal),)).fetchone()
                recovered=True
        self.resume_goal=None
        if old and old['status']=='FAILED' and old['input_hash']==digest({'body':body,'principal':principal}):
            row=self.db.execute("SELECT g.id FROM event e JOIN goal g ON g.id=e.goal WHERE e.request=? AND g.session=? AND g.status='PENDING' ORDER BY e.id DESC LIMIT 1",
                (body['request_id'],body['session_id'])).fetchone()
            if row:self.resume_goal=row['id']
        external=self.executor.model.pipeline.term_agent.transport.binding['trust_zone']=='external'
        with self.transaction():
            row=self.db.execute('SELECT public_only FROM session_export WHERE session_id=?',(body['session_id'],)).fetchone()
            from .workflow_execution import authorization
            approved_workflow = authorization() is not None
            if external and not approved_workflow and (body.get('public_question') is not True or (row and not row[0])):
                raise MemoryError('private session history is not approved for external transfer')
            public=int(body.get('public_question') is True)
            self.db.execute('INSERT INTO session_export VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET public_only=MIN(public_only,excluded.public_only)',
                (body['session_id'],public))
        if recovered:
            # A process can exit after the route commit but before caching the
            # response. Publish those committed parts without a new judgment.
            row=self.db.execute('''SELECT g.id,e.command FROM event e JOIN goal g ON g.id=e.goal
                WHERE e.request=? AND g.session=? ORDER BY e.id DESC LIMIT 1''',
                (body['request_id'],body['session_id'])).fetchone()
            goal=self.goal(row['id'],body['session_id']) if row else None
            if goal and goal['status']=='READY':
                route=self.route(goal['id']);parts=self.parts(goal['id'])
                if (not route or route['revision']!=goal['revision'] or
                        route['payload']['binding']!=self.executor.binding or
                        route['payload']['nodes']!={s:parts[s]['id'] for s in STAGES}):
                    raise MemoryError('abandoned request committed route changed')
                with self.executor.open(goal['state'],principal,body) as execution:
                    originals={e['evidence_id']:e for e in parts['READ']['payload']['evidence']+
                        parts['SELECT']['payload'].get('selected_evidence',[])}
                    self.executor.verify({'binding':parts['READ']['payload']['binding'],
                                          'evidence':list(originals.values())})
                    execution.s.work.record_observation(
                        {'tool':'workflow_committed_original_restore','args':{'route_hash':digest(route['payload'])}},
                        {'status':'REUSED'},list(originals.values()),verify=execution.s.sources.source.verify)
                knowledge=route['payload'].get('reused_experience_id')
                result={'status':'REUSED' if knowledge else 'READY','goal_id':goal['id'],
                    'revision':goal['revision'],'route_id':route['id'],'state':goal['state'],
                    'executed':[],'answer':parts['COMPOSE']['payload'],'knowledge_id':knowledge,
                    'method_id':json.loads(row['command'])['method_id']}
                self.validate_response(result,principal,body['session_id'])
                self.db.execute("UPDATE request SET status='COMPLETE',response=? WHERE id=?",
                    (encoded(result),self.request_key(body,principal)))
                return result
        return super().execute(body,principal)

    def resolve(self,context):
        if self.resume_goal:
            from .corrected_memory import COMMAND
            g=next(g for g in context['goals'] if g['id']==self.resume_goal)
            return {'method_id':'RESEARCH_REENTER','document_scope_mode':'KEEP','action':'FOLLOW',
                'target':g['id'],'knowledge_id':None,'stage':g['pending'] or 'INTENT','task':None,
                'source_category':'KEEP','document_ids':None,'facts':None,'queries':None,
                'restore_event':None,'restore_fields':[],'format':'prose','reason':'resume the recorded incomplete request'}
        from .workflow_execution import reentry
        command = reentry(self, context)
        if command is not None:return command
        entry=getattr(self.executor,'request_entry',None)
        if entry is not None and entry['command'] is not None:
            self.admit(entry['command'],context)
            return dict(entry['command'])
        c=super().resolve(context)
        if c['action'] in ('START','REUSE') and c.get('target') is None:
            from ..pipeline import route_question
            _,category=route_question(context['utterance'])
            if category is not None:c['source_category']=category
        return c

    def direct_request(self,context):
        """Route before commands, procedure replay, or any legal checkpoints."""
        # execute() sets this only for the same failed request fingerprint and
        # an existing pending goal. Its CASE route is already established;
        # both native and shortcut consumers must resume without rerouting.
        if getattr(self,'resume_goal',None):return None
        from .workflow_execution import has_reentry
        if has_reentry():return None
        from .source_query_planning import (CASE_ROUTING_SYSTEM, CAPABILITIES,
            case_routing_schema, validate_case_routing)
        if not hasattr(self,'request_routing'):
            from .request_entry import eligible,run
            if eligible(self,context):run(self,context)
        if not hasattr(self,'request_routing'):
            data={'question':context['utterance'],
                'current_goals':[{'task':g['state']['task'],'facts':g['state']['facts'],
                                 'status':g['status']} for g in context['goals']],
                'capabilities':{**CAPABILITIES,'limitations':['등록되고 요청 범위에 허용된 자료만 조회']}}
            from . import output_contract as output
            routing_schema=case_routing_schema()
            def propose(payload,attempt):
                return self.invoke(CASE_ROUTING_SYSTEM,payload,routing_schema,
                    'source-request-route' if not attempt else 'source-request-route-repair')
            def check(value):
                output.validate_shape(value,routing_schema)
                try:validate_case_routing(value)
                except ValueError as exc:
                    raise output.OutputContractError(str(exc),
                        [output.issue('REQUEST_ROUTING_CONFLICT')],category='DECISION_CONFLICT') from exc
            self.request_routing=output.bounded_decision(
                self,'request-routing',data,routing_schema,propose,check,
                identity={'request':self._entry_body,'principal':self._entry_principal,
                    'binding':self.executor.binding,'view':data})
            self.executor.model.ensure().work.event('REQUEST_ROUTED',{
                **self.request_routing,'owner':'V6_ENTRY','agent_required':self.request_routing['mode']!='DIRECT'})
        if self.request_routing['mode']=='BROWSE':
            session=self.executor.model.ensure()
            filters=dict(self.request_routing['catalogue'])
            from ..pipeline import route_question
            _,category=route_question(context['utterance'])
            if category is not None:filters['document_category']='all' if category == 'ALL' else category
            # Reuse the bound, budgeted catalogue tools. A model cannot supply
            # the returned document names or expand the request allowlist.
            allowed=set(self._entry_principal['document_ids'])
            requested=self._entry_body.get('document_ids')
            if requested:allowed.intersection_update(requested)
            text,plan=session.catalogue_observation(
                {'mode':'BROWSE','inspect_documents':False,**filters},
                document_scope=allowed)
            if plan is not None:raise MemoryError('catalogue response cannot start a legal case')
            return {'status':'CLARIFY','answer':{'text':text,'claims':[],'limitations':[]},
                    'request_routing':self.request_routing,'executed':[]}
        if self.request_routing['mode']=='DIRECT':
            # The existing no-judgment response contract already accepts CLARIFY.
            # request_routing explicitly distinguishes ordinary guidance here.
            return {'status':'CLARIFY','answer':{'text':self.request_routing['answer'],
                    'claims':[],'limitations':[]},'request_routing':self.request_routing,'executed':[]}
        return None

    def _execute(self,body,principal):
        direct=self.direct_request(self.context(body['session_id'],principal,body['question']))
        if direct is not None:return direct
        return super()._execute(body,principal)

    def context(self,session,principal,utterance):
        context=super().context(session,principal,utterance)
        context['goals']=[g for g in context['goals'] if set(g['state']['document_ids'])<=set(principal['document_ids'])]
        from .knowledge_repository import KnowledgeRepository
        knowledge=KnowledgeRepository(self)
        # Original events and explicitly named correction ordinals remain
        # available when a long transcript is reduced for the model input.
        import re
        ordinals={int(x) for x in re.findall(r'(\d+)\s*(?:번째|차)?\s*정정',utterance)}
        for word,index in [('첫',1),('두',2),('세',3),('네',4),('다섯',5),('여섯',6),('일곱',7),('여덟',8),('아홉',9),('열',10)]:
            if re.search(word+r'\s*번째\s*정정',utterance):ordinals.add(index)
        for g in context['goals']:
            events=g['events'];keep={e['id'] for e in events[:1]+events[-48:]}
            keep.update(e['id'] for e in events if e.get('correction_ordinal') in ordinals)
            g['events']=[e for e in events if e['id'] in keep]
            g['event_count']=len(events);g['history_partial']=len(g['events'])!=len(events)
        valid=[]
        for k in context['knowledge']:
            try:knowledge.get(k['id'],principal)
            except MemoryError:continue
            valid.append(k)
        context['knowledge']=valid
        context['wiki_links']={question:experience for question,experience in context['wiki_links'].items()
            if experience in {k['id'] for k in valid}}
        # Legal experience refs remain available without a personal wiki/history view.
        context['legal_wiki']=[{'experience_id':k['id'],'concepts':k['concepts']} for k in valid]
        return context

    def candidates(self,principal,query):
        candidates=super().candidates(principal,query)
        if self.executor.model.pipeline.term_agent.transport.binding['trust_zone']!='external':return candidates
        # A public current question does not authorize exporting another
        # conversation's private conditions or concept observations.
        return [k for k in candidates if self.db.execute('''SELECT 1 FROM goal g
            JOIN session_export e ON e.session_id=g.session
            WHERE g.id=? AND e.public_only=1''',(k['bundle'],)).fetchone()]

    def stage_recorded(self,node,stage,payload,execution):
        ref=getattr(execution,'last_judgment_ref',None)
        if ref is None:raise MemoryError('stage has no native judgment reference')
        if ref['payload_hash']!=digest(payload):raise MemoryError('native judgment hash mismatch')
        self.db.execute('INSERT INTO judgment_ref VALUES(?,?)',(node,encoded(ref)))

    def stage_committed(self,node,stage,payload,execution):
        # The native journal records validation first; public acceptance follows
        # the durable case revision/head transaction. A late result stays private.
        pending=getattr(execution,'pending_judgment',None)
        if not pending:return
        with self.transaction():
            row=self.db.execute('SELECT n.hash,n.revision,g.revision FROM node n JOIN goal g ON g.id=n.goal JOIN head h ON h.node=n.id WHERE n.id=? AND h.stage=?',(node,stage)).fetchone()
            if row is None or row[0]!=digest(payload) or row[1]!=row[2]:
                raise Conflict('late committed judgment')
            with execution.s.work.transaction():
                execution.s.work.event('CASE_JUDGMENT_ACCEPTED', {**pending,
                    'case_node':node,'request_revision':row[1]})
        execution.pending_judgment=None

    def route_fields(self,gid):
        refs={r['stage']:json.loads(r['ref']) for r in self.db.execute(
            'SELECT h.stage,r.ref FROM head h JOIN judgment_ref r ON r.node=h.node WHERE h.goal=?',(gid,))}
        if set(refs)!=set(STAGES):raise MemoryError('current route is missing native judgment refs')
        return {'judgment_refs':refs}

    def enqueue(self,kind,aggregate,revision,payload):
        ident=digest([kind,aggregate,revision])
        old=self.db.execute('SELECT hash FROM outbox WHERE id=?',(ident,)).fetchone()
        if old and old[0]!=digest(payload):raise Conflict('outbox identity reused with different payload')
        self.db.execute('INSERT OR IGNORE INTO outbox(id,kind,aggregate_id,revision,payload,hash) VALUES(?,?,?,?,?,?)',
            (ident,kind,aggregate,revision,encoded(payload),digest(payload)))

    def route_accepted(self,gid,revision,route_id,payload,body):
        experience=payload.get('reused_experience_id')
        if experience:
            source=self.db.execute("SELECT bundle FROM knowledge WHERE id=? AND status='ACTIVE'",(experience,)).fetchone()
            if source is None:raise Conflict('source experience changed during reuse')
            if source['bundle']!=gid:self.db.execute('INSERT OR IGNORE INTO experience_dependency VALUES(?,?)',(gid,experience))
        else:self.db.execute('DELETE FROM experience_dependency WHERE question_id=?',(gid,))
        self.enqueue('ANSWER_ACCEPTED',gid,revision,{'question_id':gid,'revision':revision,
            'route_id':route_id,'run_id':self.executor.model.session.context.run_id,
            'request_id':body['request_id'],'judgment_refs':payload['judgment_refs']})

    def question_changed(self,gid):
        # Only actual judgment reuse creates dependencies; route hints do not.
        affected=self.db.execute('''WITH RECURSIVE affected(id) AS (
          SELECT ? UNION SELECT d.question_id FROM experience_dependency d
          JOIN knowledge k ON k.id=d.experience_id JOIN affected a ON k.bundle=a.id)
          SELECT id FROM affected WHERE id<>?''',(gid,gid)).fetchall()
        for row in affected:
            self.db.execute("UPDATE knowledge SET status='RETIRED' WHERE bundle=?",(row[0],))
            self.db.execute("UPDATE route SET status='RETIRED' WHERE goal=?",(row[0],))
            self.db.execute("UPDATE goal SET status='PENDING',pending='ASSESS',revision=revision+1 WHERE id=?",(row[0],))

    def experience_confirmed(self,kid,payload,principal):
        self.enqueue('EXPERIENCE_CONFIRMED',kid,payload['revision'],{
            'experience_id':kid,'experience_revision':payload['revision'],'experience_hash':digest(payload),
            'judgment_refs':payload['judgment_refs'],'owner':principal['user_id'],'team':principal['team_id']})

    def validate_response(self,result,principal,session):
        if result.get('kind')=='SOURCE_HANDOFF':
            from .source_handoff import validate
            return validate(self,result,principal,session)
        gid=result.get('goal_id')
        if gid:
            g=self.goal(gid,session)
            if not g or g['revision']!=result['revision'] or g['status']!='READY':
                raise Conflict('cached response is historical; current case changed')
            if not set(g['state']['document_ids'])<=set(principal['document_ids']):raise MemoryError('case scope denied')
            self.executor.verify(self.parts(gid)['READ']['payload'])
        return result

    def recover_requests(self):
        """Only an ownerless local session can turn RUNNING into resumable FAILED."""
        recovered=[]
        rows=list(self.db.execute("SELECT r.id,r.session,s.owner,s.team FROM request r JOIN session s ON s.id=r.session WHERE r.status='RUNNING' AND r.response IS NULL"))
        for row in rows:
            body={'session_id':row['session']};principal={'user_id':row['owner'],'team_id':row['team']}
            try:
                with self.owner(body,principal):
                    with self.transaction():
                        self.db.execute("UPDATE request SET status='FAILED' WHERE id=? AND status='RUNNING' AND response IS NULL",(row['id'],))
                        recovered.append(row['id'])
            except Conflict:continue
        return recovered

    def events_page(self,gid,principal,*,after=0,limit=50):
        r=self.db.execute('SELECT s.owner,s.team,g.state FROM goal g JOIN session s ON s.id=g.session WHERE g.id=?',(gid,)).fetchone()
        if not r or (r['owner'],r['team'])!=(principal['user_id'],principal['team_id']):raise MemoryError('question inaccessible')
        if not set(json.loads(r['state'])['document_ids'])<=set(principal['document_ids']):raise MemoryError('question document scope denied')
        limit=max(1,min(limit,100))
        rows=[dict(r) for r in self.db.execute('SELECT * FROM event WHERE goal=? AND id>? ORDER BY id LIMIT ?',
            (gid,after,limit+1))]
        return {'question_id':gid,'events':rows[:limit],'next':rows[limit-1]['id'] if len(rows)>limit else None}
