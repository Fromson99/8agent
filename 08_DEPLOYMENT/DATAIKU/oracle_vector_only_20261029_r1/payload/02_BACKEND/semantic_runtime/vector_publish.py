"""Dataiku-owned bounded vector build. GENOS never downloads this corpus."""
import json,secrets,time
from .initial_vector import Repository,Encoder,VectorError,decode,profile,vector_sql,QUERY,STATUS,LEASE,REVISION,ACTIVE_KEY,DOC,SOURCE
from .oracle_dp_io import digest

def segments(request):
 path=request.snapshot.manifest['navigation']['path']+'/navigation.sqlite'
 kind='asset_'+digest(path)[:12]+'.source'
 after=None
 while True:
  page=request.records.page(kind,after=after,limit=100)
  for row in page['rows']:
   source=decode(row['json']);did=source['document_id'];sid=source['id']
   if did not in request.sources.allowed:raise VectorError('VECTOR_BUILD_SCOPE: unexpected document')
   title=source['document_name']+' / '+source.get('heading','')
   # Source blocks already encode body/supplement/annex partitions. Do not
   # reconstruct an article from its number or merge branches with equal titles.
   blocks=source['blocks']
   for off in range(0,len(blocks),100):
    fetched=request.sources.sources(did,[str(x['block_id']) for x in blocks[off:off+100]])
    for block in fetched:
     body=block['text']
     if not body.strip():continue
     # Complete source coverage, including long final tails. Original text stays unchanged.
     for pos in range(0,len(body),700):
      text=title+'\n'+body[pos:pos+800]
      meta={'source_id':sid,'document_id':did,'unit_id':str(source['unit_id']),'block_id':str(block['block_id']),'start':pos,'end':min(pos+800,len(body)),'source_sha256':digest(source),'block_sha256':digest(body),'input_sha256':digest(text)}
      yield {'id':digest([request.release_id,meta]),'meta':meta,'text':text}
      if pos+800>=len(body):break
  if page['next'] is None:break
  after=page['next']

