"""Typed expression observations in the existing learning ledger; operator approval only."""
from contextlib import closing
from datetime import datetime, timezone
from copy import deepcopy
import hashlib,json,uuid
from . import learning_store as base
from . import typed_navigation as previous

KINDS=('folder','document','term','structure')
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def string(value,limit=200):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:raise ValueError('nonempty bounded string required')
    return value.strip()
def connect(path):
    db=base.connect(path)
    # Namespaced tables preserve the v1 expression/recipe reader and publisher unchanged.
    db.executescript('''CREATE TABLE IF NOT EXISTS entity_mapping_candidate(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS entity_mapping_review(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,candidate_id TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS entity_mapping_latest ON entity_mapping_review(candidate_id,seq);''')
    return db

def rows(db):
    return [{'id':r['id'],'payload':json.loads(r['payload']),'status':r['status'] or 'PROPOSED','review':json.loads(r['review']) if r['review'] else None} for r in db.execute('''SELECT c.*,e.status,e.payload AS review FROM entity_mapping_candidate c LEFT JOIN entity_mapping_review e ON e.seq=(SELECT max(seq) FROM entity_mapping_review WHERE candidate_id=c.id) ORDER BY c.id''')]

def target(matcher,scope,value):
    if not isinstance(value,dict) or set(value)!={'type','identity'} or value['type'] not in KINDS:raise ValueError('typed target required')
    kind,ident=value['type'],string(value['identity'],1000);scope=set(matcher.tools.validate_scope(scope))
    if kind=='folder':
        paths={p for d in scope if (p:=matcher.document_catalogue[d].get('navigation_folder'))}
        if ident not in ('internal','external') and not any(p==ident or p.startswith(ident+'/') for p in paths):raise ValueError('unknown or unauthorized folder')
        ids=[d for d in scope if (p:=matcher.document_catalogue[d].get('navigation_folder')) and (p==ident or p.startswith(ident+'/'))]
    elif kind=='document':
        if ident not in scope:raise ValueError('unknown or unauthorized document')
        ids=[ident]
    elif kind=='term':
        t=matcher.tools.terms.get(ident)
        if not t or (t.get('scope_document_id') and t['scope_document_id'] not in scope):raise ValueError('unknown or unauthorized term')
        ids=sorted(scope)
    else:
        found=[(d,u) for d,u in matcher.units if d in scope and d+':'+u==ident]
        if len(found)!=1:raise ValueError('unknown or unauthorized structure')
        ids=[found[0][0]]
    return {'type':kind,'identity':ident},sorted(ids)

