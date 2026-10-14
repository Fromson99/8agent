"""v6 compatibility adapter backed by the new v4 database generation."""
from contextlib import contextmanager
import json
from pathlib import Path
from .case_repository import CaseRepository
from .shortcut_repository import ShortcutRepository
from .corrected_memory import Conflict, MemoryError, digest, encoded


class ShortcutCases(CaseRepository):
    VERSION=4

    def __init__(self,path,executor,invoke,*,flags=None):
        super().__init__(path,executor,invoke)
        self.shortcut=ShortcutRepository(path,db=self.db)
        self.flags=flags or {};self.active_case=None;self.original_session=None;self.recorded_observations=set()

    @contextmanager
    def owner(self,body,principal):
        # The intake survives even failure to acquire a busy case lease.
        received=self.shortcut.intake(body,principal)
        self.intake_id=received['id'];self.original_session=body['session_id']
        self.active_case=received.get('investigation') or body.get('investigation_id')
        if self.active_case:
            self.shortcut.investigation(self.active_case,principal,body['session_id'])
        lock_body={**body,'session_id':self.active_case or body['session_id']}
        with super().owner(lock_body,principal): yield

    def execute(self,body,principal):
        if not getattr(self,'owner_held',False):
            with self.owner(body,principal): return self.execute(body,principal)
        self.active_principal=principal
        row=self.db.execute('SELECT * FROM sw_intake WHERE id=?',(self.intake_id,)).fetchone()
        # On a new session, connection is explicit. Within a session use its current case.
        target=row['investigation'] or body.get('investigation_id')
        if target is None:
            from .conversation_linker import propose
            proposal=propose(self.shortcut,principal,session=body['session_id'])
            links=proposal.get('investigation_ids',[])
            if len(links)==1:target=links[0]
        if target:
            case=self.shortcut.investigation(target,principal,body['session_id'])
            expected=body.get('investigation_revision')
            if expected is not None and case['revision']!=expected and row['status']!='COMPLETED': raise Conflict('stale investigation revision')
        case=self.shortcut.connect(self.intake_id,principal,investigation_id=target)
        self.active_case=case['id'];self.original_session=body['session_id']
        from .wiki_execution import WikiExecution
        self.executor.execution_class=WikiExecution
        from .procedure_memory import ProcedureMemory
        self.procedure=ProcedureMemory(self.db,principal,self.executor.binding,
            self.request_key(body,principal),self.executor.model.ensure().work.event)
        self.executor.procedure=self.procedure
        self.executor.shortcut=self.shortcut;self.executor.shortcut_flags=self.flags;self.executor.active_case=self.active_case
        # Legacy goals belong to a stable case/branch session. User-facing session remains in intake.
        branch=body.get('branch_id')
        if branch:
            r=self.db.execute('SELECT investigation FROM sw_branch WHERE id=?',(branch,)).fetchone()
            if not r or r[0]!=case['id']: raise MemoryError('branch inaccessible')
        self.internal_session=case['id']+(':'+branch if branch else '')
        translated={**body,'session_id':self.internal_session}
        self.db.execute("UPDATE sw_intake SET status='RUNNING' WHERE id=? AND status<>'COMPLETED'",(self.intake_id,))
        try:
            result=super().execute(translated,principal)
            if result.get('state'):self.sync_facts(result['goal_id'],result['state']['facts'])
            result={**result,'investigation_id':self.active_case,'investigation_revision':self.shortcut.investigation(self.active_case,principal,body['session_id'])['revision'],
                    'intake_id':self.intake_id,'original_session_id':body['session_id']}
            self.db.execute("UPDATE sw_intake SET status='COMPLETED',response=? WHERE id=?",(encoded(result),self.intake_id))
            return result
        except BaseException:
            self.db.execute("UPDATE sw_intake SET status='FAILED' WHERE id=? AND status<>'COMPLETED'",(self.intake_id,))
            raise

    def goal(self,ident,session):
        return super().goal(ident,self.internal_session if session==self.original_session else session)

    def request_key(self,body,principal):
        # Native publishing uses the original HTTP body, execute the translated body.
        return digest([principal['user_id'],principal['team_id'],getattr(self,'original_session',None) or body['session_id'],body['request_id']])

    def _execute(self,body,principal):
        context=self.context(body['session_id'],principal,body['question'])
        direct=self.direct_request(context)
        if direct is not None:return direct
        # Never replay a new-case command over an existing goal/correction.
        data={'utterance':context['utterance'],'allowed_documents':context['allowed_documents'],
              'goals':context['goals']}
        entry=getattr(self.executor,'request_entry',None)
        command=entry['command'] if entry else None
        if command is None and not context['goals'] and not self.flags.get('core_evidence_route'):
            command,_=self.procedure.lookup('command',context['utterance'],data)
        else:
            self.procedure.event('command',{'status':'DEVIATION','reason':'CURRENT_CASE_STATE_REQUIRES_DECISION',
                                          'actual_input':data})
        if command is None:
            command=super().resolve(context)
            if not context['goals'] and command['action']=='START' and not self.flags.get('core_evidence_route'):
                self.procedure.save('command',context['utterance'],data,command,decision='MODEL_AND_COMMAND_VALIDATOR')
        self.admit(command,context)
        if command['action']=='START' and context['goals'] and not body.get('investigation_id'):
            # The new-case decision is semantic, but the relink and provenance are transactional.
            with self.transaction():
                old=self.shortcut.investigation(self.active_case,principal,self.original_session)
                event=self.shortcut._event(old['scope'],old['id'],'INTAKE_REASSIGNED',
                    {'intake_id':self.intake_id,'reason':'resolver selected a distinct new question'},session=self.original_session)
                self.db.execute('UPDATE sw_session_link SET detached=? WHERE scope=? AND session=? AND detached IS NULL',
                                (event,old['scope'],self.original_session))
                self.db.execute('UPDATE sw_intake SET investigation=NULL WHERE id=?',(self.intake_id,))
                new=self.shortcut.connect(self.intake_id,principal,title=command.get('task') or body['question'])
                self.active_case=new['id'];self.internal_session=new['id'];self.executor.active_case=self.active_case
                body={**body,'session_id':new['id']}
                self.identity(new['id'],principal)
                self.db.execute('UPDATE request SET session=?,input_hash=? WHERE id=?',
                    (new['id'],digest({'body':body,'principal':principal}),self.request_key(body,principal)))
        self.resolved_command=command
        try:return super()._execute(body,principal)
        finally:self.resolved_command=None

    def resolve(self,context):
        if getattr(self,'resolved_command',None) is not None:return self.resolved_command
        return super().resolve(context)

    def candidates(self,principal,query):
        # Old USER_CONFIRMED experience cannot bypass the new verification gates.
        return []

    def context(self,session,principal,utterance):
        context=super().context(session,principal,utterance)
        if self.flags.get('hint') and principal.get('authenticated'):
            # Common curated source entries are looked up by the literal
            # current request in RECALL, without flooding the private hint menu.
            pages=self.shortcut.search(principal,limit=8,include_common=False)['pages']
            if self.executor.model.pipeline.term_agent.transport.binding['trust_zone']=='external':
                pages=[p for p in pages if not p.get('core_evidence_route') or p['core_evidence_route']['public_only']]
            # Only topic/questions, never unverified stored conclusions.
            context['legal_wiki']=[{'unit_id':p['unit_id'],'revision':p['revision'],'topic':p['topic'],'question':p['question'],
                                    'use_mode':'HINT','verification':'UNVERIFIED'} for p in pages]
        return context

    def stage_recorded(self,node,stage,payload,execution):
        super().stage_recorded(node,stage,payload,execution)
        principal=execution.principal
        if stage=='READ' and principal.get('authenticated'):
            for original in payload.get('originals',[]):
                self.shortcut.source(principal,{'document_id':original['document_id'],
                    'document_name':original.get('document_name') or original['document_id'],
                    'generation':self.executor.binding['generation'],
                    'coordinate':original.get('unit_id') or original['source_id'],
                    'text':original['text'],'version':self.executor.binding['store_sha256']})
        for observation in execution.s.work.db.execute('SELECT * FROM observation ORDER BY created_seq'):
            if observation['observation_id'] in self.recorded_observations:continue
            self.shortcut.trace(self.active_case,principal,kind='TOOL',payload={**dict(observation),
                'run_id':execution.s.context.run_id,'journal_ref':str(execution.s.work.path),
                'purpose_status':'NOT_RECORDED' if not json.loads(observation['request_json']).get('reason') else 'RECORDED'},
                documents=execution.state['document_ids'],session=self.original_session)
            self.recorded_observations.add(observation['observation_id'])
        self.shortcut.trace(self.active_case,principal,kind='JUDGMENT',
                            payload={'stage':stage,'native_ref':execution.last_judgment_ref,'payload':payload,'status':'RECORDED'},
                            documents=execution.state['document_ids'],session=self.original_session)

    def question_changed(self,gid):
        super().question_changed(gid)
        command=getattr(self,'resolved_command',None) or {}
        facts=command.get('facts')
        if 'facts' in command.get('restore_fields',[]):
            origin=next((e for e in self.events(gid) if e['id']==command['restore_event']),None)
            facts=origin['after']['facts'] if origin else facts
        if facts is not None:self.sync_facts(gid,facts)
        # Runs inside the existing state transaction; invalidation is atomic with correction.
        self.shortcut.invalidate(self.active_case)

    def route_accepted(self,gid,revision,route_id,payload,body):
        super().route_accepted(gid,revision,route_id,payload,body)
        scope=self.db.execute('SELECT scope FROM sw_investigation WHERE id=?',(self.active_case,)).fetchone()[0]
        self.shortcut._event(scope,self.active_case,'ANSWER_ACCEPTED',{'goal_id':gid,'revision':revision,'route_id':route_id,
            'judgment_refs':payload['judgment_refs']},session=self.original_session,request=body['request_id'])
        self.db.execute('UPDATE sw_investigation SET revision=revision+1 WHERE id=?',(self.active_case,))
        current=self.db.execute('SELECT revision FROM sw_investigation WHERE id=?',(self.active_case,)).fetchone()[0]
        self.shortcut.enqueue(scope,'wiki',self.active_case,current)

    def experience_confirmed(self,kid,payload,principal):
        super().experience_confirmed(kid,payload,principal)
        case=self.shortcut.investigation(self.active_case,principal,self.original_session)
        self.shortcut._event(case['scope'],self.active_case,'USER_CONFIRMED',{'experience_id':kid,'scope':'user supplied facts and response','legal_verification':'UNKNOWN'},session=self.original_session)

    def sync_facts(self,gid,facts):
        import re
        principal=self.active_principal
        intake=self.db.execute('SELECT event FROM sw_intake WHERE id=?',(self.intake_id,)).fetchone()[0]
        existing={r['predicate']:dict(r) for r in self.db.execute('SELECT f.* FROM sw_fact f JOIN sw_fact_head h ON f.id=h.id AND f.revision=h.revision WHERE f.investigation=? AND f.subject=?',(self.active_case,gid))}
        values={f['name']:f['value'] for f in facts}
        for name in sorted(set(existing)|set(values)):
            raw=values.get(name)
            value={'kind':'unknown'} if raw is None else {'kind':'string','value':raw}
            match=re.fullmatch(r'(\d+)\s*(개월|년|일)',raw or '')
            if match:value={'kind':'duration','value':int(match[1]),'unit':{'개월':'month','년':'year','일':'day'}[match[2]]}
            old=existing.get(name)
            if old and json.loads(old['value'])==value:continue
            case=self.shortcut.investigation(self.active_case,principal,self.original_session)
            self.shortcut.fact(self.active_case,principal,expected_revision=case['revision'],event=intake,
                subject=gid,predicate=name,value=value,fact_id=old['id'] if old else None,session=self.original_session)

    def recover_requests(self):
        recovered=[]
        for row in list(self.db.execute("SELECT r.id,r.session,s.owner,s.team FROM request r JOIN session s ON s.id=r.session WHERE r.status='RUNNING' AND r.response IS NULL")):
            principal={'user_id':row['owner'],'team_id':row['team']}
            try:
                with CaseRepository.owner(self,{'session_id':row['session']},principal):
                    with self.transaction():
                        self.db.execute("UPDATE request SET status='FAILED' WHERE id=? AND status='RUNNING' AND response IS NULL",(row['id'],))
                        self.db.execute("UPDATE sw_intake SET status='INTERRUPTED' WHERE investigation=? AND status='RUNNING'",(row['session'],))
                        recovered.append(row['id'])
            except Conflict:continue
        return recovered
