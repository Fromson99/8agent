"""Revision-bound shortcut authority. SQLite; no model or provider calls.

All public reads require a fresh principal. Events and knowledge bodies are
immutable; mutable heads are only pointers. ACL narrowing takes effect on reads.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from ..oracle_runtime_paths import Path
from .. import runtime_sqlite as sqlite3
import time
import uuid
from .corrected_memory import Conflict, MemoryError, digest, encoded


def now(): return datetime.now(timezone.utc).isoformat()
def uid(prefix): return prefix + uuid.uuid4().hex


SCHEMA = '''
CREATE TABLE IF NOT EXISTS sw_compile_seen(investigation TEXT NOT NULL, revision INTEGER NOT NULL, ref TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(investigation,revision,ref));
CREATE TABLE IF NOT EXISTS sw_compiled_record(investigation TEXT NOT NULL, ref TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(investigation,ref));
CREATE TABLE IF NOT EXISTS sw_compile_cursor(investigation TEXT PRIMARY KEY, revision INTEGER NOT NULL, offset INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sw_source_version(id TEXT NOT NULL, hash TEXT NOT NULL, revision TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(id,hash));
CREATE TABLE IF NOT EXISTS sw_unit_relation(source TEXT NOT NULL, revision INTEGER NOT NULL, target TEXT NOT NULL, target_revision INTEGER NOT NULL, kind TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sw_migration_identity(source_id TEXT NOT NULL, legacy_id TEXT NOT NULL, investigation TEXT NOT NULL, state_hash TEXT NOT NULL, PRIMARY KEY(source_id,legacy_id));
CREATE TABLE IF NOT EXISTS sw_scope(id TEXT PRIMARY KEY, tenant TEXT NOT NULL, owner TEXT NOT NULL, team TEXT NOT NULL, ephemeral_session TEXT, UNIQUE(tenant,owner,team,ephemeral_session));
CREATE TABLE IF NOT EXISTS sw_intake(id TEXT PRIMARY KEY, scope TEXT NOT NULL REFERENCES sw_scope(id), session TEXT NOT NULL, request TEXT NOT NULL, input_hash TEXT NOT NULL, event TEXT, investigation TEXT, status TEXT NOT NULL, response TEXT, UNIQUE(scope,session,request));
CREATE TABLE IF NOT EXISTS sw_event(id TEXT PRIMARY KEY, scope TEXT NOT NULL REFERENCES sw_scope(id), aggregate_id TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, hash TEXT NOT NULL, session TEXT, request TEXT, run TEXT, recorded_at TEXT NOT NULL, occurred_at TEXT, causation TEXT, UNIQUE(aggregate_id,seq));
CREATE INDEX IF NOT EXISTS sw_event_scope ON sw_event(scope,aggregate_id,seq);
CREATE TABLE IF NOT EXISTS sw_investigation(id TEXT PRIMARY KEY, scope TEXT NOT NULL REFERENCES sw_scope(id), title TEXT NOT NULL, revision INTEGER NOT NULL, documents TEXT NOT NULL, public_only INTEGER NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sw_session_link(id TEXT PRIMARY KEY, scope TEXT NOT NULL, session TEXT NOT NULL, investigation TEXT NOT NULL REFERENCES sw_investigation(id), event TEXT NOT NULL REFERENCES sw_event(id), detached TEXT REFERENCES sw_event(id));
CREATE TABLE IF NOT EXISTS sw_branch(id TEXT PRIMARY KEY, investigation TEXT NOT NULL REFERENCES sw_investigation(id), parent TEXT REFERENCES sw_branch(id), question TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sw_issue(id TEXT PRIMARY KEY, investigation TEXT NOT NULL REFERENCES sw_investigation(id), branch TEXT NOT NULL REFERENCES sw_branch(id), question TEXT NOT NULL, constraints_json TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sw_assignment(id TEXT PRIMARY KEY, event TEXT NOT NULL REFERENCES sw_event(id), issue TEXT NOT NULL REFERENCES sw_issue(id), start INTEGER NOT NULL, stop INTEGER NOT NULL, role TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sw_fact(id TEXT NOT NULL, revision INTEGER NOT NULL, investigation TEXT NOT NULL REFERENCES sw_investigation(id), subject TEXT NOT NULL, predicate TEXT NOT NULL, value TEXT NOT NULL, valid_time TEXT NOT NULL, event TEXT NOT NULL REFERENCES sw_event(id), supersedes INTEGER, status TEXT NOT NULL, PRIMARY KEY(id,revision));
CREATE TABLE IF NOT EXISTS sw_fact_head(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, FOREIGN KEY(id,revision) REFERENCES sw_fact(id,revision));
CREATE TABLE IF NOT EXISTS sw_relation(id TEXT NOT NULL, revision INTEGER NOT NULL, scope TEXT NOT NULL, source TEXT NOT NULL, target TEXT NOT NULL, kind TEXT NOT NULL, reason TEXT NOT NULL, event TEXT NOT NULL, status TEXT NOT NULL, PRIMARY KEY(id,revision));
CREATE TABLE IF NOT EXISTS sw_artifact(id TEXT PRIMARY KEY, scope TEXT NOT NULL REFERENCES sw_scope(id), hash TEXT NOT NULL, bytes INTEGER NOT NULL, relative_path TEXT NOT NULL, documents TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sw_trace(id TEXT PRIMARY KEY, investigation TEXT NOT NULL REFERENCES sw_investigation(id), kind TEXT NOT NULL, artifact TEXT NOT NULL REFERENCES sw_artifact(id), payload TEXT NOT NULL, hash TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sw_unit(id TEXT PRIMARY KEY, scope TEXT NOT NULL REFERENCES sw_scope(id), head INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sw_knowledge(unit TEXT NOT NULL REFERENCES sw_unit(id), revision INTEGER NOT NULL, build TEXT NOT NULL, payload TEXT NOT NULL, hash TEXT NOT NULL, completeness TEXT NOT NULL, PRIMARY KEY(unit,revision));
CREATE TABLE IF NOT EXISTS sw_lifecycle(unit TEXT NOT NULL, revision INTEGER NOT NULL, status TEXT NOT NULL, PRIMARY KEY(unit,revision), FOREIGN KEY(unit,revision) REFERENCES sw_knowledge(unit,revision));
CREATE TABLE IF NOT EXISTS sw_member(unit TEXT NOT NULL, revision INTEGER NOT NULL, ref TEXT NOT NULL, payload TEXT NOT NULL, FOREIGN KEY(unit,revision) REFERENCES sw_knowledge(unit,revision));
CREATE TABLE IF NOT EXISTS sw_claim(unit TEXT NOT NULL, revision INTEGER NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(unit,revision,id), FOREIGN KEY(unit,revision) REFERENCES sw_knowledge(unit,revision));
CREATE TABLE IF NOT EXISTS sw_procedure(unit TEXT NOT NULL, revision INTEGER NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(unit,revision,id), FOREIGN KEY(unit,revision) REFERENCES sw_knowledge(unit,revision));
CREATE TABLE IF NOT EXISTS sw_dependency(unit TEXT NOT NULL, revision INTEGER NOT NULL, ref TEXT NOT NULL, version TEXT NOT NULL, hash TEXT NOT NULL, role TEXT NOT NULL, FOREIGN KEY(unit,revision) REFERENCES sw_knowledge(unit,revision));
CREATE INDEX IF NOT EXISTS sw_dependency_ref ON sw_dependency(ref,version);
CREATE TABLE IF NOT EXISTS sw_source(id TEXT PRIMARY KEY, scope TEXT NOT NULL, revision TEXT NOT NULL, hash TEXT NOT NULL, payload TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sw_verification(id TEXT PRIMARY KEY, scope TEXT NOT NULL, unit TEXT NOT NULL, revision INTEGER NOT NULL, target_hash TEXT NOT NULL, kind TEXT NOT NULL, result TEXT NOT NULL, policy TEXT NOT NULL, verifier TEXT NOT NULL, evidence TEXT NOT NULL, expires REAL NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(unit,revision) REFERENCES sw_knowledge(unit,revision));
CREATE TABLE IF NOT EXISTS sw_reuse(id TEXT PRIMARY KEY, scope TEXT NOT NULL, request TEXT NOT NULL, unit TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sw_queue(id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL, consumer TEXT NOT NULL, aggregate_id TEXT NOT NULL, revision INTEGER NOT NULL, dedup TEXT NOT NULL UNIQUE, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, lease TEXT, lease_until REAL, next_attempt REAL NOT NULL DEFAULT 0, error TEXT);
CREATE INDEX IF NOT EXISTS sw_queue_ready ON sw_queue(consumer,status,next_attempt);
CREATE TABLE IF NOT EXISTS sw_cursor(consumer TEXT PRIMARY KEY, watermark INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sw_build(id TEXT PRIMARY KEY, scope TEXT NOT NULL, payload TEXT NOT NULL, hash TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sw_import(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sw_legacy(source TEXT NOT NULL, kind TEXT NOT NULL, original_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(source,kind,original_id));
'''


class ShortcutRepository:
    VERSION = 4

    def __init__(self, path, *, db=None):
        self.path = Path(path).resolve()
        from ..state_sqlite import connect, configure
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.owns_db = db is None
        self.db = connect(self.path) if db is None else db
        if db is not None: configure(db, self.path, borrowed=True)
        from .journal_storage import row
        self.db.row_factory = row
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 4):
            if self.owns_db: self.db.close()
            raise MemoryError('explicit new-generation migration required')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript(SCHEMA)
        for table in ('sw_source_version','sw_unit_relation','sw_event','sw_fact','sw_knowledge','sw_member','sw_claim','sw_procedure','sw_dependency','sw_verification','sw_reuse','sw_trace','sw_legacy','sw_import'):
            for operation in ('UPDATE','DELETE'):
                self.db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'immutable record'); END")
        self.db.execute('PRAGMA user_version=4')
        self.path.chmod(0o600)
        self.artifacts = self.path.parent / 'artifacts'

    def close(self):
        if self.owns_db: self.db.close()

    @contextmanager
    def transaction(self):
        nested = self.db.in_transaction
        if not nested: self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            if not nested: self.db.execute('COMMIT')
        except BaseException:
            if not nested: self.db.execute('ROLLBACK')
            raise

    def scope(self, principal, session=None, *, create=False):
        from lawrag.pipeline.shortcut_package import COMMON_OWNER, COMMON_TEAM, is_common_operator
        if (principal.get('user_id'), principal.get('team_id')) == (COMMON_OWNER, COMMON_TEAM) and not is_common_operator(principal):
            raise MemoryError('reserved catalogue identity requires filesystem operator')
        if principal.get('_ad_scope'):
            row=self.db.execute('SELECT owner,team FROM sw_scope WHERE id=?',(principal['_ad_scope'],)).fetchone()
            if not row or tuple(row)!=(principal.get('user_id'),principal.get('team_id')):raise MemoryError('AD scope mismatch')
            return principal['_ad_scope']
        if not principal.get('user_id') or not principal.get('team_id'):
            raise MemoryError('trusted principal required')
        ephemeral = None if principal.get('authenticated') else session
        if not principal.get('authenticated') and not session:
            raise MemoryError('anonymous cross-session access denied')
        values = [principal.get('tenant_id', principal['team_id']), principal['user_id'], principal['team_id'], ephemeral]
        ident = 'scope:' + digest(values)
        if create: self.db.execute('INSERT OR IGNORE INTO sw_scope VALUES(?,?,?,?,?)', (ident,*values))
        return ident

    def knowledge_scopes(self, principal, *, include_common=True):
        from lawrag.pipeline.shortcut_package import common_scope_id
        own = self.scope(principal)
        scopes = [own]
        if include_common and principal.get('authenticated') and common_scope_id() != own:
            scopes.append(common_scope_id())
        return scopes

    def _event(self, scope, aggregate, kind, payload, *, session=None, request=None, run=None, causation=None, occurred_at=None):
        seq = self.db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM sw_event WHERE aggregate_id=?',(aggregate,)).fetchone()[0]
        ident = uid('ev:')
        self.db.execute('INSERT INTO sw_event VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (ident,scope,aggregate,seq,kind,encoded(payload),digest(payload),session,request,run,now(),occurred_at,causation))
        return ident

    def enqueue(self, scope, consumer, aggregate, revision):
        if consumer == 'wiki':
            from .successful_answer import eligible
            if not eligible(self,aggregate):return
        if consumer == 'projection':
            from .wiki_recall import index_unit
            index_unit(self, aggregate, revision)
        self.db.execute("INSERT OR IGNORE INTO sw_queue(scope,consumer,aggregate_id,revision,dedup,status) VALUES(?,?,?,?,?,'PENDING')",
                        (scope,consumer,aggregate,revision,digest([scope,consumer,aggregate,revision])))

    def intake(self, body, principal):
        with self.transaction():
            scope = self.scope(principal,body['session_id'],create=True)
            ident = digest([scope,body['session_id'],body['request_id']])
            fingerprint = digest(body)
            row = self.db.execute('SELECT * FROM sw_intake WHERE id=?',(ident,)).fetchone()
            if row:
                if row['input_hash'] != fingerprint: raise Conflict('request key reused with different body')
                return dict(row)
            event = self._event(scope,'intake:'+digest([scope,body['session_id']]),'UTTERANCE_RECEIVED',
                                {'text':body['question'],'documents':body.get('document_ids',[]),
                                 'public_question':body.get('public_question') is True},
                                session=body['session_id'],request=body['request_id'])
            self.db.execute("INSERT INTO sw_intake VALUES(?,?,?,?,?,?,NULL,'RECEIVED',NULL)",
                            (ident,scope,body['session_id'],body['request_id'],fingerprint,event))
        return dict(self.db.execute('SELECT * FROM sw_intake WHERE id=?',(ident,)).fetchone())

    def investigation(self, ident, principal, session=None):
        from ..ad_store import excluded
        if excluded(self.db,'shortcut',ident):raise MemoryError('shortcut is in trash or rejected')
        row=self.db.execute('SELECT * FROM sw_investigation WHERE id=? AND scope=?',
                            (ident,self.scope(principal,session))).fetchone()
        if not row: raise MemoryError('record inaccessible')
        value=dict(row);value['documents']=json.loads(row['documents'])
        if not set(value['documents']) <= set(principal['document_ids']): raise MemoryError('record inaccessible')
        return value

    def connect(self, intake_id, principal, *, investigation_id=None, title=None):
        with self.transaction():
            row=self.db.execute('SELECT * FROM sw_intake WHERE id=?',(intake_id,)).fetchone()
            if not row or row['scope']!=self.scope(principal,row['session']): raise MemoryError('record inaccessible')
            if row['investigation']:
                if investigation_id and investigation_id!=row['investigation']: raise Conflict('request already assigned')
                return self.investigation(row['investigation'],principal,row['session'])
            event=self.event(row['event'],principal,row['session'])
            if investigation_id:
                if not principal.get('authenticated'): raise MemoryError('explicit cross-session connection requires authentication')
                case=self.investigation(investigation_id,principal,row['session'])
                if not set(event['payload']['documents'])<=set(case['documents']): raise MemoryError('case document expansion requires explicit review')
            else:
                investigation_id=uid('inv:')
                docs=event['payload']['documents']
                if not set(docs)<=set(principal['document_ids']): raise MemoryError('document scope denied')
                self.db.execute("INSERT INTO sw_investigation VALUES(?,?,?,?,?,?,?)",
                                (investigation_id,row['scope'],title or event['payload']['text'][:200],0,encoded(docs),int(event['payload']['public_question']),'OPEN'))
            connected=self._event(row['scope'],investigation_id,'SESSION_CONNECTED',{'intake_id':intake_id,'source_event':row['event']},session=row['session'],request=row['request'])
            self.db.execute('INSERT INTO sw_session_link VALUES(?,?,?,?,?,NULL)',(uid('link:'),row['scope'],row['session'],investigation_id,connected))
            self.db.execute('UPDATE sw_intake SET investigation=? WHERE id=?',(investigation_id,intake_id))
            self.db.execute('UPDATE sw_investigation SET revision=revision+1,public_only=MIN(public_only,?) WHERE id=?',(int(event['payload']['public_question']),investigation_id))
            case=self.investigation(investigation_id,principal,row['session'])
            self.enqueue(row['scope'],'wiki',investigation_id,case['revision'])
            return case

    def advance(self, ident, principal, expected_revision, kind, payload, *, session=None, causation=None):
        with self.transaction():
            case=self.investigation(ident,principal,session)
            if case['revision']!=expected_revision: raise Conflict('stale investigation revision')
            event=self._event(case['scope'],ident,kind,payload,session=session,causation=causation)
            self.db.execute('UPDATE sw_investigation SET revision=revision+1 WHERE id=? AND revision=?',(ident,expected_revision))
            self.enqueue(case['scope'],'wiki',ident,expected_revision+1)
            return event

    def event(self, ident, principal, session=None):
        row=self.db.execute('SELECT * FROM sw_event WHERE id=? AND scope=?',(ident,self.scope(principal,session))).fetchone()
        if not row: raise MemoryError('record inaccessible')
        result=dict(row);result['payload']=json.loads(row['payload'])
        if digest(result['payload'])!=row['hash']: raise MemoryError('event hash mismatch')
        if row['aggregate_id'].startswith('inv:'): self.investigation(row['aggregate_id'],principal,session)
        if not set(result['payload'].get('documents',[]))<=set(principal['document_ids']): raise MemoryError('record inaccessible')
        return result

    def history(self, ident, principal, *, after=0, limit=50, session=None):
        case=self.investigation(ident,principal,session);limit=max(1,min(int(limit),100))
        rows=list(self.db.execute('SELECT id,seq FROM sw_event WHERE aggregate_id=? AND scope=? AND seq>? ORDER BY seq LIMIT ?',
                                 (ident,case['scope'],int(after),limit+1)))
        return {'events':[self.event(r['id'],principal,session) for r in rows[:limit]],'next':rows[limit-1]['seq'] if len(rows)>limit else None}

    def cases(self, principal, *, after='', limit=50):
        scope=self.scope(principal);values=[];limit=max(1,min(int(limit),100))
        for row in self.db.execute('SELECT id FROM sw_investigation WHERE scope=? AND id>? ORDER BY id',(scope,after)):
            try: values.append(self.investigation(row['id'],principal))
            except MemoryError: continue
            if len(values)>limit: break
        return {'investigations':values[:limit],'next':values[limit-1]['id'] if len(values)>limit else None}

    def issue(self, ident, principal, question, *, branch=None, parent=None, constraints=None, session=None):
        with self.transaction():
            self.investigation(ident,principal,session)
            if parent:
                row=self.db.execute('SELECT investigation FROM sw_branch WHERE id=?',(parent,)).fetchone()
                if not row or row[0]!=ident: raise MemoryError('branch inaccessible')
            if branch:
                row=self.db.execute('SELECT investigation FROM sw_branch WHERE id=?',(branch,)).fetchone()
                if not row or row[0]!=ident: raise MemoryError('branch inaccessible')
            else:
                branch=uid('branch:');self.db.execute('INSERT INTO sw_branch VALUES(?,?,?,?)',(branch,ident,parent,question))
            issue=uid('issue:')
            self.db.execute("INSERT INTO sw_issue VALUES(?,?,?,?,?,'OPEN')",(issue,ident,branch,question,encoded(constraints or {})))
            return issue

    def assign(self, event, issue, principal, start, stop, *, role='CONTEXT', reason='', session=None):
        with self.transaction():
            e=self.event(event,principal,session)
            target=self.db.execute('SELECT investigation FROM sw_issue WHERE id=?',(issue,)).fetchone()
            if not target: raise MemoryError('issue inaccessible')
            case=self.investigation(target[0],principal,session)
            linked=self.db.execute('SELECT 1 FROM sw_intake WHERE event=? AND investigation=?',(event,case['id'])).fetchone()
            if not linked and e['aggregate_id']!=case['id']: raise MemoryError('event not connected to issue case')
            text=e['payload'].get('text','')
            if type(start) is not int or type(stop) is not int or not 0<=start<stop<=len(text): raise MemoryError('invalid exact span')
            overlaps=self.db.execute('SELECT 1 FROM sw_assignment WHERE event=? AND start<? AND stop>?',(event,stop,start)).fetchone()
            if overlaps and not reason: raise MemoryError('shared span needs a reason')
            ident=uid('assignment:')
            self.db.execute("INSERT INTO sw_assignment VALUES(?,?,?,?,?,?,?,'ASSERTED')",(ident,event,issue,start,stop,role,reason))
            return ident

    def fact(self, ident, principal, *, expected_revision, event, subject, predicate, value, valid_time=None, fact_id=None, restore_revision=None, session=None):
        if value.get('kind') not in {'string','number','boolean','date','duration','unknown'}: raise MemoryError('typed fact required')
        if value['kind']=='duration' and value.get('unit') not in {'day','month','year'}: raise MemoryError('duration unit required')
        if value['kind'] in {'number','duration'} and type(value.get('value')) not in (int,float): raise MemoryError('numeric fact required')
        if value['kind']=='boolean' and type(value.get('value')) is not bool: raise MemoryError('boolean fact required')
        with self.transaction():
            source=self.event(event,principal,session)
            case=self.investigation(ident,principal,session)
            if source['aggregate_id']!=ident and not self.db.execute('SELECT 1 FROM sw_intake WHERE event=? AND investigation=?',(event,ident)).fetchone(): raise MemoryError('fact assertion belongs to another case')
            previous=None
            if fact_id:
                previous=self.db.execute('SELECT f.* FROM sw_fact f JOIN sw_fact_head h ON f.id=h.id AND f.revision=h.revision WHERE f.id=?',(fact_id,)).fetchone()
                if not previous or (previous['investigation'],previous['subject'],previous['predicate'])!=(ident,subject,predicate): raise MemoryError('fact scope mismatch')
            else: fact_id=uid('fact:')
            if restore_revision is not None:
                origin=self.db.execute('SELECT * FROM sw_fact WHERE id=? AND revision=?',(fact_id,restore_revision)).fetchone()
                if not origin: raise MemoryError('original fact not found')
                value=json.loads(origin['value']);valid_time=json.loads(origin['valid_time'])
            revision=previous['revision']+1 if previous else 1
            correction=self.advance(ident,principal,expected_revision,'FACT_RESTORED' if restore_revision else 'FACT_CORRECTED' if previous else 'FACT_ASSERTED',
                                    {'fact_id':fact_id,'revision':revision,'value':value,'restored_from':restore_revision},session=session,causation=event)
            self.db.execute('INSERT INTO sw_fact VALUES(?,?,?,?,?,?,?,?,?,?)',(fact_id,revision,ident,subject,predicate,encoded(value),encoded(valid_time or {}),correction,previous['revision'] if previous else None,'USER_ASSERTED'))
            self.db.execute('INSERT INTO sw_fact_head VALUES(?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision',(fact_id,revision))
            self.invalidate(fact_id)
            return {'id':fact_id,'revision':revision,'event':correction}

    def invalidate(self, ref):
        # Query gates independently inspect dependencies, so lag cannot reopen a head.
        self.db.execute("UPDATE sw_lifecycle SET status='STALE' WHERE (unit,revision) IN (SELECT unit,revision FROM sw_dependency WHERE ref=? AND role NOT IN ('HINT','ACL'))",(ref,))

    def requeue_dependents(self, ref):
        for row in self.db.execute("SELECT DISTINCT d2.ref FROM sw_dependency d JOIN sw_dependency d2 ON d.unit=d2.unit AND d.revision=d2.revision WHERE d.ref=? AND d2.ref LIKE 'inv:%'",(ref,)):
            case=self.db.execute('SELECT scope,revision FROM sw_investigation WHERE id=?',(row[0],)).fetchone()
            if case:
                # A fresh source change must not collide with a completed wiki job.
                self.db.execute("UPDATE sw_queue SET status='PENDING',attempts=0,next_attempt=0,error=NULL WHERE consumer='wiki' AND aggregate_id=? AND status IN ('DONE','QUARANTINED')",(row[0],))
                self.enqueue(case['scope'],'wiki',row[0],case['revision'])

    def relation(self, source, target, principal, *, kind, reason, event, relation_id=None):
        with self.transaction():
            a=self.investigation(source,principal);self.investigation(target,principal)
            e=self.event(event,principal)
            if e['aggregate_id'] not in (source,target): raise MemoryError('relation evidence not in either case')
            if kind not in {'CONTINUES','SAME_TOPIC','CONTRADICTS','LINK_RETRACTED'} or not reason: raise MemoryError('typed relation and reason required')
            revision=1
            if relation_id:
                old=self.db.execute('SELECT * FROM sw_relation WHERE id=? ORDER BY revision DESC LIMIT 1',(relation_id,)).fetchone()
                if not old or (old['scope'],old['source'],old['target'])!=(a['scope'],source,target): raise MemoryError('relation inaccessible')
                revision=old['revision']+1
            else: relation_id=uid('rel:')
            self.db.execute('INSERT INTO sw_relation VALUES(?,?,?,?,?,?,?,?,?)',(relation_id,revision,a['scope'],source,target,kind,reason,event,'RETRACTED' if kind=='LINK_RETRACTED' else 'ASSERTED'))
            if kind=='LINK_RETRACTED': self.invalidate(relation_id)
            return relation_id

    def artifact(self, data, principal, *, documents=(), session=None):
        if not isinstance(data,bytes): data=encoded(data).encode()
        if not set(documents)<=set(principal['document_ids']): raise MemoryError('artifact scope denied')
        scope=self.scope(principal,session,create=True);sha=hashlib.sha256(data).hexdigest();ident=digest([scope,sha,sorted(documents)])
        relative=Path(scope.split(':')[1])/sha
        path=self.artifacts/relative;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        from ..oracle_runtime_paths import virtual, write_file
        try:
            if virtual(path):
                write_file(path, data, exclusive=True)
            else:
                with path.open('xb') as f: f.write(data);f.flush();os.fsync(f.fileno())
                path.chmod(0o600)
                fd=os.open(path.parent,os.O_RDONLY)
                try: os.fsync(fd)
                finally: os.close(fd)
        except FileExistsError:
            if path.read_bytes()!=data: raise MemoryError('artifact hash collision')
        self.db.execute('INSERT OR IGNORE INTO sw_artifact VALUES(?,?,?,?,?,?)',(ident,scope,sha,len(data),str(relative),encoded(sorted(documents))))
        return ident

    def read_artifact(self, ident, principal, session=None):
        row=self.db.execute('SELECT * FROM sw_artifact WHERE id=? AND scope=?',(ident,self.scope(principal,session))).fetchone()
        if not row or not set(json.loads(row['documents']))<=set(principal['document_ids']): raise MemoryError('artifact inaccessible')
        path=(self.artifacts/row['relative_path']).resolve()
        if not path.is_relative_to(self.artifacts.resolve()): raise MemoryError('artifact path escaped')
        data=path.read_bytes()
        if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['hash']: raise MemoryError('artifact damaged')
        return data

    def trace(self, ident, principal, *, kind, payload, documents=(), session=None):
        with self.transaction():
            self.investigation(ident,principal,session)
            artifact=self.artifact(payload,principal,documents=documents,session=session)
            ref=uid('trace:')
            self.db.execute('INSERT INTO sw_trace VALUES(?,?,?,?,?,?,?)',(ref,ident,kind,artifact,encoded(payload),digest(payload),payload.get('status','RECORDED')))
            return ref

    def source(self, principal, payload):
        """Trusted source adapter supplies verified bytes, never a compiler claim."""
        required={'document_id','document_name','generation','coordinate','text','version'}
        if not required<=payload.keys() or payload['document_id'] not in principal['document_ids']: raise MemoryError('source binding incomplete')
        scope=self.scope(principal,create=True);ident='source:'+digest([scope,payload['document_id'],payload['coordinate']])
        with self.transaction():
            self.db.execute('INSERT OR IGNORE INTO sw_source_version VALUES(?,?,?,?)',(ident,digest(payload),str(payload['version']),encoded(payload)))
            old=self.db.execute('SELECT hash,revoked FROM sw_source WHERE id=?',(ident,)).fetchone()
            self.db.execute('INSERT INTO sw_source VALUES(?,?,?,?,?,0) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,hash=excluded.hash,payload=excluded.payload,revoked=0',
                            (ident,scope,str(payload['version']),digest(payload),encoded(payload)))
            if old and (old['hash']!=digest(payload) or old['revoked']):
                self.invalidate(ident);self.requeue_dependents(ident)
        return ident

    def revoke_source(self, ident, principal):
        with self.transaction():
            cursor=self.db.execute('UPDATE sw_source SET revoked=1 WHERE id=? AND scope=?',(ident,self.scope(principal)))
            if cursor.rowcount!=1: raise MemoryError('source inaccessible')
            self.invalidate(ident);self.requeue_dependents(ident)

    def snapshot(self, ident, principal):
        # Consistent read transaction; no lock survives model invocation.
        with self.transaction():
            case=self.investigation(ident,principal)
            events=[]
            ids={r[0] for r in self.db.execute('SELECT id FROM sw_event WHERE aggregate_id=?',(ident,))}
            ids.update(r[0] for r in self.db.execute('SELECT event FROM sw_intake WHERE investigation=?',(ident,)))
            for event in sorted(ids): events.append(self.event(event,principal))
            facts=[dict(r) for r in self.db.execute('SELECT f.* FROM sw_fact f JOIN sw_fact_head h ON f.id=h.id AND f.revision=h.revision WHERE investigation=?',(ident,))]
            traces=[dict(r) for r in self.db.execute('SELECT * FROM sw_trace WHERE investigation=?',(ident,))]
            for trace in traces: self.read_artifact(trace['artifact'],principal)
            sources=[{**dict(r),'payload':json.loads(r['payload'])} for r in self.db.execute('SELECT * FROM sw_source WHERE scope=? AND revoked=0',(case['scope'],)) if json.loads(r['payload'])['document_id'] in case['documents']]
            value={'case':case,'events':events,'facts':facts,'traces':traces,'sources':sources,
                   'issues':[dict(r) for r in self.db.execute('SELECT * FROM sw_issue WHERE investigation=?',(ident,))]}
            value['hash']=digest(value)
            return value

    def snapshot_page(self, ident, principal, *, offset=0, limit=64, max_bytes=120000):
        """Exact, bounded DB records. No summary replaces an original record.

        Oversized single records fail visibly for operator segmentation. Partial
        history is marked, so a page can never authorize a completed judgment.
        """
        if type(offset) is not int or offset<0:raise MemoryError('invalid compiler cursor')
        limit=max(1,min(int(limit),128))
        with self.transaction():
            case=self.investigation(ident,principal)
            queries=[('events',"SELECT e.id FROM sw_event e WHERE (e.aggregate_id=? OR e.id IN (SELECT event FROM sw_intake WHERE investigation=?)) AND NOT EXISTS (SELECT 1 FROM sw_compiled_record c WHERE c.investigation=? AND c.ref=e.id AND c.hash=e.hash) ORDER BY e.rowid",(ident,ident,ident)),
                ('facts',"SELECT f.* FROM sw_fact f JOIN sw_fact_head h ON f.id=h.id AND f.revision=h.revision WHERE f.investigation=? ORDER BY f.id",(ident,)),
                ('traces',"SELECT t.* FROM sw_trace t WHERE investigation=? AND NOT EXISTS (SELECT 1 FROM sw_compiled_record c WHERE c.investigation=t.investigation AND c.ref=t.id AND c.hash=t.hash) ORDER BY t.rowid",(ident,)),
                ('sources',"SELECT * FROM sw_source WHERE scope=? AND revoked=0 AND json_extract(payload,'$.document_id') IN (SELECT value FROM json_each(?)) ORDER BY id",(case['scope'],encoded(case['documents'])))]
            from ..ad_store import table_exists
            if table_exists(self.db,'ad_object'):
                filtered=[]
                for group,q,args in queries:
                    kind={'events':'event','facts':'fact','traces':'trace','sources':'source'}[group]
                    q="SELECT original.* FROM ("+q+") original WHERE NOT EXISTS(SELECT 1 FROM ad_object a WHERE a.kind='"+kind+"' AND a.entity=original.id AND (a.trashed=1 OR a.review='REJECTED'))"
                    filtered.append((group,q,args))
                queries=filtered
            counts=[self.db.execute('SELECT count(*) FROM ('+q+')',args).fetchone()[0] for _,q,args in queries]
            total=sum(counts);seen=0;used=0;n=0;value={'case':case,'events':[],'facts':[],'traces':[],'sources':[],'issues':[]}
            for (group,q,args),count in zip(queries,counts):
                start=max(0,offset-seen);seen+=count
                if start>=count or n>=limit:continue
                for row in self.db.execute(q+' LIMIT ? OFFSET ?',(*args,limit-n,start)):
                    item=self.event(row['id'],principal) if group=='events' else dict(row)
                    if group=='sources':item['payload']=json.loads(item['payload'])
                    size=len(encoded(item).encode())
                    if size>max_bytes and not n:raise MemoryError('COMPILER_RECORD_EXCEEDS_BUDGET: exact record '+item['id'])
                    if used+size>max_bytes:break
                    if group=='traces':self.read_artifact(item['artifact'],principal)
                    value[group].append(item);n+=1;used+=size
                if n and used+size>max_bytes:break
            value['window']={'offset':offset,'next':offset+n if offset+n<total else None,'total_records':total,'partial_context':offset>0 or n<total}
            value['prior_knowledge']=self.prior_knowledge(ident,principal)
            value['hash']=digest(value)
            return value

    def compiler_input(self, ident, principal):
        from .successful_answer import require
        require(self,ident)
        case=self.investigation(ident,principal)
        row=self.db.execute('SELECT revision,offset FROM sw_compile_cursor WHERE investigation=?',(ident,)).fetchone()
        offset=row['offset'] if row and row['revision']==case['revision'] else 0
        return self.snapshot_page(ident,principal,offset=offset)

    def prior_knowledge(self, ident, principal, limit=16):
        case=self.investigation(ident,principal);values=[]
        for row in self.db.execute("SELECT DISTINCT k.unit,k.revision,k.payload,k.hash,l.status FROM sw_knowledge k JOIN sw_unit u ON u.id=k.unit AND u.head=k.revision JOIN sw_lifecycle l ON l.unit=k.unit AND l.revision=k.revision JOIN sw_dependency d ON d.unit=k.unit AND d.revision=k.revision WHERE d.ref=? AND u.scope=? ORDER BY k.unit LIMIT ?",(ident,case['scope'],limit)):
            value=json.loads(row['payload'])
            if not set(value['documents'])<=set(principal['document_ids']):continue
            values.append({'unit_id':row['unit'],'revision':row['revision'],'hash':row['hash'],'topic':value['topic'],'question':value['question'],'status':row['status'],'unresolved':value['unresolved'],'role':'COMPARISON_ONLY_NOT_CURRENT_TRUTH'})
        return values

    def related_inputs(self, snapshot, principal, *, limit=3):
        """Only explicit live case relations select companions; no name guesses."""
        result=[snapshot];ident=snapshot['case']['id'];scope=snapshot['case']['scope']
        rows=self.db.execute("SELECT r.* FROM sw_relation r WHERE scope=? AND (source=? OR target=?) AND revision=(SELECT max(x.revision) FROM sw_relation x WHERE x.id=r.id) AND status='ASSERTED' AND kind IN ('CONTINUES','SAME_TOPIC') ORDER BY id",(scope,ident,ident))
        for row in rows:
            if len(result)>=limit:break
            target=row['target'] if row['source']==ident else row['source']
            if target in {x['case']['id'] for x in result}:continue
            try:value=self.compiler_input(target,principal)
            except MemoryError:continue
            value['relation_binding']={'id':row['id'],'revision':row['revision'],'hash':digest(dict(row))}
            value['hash']=digest({k:v for k,v in value.items() if k!='hash'});result.append(value)
        return result

    def compiler_progress(self, snapshot):
        window=snapshot.get('window',{});offset=window.get('next');ident=snapshot['case']['id']
        for record in snapshot['events']+snapshot['traces']:
            self.db.execute('INSERT INTO sw_compile_seen VALUES(?,?,?,?) ON CONFLICT(investigation,revision,ref) DO UPDATE SET hash=excluded.hash',(ident,snapshot['case']['revision'],record['id'],record['hash']))
        if offset is not None:
            self.db.execute('INSERT INTO sw_compile_cursor VALUES(?,?,?) ON CONFLICT(investigation) DO UPDATE SET revision=excluded.revision,offset=excluded.offset',
                (ident,snapshot['case']['revision'],offset))
        else:
            # Commit only records actually admitted across this revision's pages.
            # A trace arriving during the model call is never silently consumed.
            for row in self.db.execute('SELECT ref,hash FROM sw_compile_seen WHERE investigation=? AND revision=?',(ident,snapshot['case']['revision'])):
                self.db.execute('INSERT INTO sw_compiled_record VALUES(?,?,?) ON CONFLICT(investigation,ref) DO UPDATE SET hash=excluded.hash',(ident,row['ref'],row['hash']))
            self.db.execute('DELETE FROM sw_compile_seen WHERE investigation=?',(ident,))
            self.db.execute('DELETE FROM sw_compile_cursor WHERE investigation=?',(ident,))
        pending_trace=self.db.execute('SELECT 1 FROM sw_trace t WHERE investigation=? AND NOT EXISTS (SELECT 1 FROM sw_compiled_record c WHERE c.investigation=t.investigation AND c.ref=t.id AND c.hash=t.hash) LIMIT 1',(ident,)).fetchone()
        return offset is None and not pending_trace

    def current(self, unit, revision, principal, *, allow_draft=False, _seen=None):
        from ..ad_store import excluded,features
        if excluded(self.db,'wiki',unit,revision=revision) or not features(self.db,principal['team_id'])['wiki']:raise MemoryError('wiki disabled, rejected or in trash')
        seen=set(_seen or ())
        if (unit,revision) in seen:raise MemoryError('cyclic knowledge dependency')
        seen.add((unit,revision))
        scopes=self.knowledge_scopes(principal)
        slots=','.join('?' for _ in scopes)
        row=self.db.execute(f'''SELECT k.*,u.scope,l.status FROM sw_knowledge k JOIN sw_unit u ON u.id=k.unit
            JOIN sw_lifecycle l ON l.unit=k.unit AND l.revision=k.revision WHERE k.unit=? AND k.revision=? AND u.scope IN ({slots})''',
                            (unit,revision,*scopes)).fetchone()
        if not row or row['status'] not in (('PUBLISHED','DRAFT') if allow_draft else ('PUBLISHED',)): raise MemoryError('knowledge inaccessible or stale')
        value=json.loads(row['payload'])
        if digest(value)!=row['hash']: raise MemoryError('knowledge hash mismatch')
        from lawrag.pipeline.shortcut_package import common_scope_id, CONTRACT
        if row['scope']==common_scope_id() and (value.get('visibility')!='COMMON'
                or value.get('core_evidence_route',{}).get('contract')!=CONTRACT):
            raise MemoryError('only explicitly curated source routes are common')
        from .successful_answer import check_knowledge
        check_knowledge(self,value)
        if value.get('core_evidence_route'):
            from .core_evidence_route import current
            current(self,value,principal)
        if not set(value['documents'])<=set(principal['document_ids']): raise MemoryError('knowledge inaccessible')
        for member in value['members']:
            prefix={'ev':'event','trace':'trace','fact':'fact','inv':'shortcut'}.get(member['ref'].split(':',1)[0])
            if prefix and excluded(self.db,prefix,member['ref']):raise MemoryError('wiki member is excluded')
        for dep in self.db.execute('SELECT * FROM sw_dependency WHERE unit=? AND revision=?',(unit,revision)):
            ref=dep['ref'];current=None
            if ref.startswith('inv:'):
                c=self.investigation(ref,principal)
                if dep['role']=='ACL':continue
                current=(str(c['revision']),digest(c))
            elif ref.startswith('fact:'):
                r=self.db.execute('SELECT f.* FROM sw_fact f JOIN sw_fact_head h ON f.id=h.id AND f.revision=h.revision WHERE f.id=?',(ref,)).fetchone()
                if r: self.investigation(r['investigation'],principal);current=(str(r['revision']),digest(dict(r)))
            elif ref.startswith('source:'):
                r=self.db.execute('SELECT * FROM sw_source WHERE id=? AND scope=? AND revoked=0',(ref,row['scope'])).fetchone()
                if r and json.loads(r['payload'])['document_id'] in principal['document_ids']: current=(r['revision'],r['hash'])
            if current!=(dep['version'],dep['hash']): raise MemoryError('knowledge dependency changed')
        for relation in self.db.execute("SELECT * FROM sw_unit_relation WHERE source=? AND revision=? AND kind='DEPENDS_ON'",(unit,revision)):
            self.current(relation['target'],relation['target_revision'],principal,allow_draft=allow_draft,_seen=seen)
        for member in value['members']:
            if member['ref'].startswith('trace:'):
                t=self.db.execute('SELECT * FROM sw_trace WHERE id=?',(member['ref'],)).fetchone()
                if not t: raise MemoryError('trace missing')
                self.investigation(t['investigation'],principal);self.read_artifact(t['artifact'],principal)
        return {**value,'unit_id':unit,'revision':revision,'hash':row['hash'],'lifecycle':row['status']}

    def search(self, principal, query='', *, after='', limit=32, include_common=True):
        limit=max(1,min(int(limit),100));values=[]
        scopes=self.knowledge_scopes(principal,include_common=include_common)
        slots=','.join('?' for _ in scopes)
        for row in self.db.execute(f'SELECT id,head FROM sw_unit WHERE scope IN ({slots}) AND id>? ORDER BY id',(*scopes,after)):
            try: value=self.current(row['id'],row['head'],principal)
            except (MemoryError,OSError): continue
            if query and query.casefold() not in (value['topic']+' '+value['question']).casefold(): continue
            values.append(value)
            if len(values)>limit: break
        return {'pages':values[:limit],'next':values[limit-1]['unit_id'] if len(values)>limit else None}

    def verification(self, unit, revision, principal, *, kind, result, policy, verifier, evidence, expires):
        if kind not in {'STRUCTURE','SOURCE','INTERPRETATION'} or result not in {'PASS','FAIL','UNKNOWN'}: raise MemoryError('invalid verification')
        if not policy or not verifier or not evidence or expires<=time.time(): raise MemoryError('bounded policy and evidence required')
        self.require_owned_knowledge(unit,principal)
        value=self.current(unit,revision,principal,allow_draft=True);ident=uid('verify:')
        self.db.execute('INSERT INTO sw_verification VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                        (ident,self.scope(principal),unit,revision,value['hash'],kind,result,policy,verifier,encoded(evidence),expires,now()))
        return ident

    def lease(self, consumer, *, seconds=60, max_attempts=3, scope=None, queue_id=None):
        with self.transaction():
            self.db.execute("UPDATE sw_queue SET status='PENDING',lease=NULL WHERE status='RUNNING' AND lease_until<?",(time.time(),))
            self.db.execute("UPDATE sw_queue SET status='QUARANTINED' WHERE attempts>=? AND status='PENDING'",(max_attempts,))
            row=self.db.execute("SELECT * FROM sw_queue WHERE consumer=? AND status='PENDING' AND next_attempt<=? AND (? IS NULL OR scope=?) AND (? IS NULL OR id=?) ORDER BY id LIMIT 1",(consumer,time.time(),scope,scope,queue_id,queue_id)).fetchone()
            if not row: return None
            lease=uid('lease:')
            self.db.execute("UPDATE sw_queue SET status='RUNNING',lease=?,lease_until=?,attempts=attempts+1 WHERE id=?",(lease,time.time()+seconds,row['id']))
            return {**dict(row),'lease':lease}

    def finish(self, job, *, error=None, max_attempts=3):
        with self.transaction():
            row=self.db.execute("SELECT * FROM sw_queue WHERE id=? AND lease=? AND status='RUNNING'",(job['id'],job['lease'])).fetchone()
            if not row or row['lease_until']<time.time(): raise Conflict('worker lease expired')
            status=('QUARANTINED' if row['attempts']>=max_attempts else 'PENDING') if error else 'DONE'
            self.db.execute('UPDATE sw_queue SET status=?,error=?,next_attempt=?,lease=NULL WHERE id=?',
                            (status,error,time.time()+min(300,2**row['attempts']) if error else 0,job['id']))
            # Cursor cannot jump a failed lower job.
            pending=self.db.execute("SELECT MIN(id) FROM sw_queue WHERE consumer=? AND status<>'DONE'",(job['consumer'],)).fetchone()[0]
            water=(pending-1) if pending is not None else self.db.execute('SELECT COALESCE(MAX(id),0) FROM sw_queue WHERE consumer=?',(job['consumer'],)).fetchone()[0]
            self.db.execute('INSERT INTO sw_cursor VALUES(?,?) ON CONFLICT(consumer) DO UPDATE SET watermark=excluded.watermark',(job['consumer'],water))

    def status(self):
        return {'schema_version':4,'intake':dict(self.db.execute('SELECT status,count(*) FROM sw_intake GROUP BY status')),
                'queue':dict(self.db.execute('SELECT status,count(*) FROM sw_queue GROUP BY status')),
                'knowledge':dict(self.db.execute('SELECT status,count(*) FROM sw_lifecycle GROUP BY status')),
                'cursors':dict(self.db.execute('SELECT consumer,watermark FROM sw_cursor'))}

    def publish(self, unit, revision, principal, *, expected_head):
        with self.transaction():
            self.require_owned_knowledge(unit,principal)
            value=self.current(unit,revision,principal,allow_draft=True)
            row=self.db.execute('SELECT head FROM sw_unit WHERE id=?',(unit,)).fetchone()
            if row[0]!=expected_head or expected_head!=revision:raise Conflict('knowledge head changed')
            self.db.execute("UPDATE sw_lifecycle SET status='PUBLISHED' WHERE unit=? AND revision=?",(unit,revision))
            self._event(self.scope(principal),unit,'KNOWLEDGE_PUBLISHED',{'revision':revision,'hash':value['hash'],'verification':'separate receipts; publication grants no judgment status'})
            self.enqueue(self.scope(principal),'projection',unit,revision)
            return {'unit_id':unit,'revision':revision,'status':'PUBLISHED'}

    def require_owned_knowledge(self, unit, principal):
        row=self.db.execute('SELECT scope FROM sw_unit WHERE id=?',(unit,)).fetchone()
        if not row or row[0]!=self.scope(principal):
            raise MemoryError('catalogue reading grants no publication or verification authority')

    def retire(self, unit, revision, principal, *, reason, disputed=False):
        if not reason:raise MemoryError('retirement reason required')
        with self.transaction():
            row=self.db.execute('SELECT scope FROM sw_unit WHERE id=?',(unit,)).fetchone()
            if not row or row[0]!=self.scope(principal):raise MemoryError('knowledge inaccessible')
            status='DISPUTED' if disputed else 'RETIRED'
            changed=self.db.execute('UPDATE sw_lifecycle SET status=? WHERE unit=? AND revision=?',(status,unit,revision))
            if changed.rowcount!=1:raise MemoryError('knowledge inaccessible')
            self._event(row[0],unit,'KNOWLEDGE_'+status,{'revision':revision,'reason':reason})
            self.invalidate(unit)
            self.enqueue(row[0],'projection',unit,revision)

    def detach_session(self, investigation, session, principal, *, expected_revision, reason):
        with self.transaction():
            event=self.advance(investigation,principal,expected_revision,'LINK_RETRACTED',{'session':session,'reason':reason})
            self.db.execute('UPDATE sw_session_link SET detached=? WHERE investigation=? AND session=? AND detached IS NULL',(event,investigation,session))
            self.invalidate(investigation)
            return event
