"""Closed SQL operations over shortcut/wiki records; never invokes legal_agent."""
import json
import time
from .ad_store import fingerprint, excluded, table_exists
from .legal_agent.corrected_memory import digest, encoded


class Backend:
    def __init__(self, store, workspace):
        self.store,self.db,self.workspace=store,store.db,workspace
        from .legal_agent.shortcut_repository import ShortcutRepository
        if table_exists(self.db,'sw_investigation'):
            self.repo=ShortcutRepository.__new__(ShortcutRepository)
            self.repo.path=store.path;self.repo.db=self.db;self.repo.owns_db=False
            self.repo.artifacts=store.path.parent/'artifacts'
        else:self.repo=ShortcutRepository(store.path,db=self.db)
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE name='ad_wiki_index_insert'").fetchone():
            self.db.executescript("""
              CREATE INDEX IF NOT EXISTS sw_scope_team_lookup ON sw_scope(team,id);
              CREATE INDEX IF NOT EXISTS sw_investigation_scope_lookup ON sw_investigation(scope,id);
              CREATE INDEX IF NOT EXISTS sw_unit_scope_lookup ON sw_unit(scope,id);
              INSERT OR REPLACE INTO ad_wiki_index
                SELECT k.unit,s.team,k.revision,json_extract(k.payload,'$.topic'),json_extract(k.payload,'$.question')
                FROM sw_knowledge k JOIN sw_unit u ON u.id=k.unit AND u.head=k.revision JOIN sw_scope s ON s.id=u.scope;
              CREATE TRIGGER ad_wiki_index_insert AFTER INSERT ON sw_knowledge BEGIN
                INSERT INTO ad_wiki_index(unit,workspace,revision,topic,question)
                SELECT NEW.unit,s.team,NEW.revision,json_extract(NEW.payload,'$.topic'),json_extract(NEW.payload,'$.question')
                  FROM sw_unit u JOIN sw_scope s ON s.id=u.scope WHERE u.id=NEW.unit
                ON CONFLICT(unit) DO UPDATE SET revision=excluded.revision,topic=excluded.topic,question=excluded.question
                  WHERE excluded.revision>=ad_wiki_index.revision;
              END;
            """)


    def scopes(self):
        return [r[0] for r in self.db.execute('SELECT id FROM sw_scope WHERE team=?',(self.workspace,))]

    def principal(self, scope):
        row=self.db.execute('SELECT * FROM sw_scope WHERE id=? AND team=?',(scope,self.workspace)).fetchone()
        if not row:raise ValueError('AD_SCOPE: inaccessible record')
        documents=set()
        for r in self.db.execute('SELECT documents FROM sw_investigation WHERE scope=?',(scope,)):
            documents.update(json.loads(r[0]))
        for r in self.db.execute('SELECT documents FROM sw_artifact WHERE scope=?',(scope,)):
            documents.update(json.loads(r[0]))
        return {'user_id':row['owner'],'team_id':row['team'],'tenant_id':row['tenant'],
                'document_ids':sorted(documents),'authenticated':True,'_ad_scope':scope}

    def scoped_sql(self, table):
        """Table identifiers come from a closed catalog; user SQL is never executed."""
        names={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE 'sw_%' OR name LIKE 'ad_%')")}
        if table not in names:raise ValueError('AD_TABLE: unknown table')
        q='SELECT t.rowid AS _rowid,t.* FROM "'+table+'" t'
        columns={r[1] for r in self.db.execute('PRAGMA table_info("'+table+'")')}
        scope='SELECT id FROM sw_scope WHERE team=?'
        cases='SELECT id FROM sw_investigation WHERE scope IN ('+scope+')'
        units='SELECT id FROM sw_unit WHERE scope IN ('+scope+')'
        sessions='SELECT id FROM ad_session WHERE workspace=?'
        if table=='sw_scope':return q+' WHERE team=?',[self.workspace]
        if table.startswith('sw_procedure_'):
            hashes=set()
            for r in self.db.execute('SELECT s.owner,s.team,i.documents FROM sw_scope s JOIN sw_investigation i ON i.scope=s.id WHERE s.team=?',(self.workspace,)):
                hashes.add(digest([r[0],r[1],sorted(json.loads(r[2]))]))
            if table=='sw_procedure_activation':
                return q+' WHERE step IN (SELECT id FROM sw_procedure_step WHERE scope IN ('+','.join('?' for _ in hashes)+'))',list(hashes)
            if 'scope' in columns:return q+' WHERE scope IN ('+','.join('?' for _ in hashes)+')',list(hashes)
        if 'workspace' in columns:return q+' WHERE workspace=?',[self.workspace]
        if 'scope' in columns:return q+' WHERE scope IN ('+scope+')',[self.workspace]
        if 'investigation' in columns:return q+' WHERE investigation IN ('+cases+')',[self.workspace]
        if 'unit' in columns:return q+' WHERE unit IN ('+units+')',[self.workspace]
        if table=='sw_unit_relation':return q+' WHERE source IN ('+units+')',[self.workspace]
        if table=='sw_assignment':return q+' WHERE issue IN (SELECT id FROM sw_issue WHERE investigation IN ('+cases+'))',[self.workspace]
        if table=='sw_fact_head':return q+' WHERE id IN (SELECT id FROM sw_fact WHERE investigation IN ('+cases+'))',[self.workspace]
        if table=='sw_source_version':return q+' WHERE id IN (SELECT id FROM sw_source WHERE scope IN ('+scope+'))',[self.workspace]
        if table=='ad_session':return q+' WHERE workspace=?',[self.workspace]
        if 'session' in columns:return q+' WHERE session IN ('+sessions+')',[self.workspace]
        if 'view' in columns:return q+' WHERE view IN (SELECT id FROM ad_view WHERE session IN ('+sessions+'))',[self.workspace]
        if 'operation' in columns:return q+' WHERE operation IN (SELECT id FROM ad_operation WHERE session IN ('+sessions+'))',[self.workspace]
        if 'job' in columns:return q+' WHERE job IN (SELECT id FROM ad_job WHERE workspace=?)',[self.workspace]
        # These are deployment metadata, not private utterance payloads.
        if table in ('sw_cursor','ad_schema','ad_worker'):return q,[]
        # Legacy/import payloads have no relational ownership. Explicitly report
        # this limitation instead of accidentally exposing another team's data.
        teams={r[0] for r in self.db.execute('SELECT DISTINCT team FROM sw_scope')}
        if teams=={self.workspace}:return q,[]
        return q+' WHERE 0',[]

    def inventory(self):
        result=[]
        for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE 'sw_%' OR name LIKE 'ad_%') ORDER BY name").fetchall():
            table=row[0];sql,args=self.scoped_sql(table)
            count=self.db.execute('SELECT count(*) FROM ('+sql+')',args).fetchone()[0]
            fields=[dict(x) for x in self.db.execute('PRAGMA table_info("'+table+'")')]
            result.append({'kind':'table','id':table,'revision':0,'title':table,
                           'status':f'{count} rows; '+('OWNERSHIP_UNBOUND' if sql.endswith('WHERE 0') else 'SCOPED'), 'columns':fields})
        return result

    def list(self, kind, query='', trash=False):
        if kind=='table':return self.inventory()
        if kind.startswith('table:'):
            table=kind.split(':',1)[1];sql,args=self.scoped_sql(table)
            return [{'kind':kind,'id':str(r['_rowid']),'revision':r['revision'] if 'revision' in r.keys() and type(r['revision']) is int else 0,
                     'title':str(r['id'] if 'id' in r.keys() else r['_rowid']),'status':str(r['status'] if 'status' in r.keys() else '')}
                    for r in self.db.execute(sql+' ORDER BY t.rowid',args)]
        if kind=='shortcut':
            sql='SELECT i.id,i.revision,i.title,i.status FROM sw_investigation i JOIN sw_scope s ON s.id=i.scope WHERE s.team=? ORDER BY i.id'
        elif kind=='wiki':
            sql="SELECT u.unit id,u.revision,u.topic title,l.status FROM ad_wiki_index u JOIN sw_lifecycle l ON l.unit=u.unit AND l.revision=u.revision WHERE u.workspace=? ORDER BY u.unit"
        elif kind in ('job','schedule','error'):
            if kind=='job':sql='SELECT id,0 revision,id title,status FROM ad_job WHERE workspace=? ORDER BY created_at DESC'
            elif kind=='schedule':sql="SELECT id,0 revision,id title,CASE enabled WHEN 1 THEN 'ENABLED' ELSE 'CANCELLED' END status FROM ad_schedule WHERE workspace=? ORDER BY due_at"
            else:sql='SELECT e.id,0 revision,e.error_type title,e.message status FROM ad_error e JOIN ad_session s ON s.id=e.session WHERE s.workspace=? ORDER BY e.created_at DESC'
        else:raise ValueError('AD_KIND: unsupported list kind '+kind)
        rows=[]
        for r in self.db.execute(sql,(self.workspace,)).fetchall():
            value=dict(r);value['kind']=kind
            if kind=='shortcut' and not trash:
                from .legal_agent.successful_answer import eligible
                if not eligible(self.repo,value['id']):continue
            state=self.db.execute('SELECT review,trashed FROM ad_object WHERE kind=? AND entity=?',(kind,value['id'])).fetchone()
            if trash and not (state and state['trashed']):continue
            if not trash and state and state['trashed']:continue
            if state:value['status']+=' / '+state['review']+(' / TRASHED' if state['trashed'] else '')
            if query and query.casefold() not in (value['title']+' '+value['id']).casefold():continue
            rows.append(value)
        return rows

    def record(self, kind, entity):
        spec={'shortcut':('sw_investigation','id'),'wiki':('sw_unit','id'), 'fact':('sw_fact','id'),
              'issue':('sw_issue','id'),'event':('sw_event','id'),'trace':('sw_trace','id'),
              'relation':('sw_relation','id'),'procedure':('sw_procedure_step','id'),
              'job':('ad_job','id'),'schedule':('ad_schedule','id'),'error':('ad_error','id')}
        if kind not in spec:raise ValueError('AD_KIND: unsupported record '+kind)
        table,key=spec[kind];sql,args=self.scoped_sql(table)
        predicate=' AND ' if ' WHERE ' in sql else ' WHERE '
        rows=self.db.execute(sql+predicate+'t."'+key+'"=? ORDER BY t.rowid DESC LIMIT 1',[*args,entity]).fetchall()
        if not rows:raise ValueError('AD_SCOPE: record missing or outside this workspace: '+str(entity))
        row=dict(rows[0]);row.pop('_rowid',None)
        if kind=='wiki':
            row.update(dict(self.db.execute('SELECT * FROM sw_knowledge WHERE unit=? AND revision=?',(entity,row['head'])).fetchone()))
        return row

    def revision(self, kind, entity):
        row=self.record(kind,entity)
        rev=int(row.get('revision',row.get('head',row.get('seq',0))))
        state=self.db.execute('SELECT revision FROM ad_object WHERE kind=? AND entity=?',(kind,entity)).fetchone()
        if state and state[0]>=1000000:raise ValueError('AD_REVISION: administrative revision limit; schema migration required')
        # Independently advancing content and administrative state form one CAS.
        return rev*1000000+(state[0] if state else 0)

    def targets(self, rows):
        mapped={'sw_investigation':'shortcut','sw_unit':'wiki','sw_knowledge':'wiki','sw_fact':'fact',
                'sw_issue':'issue','sw_event':'event','sw_trace':'trace','sw_relation':'relation','sw_procedure_step':'procedure'}
        result=[]
        for r in rows:
            kind=r['kind'];entity=str(r.get('entity',r.get('id','')))
            if kind.startswith('table:'):
                table=kind.split(':',1)[1]
                if table not in mapped:raise ValueError('AD_IMMUTABLE: this table is inspection-only: '+table)
                sql,args=self.scoped_sql(table);row=self.db.execute(sql+(' AND ' if ' WHERE ' in sql else ' WHERE ')+'t.rowid=?',[*args,int(entity)]).fetchone()
                if not row:raise ValueError('AD_SCOPE: row no longer accessible')
                kind=mapped[table];entity=str(row['unit'] if table=='sw_knowledge' else row['id'])
                if table=='sw_knowledge' and self.record('wiki',entity)['revision']!=row['revision']:raise ValueError('AD_REVISION: 과거 위키 버전은 조회 전용입니다. 현재 단위를 선택해 새 버전으로 수정하세요.')
            result.append({'kind':kind,'entity':entity,'revision':int(r['revision']) if int(r.get('revision',0))>=1000000 else self.revision(kind,entity)})
        return result

    def detail(self, kind, entity):
        if kind=='table':
            return next(x for x in self.inventory() if x['id']==entity)
        if kind.startswith('table:'):
            table=kind.split(':',1)[1];sql,args=self.scoped_sql(table)
            row=self.db.execute(sql+(' AND ' if ' WHERE ' in sql else ' WHERE ')+'t.rowid=?',[*args,int(entity)]).fetchone()
            if not row:raise ValueError('AD_SCOPE: row missing')
            value=dict(row)
            if table=='sw_artifact':
                data=self.repo.read_artifact(row['id'],self.principal(row['scope']))
                try:value['artifact_content']=data.decode('utf-8')
                except UnicodeDecodeError:
                    import base64
                    value.update(artifact_encoding='base64',artifact_content=base64.b64encode(data).decode())
            return value
        row=self.record(kind,entity)
        result={'record':row}
        if kind=='shortcut':
            for table,clause in [('sw_event','aggregate_id'),('sw_issue','investigation'),('sw_fact','investigation'),('sw_trace','investigation'),('sw_branch','investigation'),('sw_session_link','investigation')]:
                result[table]=[dict(r) for r in self.db.execute('SELECT * FROM '+table+' WHERE '+clause+'=? ORDER BY rowid',(entity,))]
        if kind=='shortcut':
            result['sw_intake']=[dict(r) for r in self.db.execute('SELECT * FROM sw_intake WHERE investigation=? ORDER BY rowid',(entity,))]
            result['intake_events']=[dict(r) for r in self.db.execute('SELECT * FROM sw_event WHERE id IN (SELECT event FROM sw_intake WHERE investigation=?) ORDER BY rowid',(entity,))]
        if kind=='wiki':
            for table in ('sw_knowledge','sw_claim','sw_procedure','sw_member','sw_dependency','sw_verification','sw_lifecycle'):
                result[table]=[dict(r) for r in self.db.execute('SELECT * FROM '+table+' WHERE unit=? ORDER BY rowid',(entity,))]
        if kind=='job':
            result['items']=[dict(r) for r in self.db.execute('SELECT * FROM ad_job_item WHERE job=? ORDER BY queue_id',(entity,))]
            result['errors']=[dict(r) for r in self.db.execute('SELECT * FROM ad_error WHERE job=? ORDER BY created_at',(entity,))]
        return result

    def change(self, target, action, operation, ordinal, field=None, value=None):
        kind,entity=target['kind'],target['entity'];before=self.revision(kind,entity)
        if before!=target['revision']:raise ValueError('AD_CONFLICT: record changed since selection; refresh the table: '+entity)
        row=self.record(kind,entity)
        self.db.execute('INSERT OR IGNORE INTO ad_object(kind,entity,workspace,changed_at) VALUES(?,?,?,?)',(kind,entity,self.workspace,time.time()))
        before_value=after_value=None
        if action in ('approve','reject','trash','restore'):
            if action in ('approve','reject'):
                review='APPROVED' if action=='approve' else 'REJECTED'
                self.db.execute('UPDATE ad_object SET review=?,reviewed_revision=? WHERE kind=? AND entity=?',(review,int(row.get('revision',row.get('head',0))),kind,entity))
            else:self.db.execute('UPDATE ad_object SET trashed=? WHERE kind=? AND entity=?',(int(action=='trash'),kind,entity))
            if kind=='wiki' and action in ('trash','restore','reject','approve'):
                payload=json.loads(row['payload'])
                signature=digest(sorted((m['ref'],m.get('start'),m.get('stop')) for m in payload.get('members',[])))
                if payload.get('members'):
                    self.db.execute('INSERT INTO ad_exclusion VALUES(?,?,?,?) ON CONFLICT(workspace,unit) DO UPDATE SET signature=excluded.signature,active=excluded.active',(self.workspace,entity,signature,int(action in ('trash','reject'))))

        elif action=='publish':
            if kind!='wiki':raise ValueError('AD_TARGET: publish requires a wiki unit')
            if excluded(self.db,'wiki',entity):raise ValueError('AD_STATE: restore/approve rejected or trashed wiki first')
            self.repo.current(entity,row['revision'],self.principal(row['scope']),allow_draft=True)
            self.db.execute("UPDATE sw_lifecycle SET status='PUBLISHED' WHERE unit=? AND revision=?",(entity,row['revision']))
        elif action=='edit':
            before_value,after_value=self.edit(kind,entity,row,field,value)
            self.db.execute("UPDATE ad_object SET review='PENDING',reviewed_revision=NULL WHERE kind=? AND entity=?",(kind,entity))
        else:raise ValueError('AD_ACTION: unsupported mutation')
        self.db.execute('UPDATE ad_object SET revision=revision+1,changed_at=? WHERE kind=? AND entity=?',(time.time(),kind,entity))
        # Existing stale-dependency mechanics are reused, never legal approval.
        self.repo.invalidate(entity)
        if kind in ('fact','event','trace','issue','relation'):
            inv=row.get('investigation') or row.get('aggregate_id') or row.get('source')
            if inv and str(inv).startswith('inv:'):self.repo.invalidate(inv)
        if kind=='shortcut' and action in ('trash','reject','edit'):
            # Stored step decisions were keyed by request scope rather than case;
            # revoke that scope's activations conservatively until fresh research.
            if table_exists(self.db,'sw_procedure_step'):
                owner=self.db.execute('SELECT owner,team FROM sw_scope WHERE id=?',(row['scope'],)).fetchone()
                scope=digest([owner[0],owner[1],sorted(json.loads(row['documents']))])
                self.db.execute('DELETE FROM sw_procedure_activation WHERE step IN (SELECT id FROM sw_procedure_step WHERE scope=?)',(scope,))
        case_id=entity if kind=='shortcut' else row.get('investigation')
        if case_id and action in ('edit','trash','restore','reject'):
            if action!='edit':self.db.execute('UPDATE sw_investigation SET revision=revision+1 WHERE id=?',(case_id,))
            case=self.db.execute('SELECT scope,revision FROM sw_investigation WHERE id=?',(case_id,)).fetchone()
            if case and not excluded(self.db,'shortcut',case_id):self.repo.enqueue(case['scope'],'wiki',case_id,case['revision'])
        if kind=='wiki':self.repo.enqueue(row['scope'],'projection',entity,int(row.get('revision',row.get('head',1))))
        after=self.revision(kind,entity)
        self.db.execute('INSERT INTO ad_change VALUES(?,?,?,?,?,?,?,?,?,?)',(operation,ordinal,kind,entity,before,after,action,field,before_value,after_value))
        return {'id':entity,'kind':kind,'before_revision':before,'after_revision':after,'action':action,
                'note':'사용자 승인과 법률 검증은 별도입니다. 복구·수정 자료는 현재 의존 상태를 다시 검사합니다.'}

    def edit(self, kind, entity, row, field, value):
        if not field or value is None:raise ValueError('AD_EDIT: field and replacement value required')
        if kind=='shortcut' and field=='title':
            old=row['title'];self.db.execute('UPDATE sw_investigation SET title=?,revision=revision+1 WHERE id=?',(str(value),entity))
            self.repo._event(row['scope'],entity,'AD_TITLE_CORRECTED',{'before':old,'after':value})
            return old,str(value)
        if kind=='fact' and field in ('value','valid_time','subject','predicate'):
            old=row[field];new=dict(row);new[field]=str(value) if field in ('subject','predicate') else encoded(value)
            new['revision']=row['revision']+1;new['supersedes']=row['revision'];new['status']='ASSERTED'
            case=self.record('shortcut',row['investigation']);event=self.repo._event(case['scope'],case['id'],'AD_FACT_CORRECTED',{'fact':entity,'field':field,'before':old,'after':value})
            new['event']=event
            cols=('id','revision','investigation','subject','predicate','value','valid_time','event','supersedes','status')
            self.db.execute('INSERT INTO sw_fact VALUES('+','.join('?' for _ in cols)+')',tuple(new[c] for c in cols))
            self.db.execute('UPDATE sw_fact_head SET revision=? WHERE id=?',(new['revision'],entity))
            self.db.execute('UPDATE sw_investigation SET revision=revision+1 WHERE id=?',(case['id'],))
            return str(old),str(new[field])
        if kind=='issue' and field=='question':
            old=row['question'];self.db.execute('UPDATE sw_issue SET question=? WHERE id=?',(str(value),entity))
            self.db.execute('UPDATE sw_investigation SET revision=revision+1 WHERE id=?',(row['investigation'],))
            return old,str(value)
        if kind=='wiki':
            allowed={'topic','question','unresolved','applicable_time','jurisdiction','claims','procedures','members'}
            if field not in allowed:raise ValueError('AD_SCHEMA: wiki editable fields: '+', '.join(sorted(allowed)))
            payload=json.loads(row['payload']);old=payload.get(field)
            if field in ('claims','procedures','members','unresolved') and not isinstance(value,list):raise ValueError('AD_SCHEMA: '+field+' must be an array')
            if field not in ('claims','procedures','members','unresolved') and not isinstance(value,str):raise ValueError('AD_SCHEMA: '+field+' must be a string')
            if field=='members':
                prior={m['ref']:m for m in payload.get('members',[])}
                for member in value:
                    if not isinstance(member,dict) or member.get('ref') not in prior:
                        raise ValueError('AD_SCHEMA: member must reference an existing bound source; compile the case to add new sources')
                    if member!=prior[member['ref']]:
                        raise ValueError('AD_SCHEMA: source span/hash must match bound evidence; remove unwanted members or rebuild from corrected shortcut')
            payload[field]=value;payload['completeness']='OPEN'
            # Structural checks for hand-edited procedures and source references.
            from .legal_agent.reuse_policy import validate_procedure
            from .legal_agent.wiki_execution import CATALOGUE
            for p in payload.get('procedures',[]):validate_procedure(p,CATALOGUE)
            refs={m['ref'] for m in payload.get('members',[])}
            for claim in payload.get('claims',[]):
                if not {'id','statement','condition','exceptions_checked','evidence_refs','rationale','unresolved'}<=claim.keys():raise ValueError('AD_SCHEMA: incomplete claim fields')
                if not set(claim['evidence_refs'])<=refs:raise ValueError('AD_SCHEMA: claim evidence is not in members')
            rev=row['revision']+1
            self.db.execute('INSERT INTO sw_knowledge VALUES(?,?,?,?,?,?)',(entity,rev,row['build'],encoded(payload),digest(payload),'OPEN'))
            self.db.execute("INSERT INTO sw_lifecycle VALUES(?,?,'DRAFT')",(entity,rev))
            self.db.execute('UPDATE sw_unit SET head=? WHERE id=?',(rev,entity))
            self.db.execute('INSERT INTO sw_dependency SELECT unit,?,ref,version,hash,role FROM sw_dependency WHERE unit=? AND revision=?',(rev,entity,row['revision']))
            for m in payload.get('members',[]):self.db.execute('INSERT INTO sw_member VALUES(?,?,?,?)',(entity,rev,m['ref'],encoded(m)))
            for table,key in [('sw_claim','claims'),('sw_procedure','procedures')]:
                for v in payload.get(key,[]):self.db.execute('INSERT INTO '+table+' VALUES(?,?,?,?)',(entity,rev,v['id'],encoded(v)))
            self.db.execute('INSERT INTO sw_unit_relation SELECT source,?,target,target_revision,kind,reason FROM sw_unit_relation WHERE source=? AND revision=?',(rev,entity,row['revision']))
            return encoded(old),encoded(value)
        raise ValueError('AD_SCHEMA: editable: shortcut.title, fact.subject/predicate/value/valid_time, issue.question, wiki.topic/question/claims/procedures/members/unresolved/applicable_time/jurisdiction. Immutable source remains unchanged.')