class MappingStore:
    def __init__(self,path,matcher,manifest,authorized,actor):
        self.path=path;self.m=matcher;self.manifest=manifest;self.scope=sorted(matcher.tools.validate_scope(authorized));self.actor=string(actor)
    def current(self,p):return p['generation_id']==self.manifest['generation_id'] and p['source_store_sha256']==self.manifest['store_sha256']
    def list(self):
        with closing(connect(self.path)) as db:items=rows(db)
        # A shared ledger never exposes another operator's query fragments.
        return [r for r in items if r['payload']['owner']==self.actor and set(r['payload']['document_version_ids'])<=set(self.scope)]
    def propose(self,expression,to,*,origin='USER',question=None,reason='사용자 입력'):
        expression=string(expression,120);string(reason,1000)
        if origin not in ('USER','LLM'):raise ValueError('invalid origin')
        to,_=target(self.m,self.scope,to)
        if origin=='LLM' and (not isinstance(question,str) or expression not in question):raise ValueError('LLM mapping must quote an exact question span')
        p={'expression':expression,'target':to,'generation_id':self.manifest['generation_id'],'source_store_sha256':self.manifest['store_sha256'],'document_version_ids':self.scope,'owner':self.actor,'origin':origin,'reason':reason,'canonical_approval':False}
        if question is not None:p['question_sha256']=digest(question);p['span']={'start':question.index(expression),'end':question.index(expression)+len(expression)}
        ident='entity-mapping:'+digest(p)
        with closing(connect(self.path)) as db,db:db.execute('INSERT OR IGNORE INTO entity_mapping_candidate VALUES (?,?)',(ident,canonical(p)))
        return ident
    def review(self,ident,status,reason):
        string(reason,1000)
        with closing(connect(self.path)) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                items=rows(db);r=next((r for r in items if r['id']==ident),None)
                if not r or r['payload']['owner']!=self.actor or not set(r['payload']['document_version_ids'])<=set(self.scope):raise ValueError('unknown or unauthorized mapping')
                if status not in {'PROPOSED':{'APPROVED','REJECTED'},'APPROVED':{'REVOKED'}}.get(r['status'],set()):raise ValueError('invalid review transition')
                p=r['payload']
                if status=='APPROVED':
                    if not self.current(p):raise ValueError('stale generation; submit a new mapping')
                    target(self.m,p['document_version_ids'],p['target'])
                    for other in items:
                        op=other['payload']
                        if other['status']=='APPROVED' and op['owner']==self.actor and self.current(op) and previous.folders.normalized(op['expression'])==previous.folders.normalized(p['expression']) and set(op['document_version_ids'])&set(p['document_version_ids']) and op['target']!=p['target']:raise ValueError('conflicting approved mapping; revoke or narrow scope first')
                event={'id':'mapping-review:'+uuid.uuid4().hex,'candidate_id':ident,'status':status,'reviewer':self.actor,'reason':reason,'at':datetime.now(timezone.utc).isoformat()}
                db.execute('INSERT INTO entity_mapping_review(id,candidate_id,status,payload) VALUES (?,?,?,?)',(event['id'],ident,status,canonical(event)));db.commit();return event
            except BaseException:db.rollback();raise
    def add(self,expression,to,reason='사용자 직접 등록'):
        ident=self.propose(expression,to,reason=reason)
        existing=next(r for r in self.list() if r['id']==ident)
        if existing['status']=='PROPOSED':self.review(ident,'APPROVED',reason)
        elif existing['status']!='APPROVED':raise ValueError('retired mapping; submit with a new reason to preserve history')
        return ident
    def active(self,scope):
        scope=set(self.m.tools.validate_scope(scope));out=[]
        for r in self.list():
            p=r['payload']
            if r['status']=='APPROVED' and self.current(p) and scope<=set(p['document_version_ids']):
                try:target(self.m,scope,p['target'])
                except ValueError:continue
                out.append(r)
        return out

class BoundMatcher:
    """Alias seeds retain the user's original question and exact occurrence spans."""
    def __init__(self,base,bindings):self.base=base;self.bindings=bindings
    def __getattr__(self,key):return getattr(self.base,key)
    def starts(self,q,scope):
        out=deepcopy(self.base.starts(q,scope))
        for binding in self.bindings:
            phrase=binding['expression'];to=binding['target']
            if phrase not in q:continue
            try:_,ids=target(self.base,scope,to)
            except ValueError:continue
            spans=[];at=0
            while (at:=q.find(phrase,at))>=0:spans.append({'text':phrase,'start':at,'end':at+len(phrase)});at+=len(phrase)
            kind=to['type'];ident=to['identity']
            if kind=='folder':continue
            key={'term':'terms','document':'documents','structure':'structures'}[kind]
            item={'id':('structure:'+ident if kind=='structure' else ident),'question_spans':spans}
            if kind=='document':item['name']=self.base.documents[ident]
            if kind=='structure':
                did,uid=next((d,u) for d,u in self.base.units if d+':'+u==ident);item.update(document_id=did,family=self.base.units[(did,uid)]['family'],kind='LOCATOR')
            found=next((x for x in out[key] if x['id']==item['id']),None)
            if found:found['question_spans']+=spans
            else:out[key].append(item)
        return out