class Publisher:
 def __init__(self,request,config,*,encoder=None,owner='SIDDS',save=lambda v:None):
  self.request=request;self.sql=request.sql;self.repo=Repository(self.sql,owner);self.profile=profile(config);self.encoder=encoder or Encoder(config,deadline=self.sql.deadline);self.save=save
  self.manifest={'schema_version':'legal-vector-publication-v1','query_id':request.release_id,'source_release_id':request.snapshot.release_id,'dataset_version':request.snapshot.dataset_version,'documents':sorted(request.sources.allowed),'profile':self.profile,'segment_profile':'source-block-window800-step700-v1'}
  self.pub=digest(self.manifest);self.lease=secrets.token_hex(24)
 def execute(self,body,binds=()):
  self.sql.request('BEGIN '+body+' COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;',binds,write=True)
 def existing(self,batch):
  binds=[('p',self.pub,'VARCHAR2')]+[('s'+str(i),v['id'],'VARCHAR2') for i,v in enumerate(batch)]
  names=','.join(':s'+str(i) for i in range(len(batch)))
  rows=self.sql.query(f'SELECT SEG_ID,META_JSON,VECTOR_DIMENSION_COUNT(EMBEDDING) AS DIM,VECTOR_DIMENSION_FORMAT(EMBEDDING) AS FMT FROM {self.repo.s} WHERE PUB_ID=:p AND SEG_ID IN ({names})',binds,limit=len(batch))
  actual={r['SEG_ID']:r for r in rows};expected={v['id']:v for v in batch}
  if len(actual)!=len(rows) or len(expected)!=len(batch) or not set(actual)<=set(expected):raise VectorError('VECTOR_BUILD: duplicate/unexpected segment')
  for sid,row in actual.items():
   if decode(row['META_JSON'])!=expected[sid]['meta'] or int(row['DIM'])!=self.profile['dimensions'] or row['FMT']!='FLOAT32':
    raise VectorError('VECTOR_BUILD: existing row metadata/dimension mismatch')
  return actual
 def insert_many(self,missing,vectors):
  for item,vector in zip(missing,vectors,strict=True):
   self.execute(f"INSERT INTO {self.repo.s}(PUB_ID,SEG_ID,META_JSON,EMBEDDING) SELECT :p,:id,:meta,{vector_sql(vector,self.profile['dimensions'])} FROM {self.repo.r} WHERE PUB_ID=:p AND {LEASE}=:lease AND {STATUS}='BUILDING'; IF SQL%ROWCOUNT<>1 THEN RAISE_APPLICATION_ERROR(-20002,'VECTOR_LEASE_LOST'); END IF;",
                [('p',self.pub,'VARCHAR2'),('id',item['id'],'VARCHAR2'),('meta',json.dumps(item['meta']),'CLOB'),('lease',self.lease,'VARCHAR2')])
 def activate(self,head):
  # A short transaction serializes only pointer swaps. Embedding never holds this lock.
  # Keep compare-and-swap revision: A -> B -> A cannot accept an old revision.
  r=self.repo.r
  body=f"""DECLARE old_pub VARCHAR2(64); old_rev NUMBER; n NUMBER;
  BEGIN
   LOCK TABLE {r} IN EXCLUSIVE MODE NOWAIT;
   SELECT COUNT(*),MAX(PUB_ID),NVL(MAX({REVISION}),0) INTO n,old_pub,old_rev FROM {r} WHERE {ACTIVE_KEY}=:q;
   IF n>1 THEN RAISE_APPLICATION_ERROR(-20003,'VECTOR_ACTIVE_INVALID'); END IF;
   IF old_pub=:p THEN NULL;
   ELSE
    IF old_rev<>:expected OR NVL(old_pub,'-')<>:previous THEN RAISE_APPLICATION_ERROR(-20003,'VECTOR_ACTIVE_CONFLICT'); END IF;
    UPDATE {r} SET PAYLOAD_JSON=JSON_MERGEPATCH(PAYLOAD_JSON,'{{"active_revision":null}}' RETURNING CLOB ERROR ON ERROR) WHERE PUB_ID=old_pub;
    UPDATE {r} SET PAYLOAD_JSON=JSON_MERGEPATCH(PAYLOAD_JSON,JSON_OBJECT('active_revision' VALUE old_rev+1 RETURNING CLOB) RETURNING CLOB ERROR ON ERROR)
     WHERE PUB_ID=:p AND {QUERY}=:q AND {STATUS}='READY' AND {LEASE} IS NULL;
    IF SQL%ROWCOUNT<>1 THEN RAISE_APPLICATION_ERROR(-20003,'VECTOR_ACTIVE_NOT_READY'); END IF;
   END IF;
  END;"""
  self.execute(body,[('q',self.request.release_id,'VARCHAR2'),('p',self.pub,'VARCHAR2'),
                     ('expected',head['REVISION'] if head else 0,'NUMBER'),('previous',head['PUB_ID'] if head else '-','VARCHAR2')])
 def build(self,*,activate=True,items=None):
  r,pub=self.repo.r,self.pub
  head=self.repo.active(self.request.release_id)
  payload={'manifest':self.manifest,'status':'BUILDING'}
  self.execute(f"BEGIN INSERT INTO {r}(PUB_ID,PAYLOAD_JSON) VALUES(:p,:payload); EXCEPTION WHEN DUP_VAL_ON_INDEX THEN NULL; END;",
               [('p',pub,'VARCHAR2'),('payload',json.dumps(payload),'CLOB')])
  row=self.repo.read(pub)
  if row['MANIFEST_JSON']!=self.manifest:raise VectorError('VECTOR_BUILD: conflicting manifest')
  ready=row['STATUS']=='READY'
  if not ready:
   self.execute(f"UPDATE {r} SET PAYLOAD_JSON=JSON_MERGEPATCH(PAYLOAD_JSON,:patch RETURNING CLOB ERROR ON ERROR) WHERE PUB_ID=:p AND {LEASE} IS NULL AND {STATUS}='BUILDING'; IF SQL%ROWCOUNT<>1 THEN RAISE_APPLICATION_ERROR(-20001,'VECTOR_BUILD_BUSY'); END IF;",
                [('patch',json.dumps({'lease':self.lease}),'CLOB'),('p',pub,'VARCHAR2')])
  count,reused,chain,batch=0,0,'0'*64,[]
  try:
   def flush():
    nonlocal reused
    if not batch:return
    old=self.existing(batch);reused+=len(old)
    missing=[v for v in batch if v['id'] not in old]
    if ready and missing:raise VectorError('VECTOR_BUILD: READY publication incomplete')
    if missing:
     self.insert_many(missing,self.encoder.encode([v['text'] for v in missing]))
     if len(self.existing(missing))!=len(missing):raise VectorError('VECTOR_BUILD: committed rows missing')
    batch.clear();self.save({'status':'BUILDING','publication_id':pub,'seen':count,'reused':reused,'embedding_calls':self.encoder.calls})
   for item in segments(self.request) if items is None else items:
    meta=item['meta']
    if meta.get('document_id') not in self.request.sources.allowed or any(not isinstance(meta.get(k),str) or not meta[k] or len(meta[k].encode())>512 for k in ('document_id','source_id')):
     raise VectorError('VECTOR_BUILD_SCOPE: invalid document/source')
    count+=1;chain=digest([chain,item['id'],meta]);batch.append(item)
    if len(batch)==16:flush()
   flush()
   actual=int(self.sql.query(f'SELECT COUNT(*) AS N FROM {self.repo.s} WHERE PUB_ID=:p',[('p',pub,'VARCHAR2')],limit=1)[0]['N'])
   if actual!=count or not count:raise VectorError('VECTOR_BUILD: incomplete/empty corpus')
   if not ready:
    self.execute(f"UPDATE {r} SET PAYLOAD_JSON=JSON_MERGEPATCH(PAYLOAD_JSON,:patch RETURNING CLOB ERROR ON ERROR) WHERE PUB_ID=:p AND {LEASE}=:lease AND {STATUS}='BUILDING'; IF SQL%ROWCOUNT<>1 THEN RAISE_APPLICATION_ERROR(-20002,'VECTOR_LEASE_LOST'); END IF;",
                 [('patch',json.dumps({'status':'READY','lease':None}),'CLOB'),('p',pub,'VARCHAR2'),('lease',self.lease,'VARCHAR2')])
   if activate:self.activate(head)
   result={'status':'READY','publication_id':pub,'query_release_id':self.request.release_id,'count':count,'chain':chain,'reused':reused,'embedding_calls':self.encoder.calls,'active':activate,'previous':head}
   self.save(result);return result
  except BaseException as exc:
   self.save({'status':'FAILED','publication_id':pub,'seen':count,'reused':reused,'embedding_calls':self.encoder.calls,'error_type':type(exc).__name__})
   raise
  finally:
   if not ready:
    self.execute(f"UPDATE {r} SET PAYLOAD_JSON=JSON_MERGEPATCH(PAYLOAD_JSON,'{{\"lease\":null}}' RETURNING CLOB ERROR ON ERROR) WHERE PUB_ID=:p AND {LEASE}=:lease;",
                 [('p',pub,'VARCHAR2'),('lease',self.lease,'VARCHAR2')])
