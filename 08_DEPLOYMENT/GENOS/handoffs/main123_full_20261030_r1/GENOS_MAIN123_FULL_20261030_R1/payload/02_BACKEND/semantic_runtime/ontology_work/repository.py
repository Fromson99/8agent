"""Transactional workflow metadata and immutable scenario publications.

One DB-API connection per operation. No writes by the RAG reader. Oracle owner
identifiers are validated; all values are binds. No corpus download or mirror.
"""
from contextlib import contextmanager
import json,re,sqlite3
from ..contracts import digest
from ..legal_agent.errors import ContractError
from .schema import now

TABLES={'work':'LGL_ONT_WORK_A','event':'LGL_ONT_EVT_A','publication':'LGL_ONT_PUB_A','head':'LGL_ONT_HEAD_A','anchor':'LGL_ONT_ANC_A'}
COLUMNS={
'work':[('BNDL_ID','VARCHAR2(84 BYTE)','묶음 ID'),('REV_NO','NUMBER(18)','작업 판본'),('WORK_HASH_VAL','VARCHAR2(64 BYTE)','S3 작업 JSON 해시'),('ST_CD','VARCHAR2(32 BYTE)','검토 상태'),('RVWR_ID','VARCHAR2(512 BYTE)','승인자'),('APRV_HASH_VAL','VARCHAR2(64 BYTE)','승인 영수증 해시')],
'event':[('EVT_ID','VARCHAR2(64 BYTE)','이벤트 영수증 ID'),('BNDL_ID','VARCHAR2(84 BYTE)','묶음 ID'),('REV_NO','NUMBER(18)','작업 판본'),('EVT_JSON_CN','CLOB','행위자·시간·상태 JSON')],
'publication':[('PUB_ID','VARCHAR2(64 BYTE)','게시 ID'),('BNDL_ID','VARCHAR2(84 BYTE)','묶음 ID'),('REV_NO','NUMBER(18)','승인 작업 판본'),('PKG_HASH_VAL','VARCHAR2(64 BYTE)','게시 JSON 해시'),('PKG_JSON_CN','CLOB','사전 조립 게시 JSON')],
'head':[('BNDL_ID','VARCHAR2(84 BYTE)','묶음 ID'),('PUB_ID','VARCHAR2(64 BYTE)','활성 게시 ID'),('CHG_SEQ_NO','NUMBER(18)','활성 포인터 변경 순번')],
'anchor':[('PUB_ID','VARCHAR2(64 BYTE)','게시 ID'),('ANC_HASH_VAL','VARCHAR2(64 BYTE)','원문 좌표 해시'),('DOC_ID','VARCHAR2(512 BYTE)','문서 ID'),('SRC_VER_ID','VARCHAR2(512 BYTE)','문서 판본'),('UNIT_ID','VARCHAR2(512 BYTE)','조항 ID')],
}
PK={'work':'BNDL_ID,REV_NO','event':'EVT_ID','publication':'PUB_ID','head':'BNDL_ID','anchor':'PUB_ID,ANC_HASH_VAL'}
def ident(s):
    if not re.fullmatch('[A-Z][A-Z0-9_]{0,29}',s):raise ContractError('invalid ontology SQL identifier')
    return s

def ddl(owner='SIDDA',dialect='oracle'):
    prefix=ident(owner)+'.' if owner else '';out=[]
    for key,name in TABLES.items():
        cols=[]
        for n,t,_ in COLUMNS[key]:
            typ=('INTEGER' if t.startswith('NUMBER') else 'TEXT') if dialect=='sqlite' else t
            nullable=n in ('RVWR_ID','APRV_HASH_VAL','PUB_ID') and key in ('work','head')
            cols.append(n+' '+typ+('' if nullable else ' NOT NULL'))
        cols.append('PRIMARY KEY ('+PK[key]+')')
        if key=='work':cols.extend(["CHECK (ST_CD IN ('INPUT','DRAFT','APPROVED','REJECTED'))",'CHECK (REV_NO>=1)'])
        if key=='head':cols.append('CHECK (CHG_SEQ_NO>=0)')
        if key=='anchor':cols.append('FOREIGN KEY (PUB_ID) REFERENCES '+prefix+TABLES['publication']+'(PUB_ID)')
        if key=='head':cols.append('FOREIGN KEY (PUB_ID) REFERENCES '+prefix+TABLES['publication']+'(PUB_ID)')
        if dialect=='oracle':
            for n,t,_ in COLUMNS[key]:
                if t=='CLOB':cols.append('CHECK ('+n+' IS JSON)')
        out.append('CREATE TABLE '+prefix+name+' (\n  '+',\n  '.join(cols)+'\n)')
    out.append('CREATE INDEX '+prefix+'LGL_ONT_ANC_IX_A ON '+prefix+TABLES['anchor']+'(ANC_HASH_VAL)')
    return out

def value(x):return x.read() if hasattr(x,'read') else x
class Repository:
    def __init__(self,connect,*,dialect='sqlite',owner=''):
        self.connect,self.dialect,self.owner=connect,dialect,owner
        self.tables={k:(ident(owner)+'.' if owner else '')+ident(v) for k,v in TABLES.items()}
    @contextmanager
    def session(self,write=False):
        db=self.connect();c=db.cursor()
        try:
            if self.dialect=='sqlite':
                c.execute('PRAGMA foreign_keys=ON')
                if write:c.execute('BEGIN IMMEDIATE')
            yield c
            if write:db.commit()
        except BaseException:
            if write:db.rollback()
            raise
        finally:c.close();db.close()
    def execute(self,c,sql,params=()):
        # Numeric named bind syntax is accepted by both Oracle and SQLite.
        if self.dialect=='oracle' and any(isinstance(x,str) and len(x.encode())>4000 for x in params):
            import oracledb
            c.setinputsizes(*[oracledb.DB_TYPE_CLOB if isinstance(x,str) and len(x.encode())>4000 else None for x in params])
        return c.execute(sql,{str(i+1):v for i,v in enumerate(params)} if self.dialect=="sqlite" else params)
    def initialize(self):
        with self.session(True) as c:
            for statement in ddl(self.owner,self.dialect):self.execute(c,statement)
    def event(self,c,bid,rev,action,actor,**data):
        event={'bundle_id':bid,'revision':rev,'action':action,'actor':actor,'at':now(),**data};eid=digest(event)
        self.execute(c,f"INSERT INTO {self.tables['event']} VALUES (:1,:2,:3,:4)",(eid,bid,rev,json.dumps(event,ensure_ascii=False)))
        return eid
    def event_record(self,eid):
        with self.session() as c:
            row=self.execute(c,f"SELECT EVT_JSON_CN FROM {self.tables['event']} WHERE EVT_ID=:1",(eid,)).fetchone()
            if not row:raise ContractError('event receipt missing')
            raw=value(row[0]);event=raw if isinstance(raw,dict) else json.loads(raw)
            if digest(event)!=eid:raise ContractError('event receipt changed')
            return event
    def latest(self,bid,c=None):
        if c is None:
            with self.session() as cursor:return self.latest(bid,cursor)
        row=self.execute(c,f"SELECT REV_NO,WORK_HASH_VAL,ST_CD,RVWR_ID,APRV_HASH_VAL FROM {self.tables['work']} WHERE BNDL_ID=:1 ORDER BY REV_NO DESC",(bid,)).fetchone()
        return dict(zip(('revision','work_hash','status','reviewer','approval'),map(value,row))) if row else None
    def list(self, prefix='', after='', limit=256):
        if not re.fullmatch('[A-Za-z0-9_-]*',prefix) or not 1<=limit<=256:raise ContractError('work list filter')
        with self.session() as c:
            rows=self.execute(c,f"SELECT BNDL_ID,REV_NO,ST_CD FROM {self.tables['work']} w WHERE BNDL_ID LIKE :1 AND BNDL_ID>:2 AND REV_NO=(SELECT MAX(REV_NO) FROM {self.tables['work']} v WHERE v.BNDL_ID=w.BNDL_ID) ORDER BY BNDL_ID",(prefix+'%',after)).fetchmany(limit+1)
            if len(rows)>limit:raise ContractError('work list requires narrower scope or pagination')
            return [dict(zip(('bundle_id','revision','status'),r)) for r in rows]
    def revision(self,bid,revision):
        with self.session() as c:
            row=self.execute(c,f"SELECT REV_NO,WORK_HASH_VAL,ST_CD,RVWR_ID,APRV_HASH_VAL FROM {self.tables['work']} WHERE BNDL_ID=:1 AND REV_NO=:2",(bid,revision)).fetchone()
            return dict(zip(('revision','work_hash','status','reviewer','approval'),map(value,row))) if row else None
    def lock(self,c,bid):
        suffix=' FOR UPDATE' if self.dialect=='oracle' else ''
        return self.execute(c,f"SELECT PUB_ID,CHG_SEQ_NO FROM {self.tables['head']} WHERE BNDL_ID=:1"+suffix,(bid,)).fetchone()
    def draft(self,bid,work_hash,expected,actor,status="DRAFT"):
        if status not in ("INPUT","DRAFT"):raise ContractError("draft status")
        with self.session(True) as c:
            head=self.lock(c,bid)
            if head is None:
                if expected!=0:raise ContractError('work no longer matches expected revision')
                self.execute(c,f"INSERT INTO {self.tables['head']} VALUES (:1,NULL,0)",(bid,))
            old=self.latest(bid,c)
            if (old['revision'] if old else 0)!=expected:raise ContractError('stale draft revision')
            rev=expected+1
            self.execute(c,f"INSERT INTO {self.tables['work']} VALUES (:1,:2,:3,:4,NULL,NULL)",(bid,rev,work_hash,status))
            self.event(c,bid,rev,status,actor,work_hash=work_hash)
            return rev
    def review(self,bid,revision,work_hash,actor,approve,reason):
        with self.session(True) as c:
            self.lock(c,bid);row=self.latest(bid,c)
            if not row or row['revision']!=revision or row['work_hash']!=work_hash or row['status']!='DRAFT':raise ContractError('stale or already reviewed draft')
            eid=self.event(c,bid,revision,'APPROVED' if approve else 'REJECTED',actor,work_hash=work_hash,reason=reason)
            self.execute(c,f"UPDATE {self.tables['work']} SET ST_CD=:1,RVWR_ID=:2,APRV_HASH_VAL=:3 WHERE BNDL_ID=:4 AND REV_NO=:5",('APPROVED' if approve else 'REJECTED',actor,eid,bid,revision))
            return eid
    def head(self,bid):
        with self.session() as c:
            row=self.execute(c,f"SELECT PUB_ID,CHG_SEQ_NO FROM {self.tables['head']} WHERE BNDL_ID=:1",(bid,)).fetchone()
            return {'publication_id':row[0],'sequence':int(row[1])} if row else {'publication_id':None,'sequence':0}
    def publish(self,bid,revision,work_hash,approval,payload,expected_sequence,actor):
        from ..legal_agent.ontology_context import configuration
        from ..legal_agent.ontology_compiler import anchor_key
        if 'assembly_package' in payload:raise ContractError('assembly publications require stage/verify/activate')
        configuration(payload);ph=digest(payload);pid=digest([bid,revision,approval,ph])
        with self.session(True) as c:
            head=self.lock(c,bid);row=self.latest(bid,c)
            if not row or row['revision']!=revision or row['work_hash']!=work_hash or row['approval']!=approval or row['status']!='APPROVED':raise ContractError('publication requires current approved revision')
            found=self.execute(c,f"SELECT PKG_HASH_VAL FROM {self.tables['publication']} WHERE PUB_ID=:1",(pid,)).fetchone()
            if found:
                if found[0]!=ph:raise ContractError('publication collision')
                # Reconciliation returns the receipt without moving a rollback head.
                return {'publication_id':pid,'package_sha256':ph,'active':head[0]==pid,'reused':True}
            if not head or int(head[1])!=expected_sequence:raise ContractError('stale publication head')
            self.execute(c,f"INSERT INTO {self.tables['publication']} VALUES (:1,:2,:3,:4,:5)",(pid,bid,revision,ph,json.dumps(payload,ensure_ascii=False)))
            for p in payload['snapshot']['bundles'][0]['provisions']:
                a=p['anchor'];self.execute(c,f"INSERT INTO {self.tables['anchor']} VALUES (:1,:2,:3,:4,:5)",(pid,anchor_key(a),a['document_id'],a['version'],a['unit_id']))
            self.execute(c,f"UPDATE {self.tables['head']} SET PUB_ID=:1,CHG_SEQ_NO=CHG_SEQ_NO+1 WHERE BNDL_ID=:2",(pid,bid))
            self.event(c,bid,revision,'PUBLISHED',actor,publication_id=pid,package_sha256=ph)
        return {'publication_id':pid,'package_sha256':ph,'active':True,'reused':False}
    def activate(self,bid,pid,expected_sequence,actor):
        with self.session(True) as c:
            head=self.lock(c,bid)
            if head is None or head[1]!=expected_sequence:raise ContractError('stale rollback head')
            if pid is not None:
                row=self.execute(c,f"SELECT REV_NO,PKG_JSON_CN FROM {self.tables['publication']} WHERE PUB_ID=:1 AND BNDL_ID=:2",(pid,bid)).fetchone()
                if not row:raise ContractError('rollback publication missing')
                raw=value(row[1]);payload=raw if isinstance(raw,dict) else json.loads(raw)
                if 'assembly_package' in payload:raise ContractError('assembly activation requires verified consumer receipt')
            self.execute(c,f"UPDATE {self.tables['head']} SET PUB_ID=:1,CHG_SEQ_NO=CHG_SEQ_NO+1 WHERE BNDL_ID=:2",(pid,bid))
            self.event(c,bid,0,'ACTIVATED' if pid else 'WITHDRAWN',actor,publication_id=pid)
    def lookup(self,anchor,allowed_documents):
        from ..legal_agent.ontology_compiler import anchor_key
        from ..legal_agent.ontology_context import configuration
        if anchor['document_id'] not in allowed_documents:return []
        with self.session() as c:
            sql=f"SELECT p.PUB_ID,p.PKG_HASH_VAL,p.PKG_JSON_CN FROM {self.tables['anchor']} a JOIN {self.tables['publication']} p ON p.PUB_ID=a.PUB_ID JOIN {self.tables['head']} h ON h.PUB_ID=p.PUB_ID AND h.BNDL_ID=p.BNDL_ID WHERE a.ANC_HASH_VAL=:1"
            # ACL preflight on anchors before reading any stored original/package.
            ids=self.execute(c,f"SELECT a.PUB_ID,b.DOC_ID FROM {self.tables['anchor']} a JOIN {self.tables['head']} h ON h.PUB_ID=a.PUB_ID JOIN {self.tables['anchor']} b ON b.PUB_ID=a.PUB_ID WHERE a.ANC_HASH_VAL=:1",(anchor_key(anchor),)).fetchmany(1025)
            if len(ids)>1024:raise ContractError('ontology anchor result bound')
            denied={pid for pid,did in ids if did not in allowed_documents}
            allowed={pid for pid,_ in ids}-denied
            if len(allowed)>8:raise ContractError('ontology bundle result bound')
            out=[]
            for pid in sorted(allowed):
                row=self.execute(c,f"SELECT PKG_HASH_VAL,PKG_JSON_CN FROM {self.tables['publication']} WHERE PUB_ID=:1",(pid,)).fetchone()
                raw=value(row[1])
                if len(json.dumps(raw,ensure_ascii=False) if isinstance(raw,dict) else raw)>2_000_000:raise ContractError('ontology package result bound')
                payload=raw if isinstance(raw,dict) else json.loads(raw)
                if digest(payload)!=row[0]:raise ContractError('published payload changed')
                configuration(payload)
                if 'assembly_package' in payload:
                    refs=payload['assembly_package']['glossary_refs']
                    check=getattr(self,'glossary_validator',None)
                    if refs and check is None:raise ContractError('assembly requires current glossary binding')
                    if check is not None:check(refs)
                out.append({'publication_id':pid,'context':payload})
            return out

    def stage(self,bid,revision,work_hash,approval,payload,expected_sequence,actor):
        from ..legal_agent.ontology_context import configuration
        from ..legal_agent.ontology_compiler import anchor_key
        configuration(payload)
        if 'assembly_package' not in payload:raise ContractError('stage requires assembly package')
        ph=digest(payload);pid=digest([bid,revision,approval,ph])
        with self.session(True) as c:
            head=self.lock(c,bid);row=self.latest(bid,c)
            if not row or (row['revision'],row['work_hash'],row['approval'],row['status'])!=(revision,work_hash,approval,'APPROVED'):
                raise ContractError('stage requires exact current approval')
            found=self.execute(c,f"SELECT PKG_HASH_VAL FROM {self.tables['publication']} WHERE PUB_ID=:1",(pid,)).fetchone()
            if found:
                if found[0]!=ph:raise ContractError('publication collision')
                return {'publication_id':pid,'package_sha256':ph,'active':head[0]==pid,'reused':True}
            if not head or int(head[1])!=expected_sequence:raise ContractError('stale staging head')
            self.execute(c,f"INSERT INTO {self.tables['publication']} VALUES (:1,:2,:3,:4,:5)",(pid,bid,revision,ph,json.dumps(payload,ensure_ascii=False)))
            for source in payload['assembly_package']['originals']:
                a=source['anchor']
                self.execute(c,f"INSERT INTO {self.tables['anchor']} VALUES (:1,:2,:3,:4,:5)",(pid,anchor_key(a),a['document_id'],a['version'],a['unit_id']))
            self.event(c,bid,revision,'STAGED',actor,publication_id=pid,package_sha256=ph)
        return {'publication_id':pid,'package_sha256':ph,'active':False,'reused':False}

    def publication(self,pid,allowed_documents):
        with self.session() as c:
            docs=self.execute(c,f"SELECT DOC_ID FROM {self.tables['anchor']} WHERE PUB_ID=:1",(pid,)).fetchmany(129)
            if not docs or len(docs)>128 or not {r[0] for r in docs}<=set(allowed_documents):
                raise ContractError('publication outside operator document scope')
            row=self.execute(c,f"SELECT BNDL_ID,REV_NO,PKG_HASH_VAL,PKG_JSON_CN FROM {self.tables['publication']} WHERE PUB_ID=:1",(pid,)).fetchone()
            raw=value(row[3]);payload=raw if isinstance(raw,dict) else json.loads(raw)
            if digest(payload)!=row[2]:raise ContractError('publication content changed')
            return {'bundle_id':row[0],'revision':row[1],'package_sha256':row[2],'context':payload}

    def consumer_receipt(self,pid,package_hash,binding,actor):
        with self.session(True) as c:
            row=self.execute(c,f"SELECT BNDL_ID,REV_NO,PKG_HASH_VAL FROM {self.tables['publication']} WHERE PUB_ID=:1",(pid,)).fetchone()
            if not row or row[2]!=package_hash:raise ContractError('consumer package changed')
            return self.event(c,row[0],row[1],'CONSUMER_VERIFIED',actor,publication_id=pid,
                              package_sha256=package_hash,binding=binding)

    def activate_staged(self,bid,pid,expected_sequence,receipt_id,binding,actor,*,rollback=False):
        with self.session(True) as c:
            head=self.lock(c,bid)
            if not head or int(head[1])!=expected_sequence:raise ContractError('stale activation head')
            row=self.execute(c,f"SELECT REV_NO,PKG_HASH_VAL FROM {self.tables['publication']} WHERE PUB_ID=:1 AND BNDL_ID=:2",(pid,bid)).fetchone()
            receipt=self.execute(c,f"SELECT EVT_JSON_CN FROM {self.tables['event']} WHERE EVT_ID=:1 AND BNDL_ID=:2",(receipt_id,bid)).fetchone()
            if not row or not receipt:raise ContractError('verified staging receipt required')
            latest=self.latest(bid,c)
            if not rollback and (not latest or latest['revision']!=row[0] or latest['status']!='APPROVED'):
                raise ContractError('stale staged work; explicit rollback required')
            raw=value(receipt[0]);event=raw if isinstance(raw,dict) else json.loads(raw)
            if (event.get('action'),event.get('publication_id'),event.get('package_sha256'),event.get('binding'))!=('CONSUMER_VERIFIED',pid,row[1],binding):
                raise ContractError('consumer receipt binding mismatch')
            if head[0]==pid:return {'publication_id':pid,'active':True,'sequence':head[1],'reused':True}
            self.execute(c,f"UPDATE {self.tables['head']} SET PUB_ID=:1,CHG_SEQ_NO=CHG_SEQ_NO+1 WHERE BNDL_ID=:2",(pid,bid))
            self.event(c,bid,row[0],'ROLLED_BACK' if rollback else 'ACTIVATED',actor,publication_id=pid,consumer_receipt=receipt_id)
            return {'publication_id':pid,'active':True,'sequence':head[1]+1,'reused':False}
