from pathlib import Path
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_1164/integrated/snapshot';p=S/'02_BACKEND/semantic_runtime/vector_publish.py'
p.write_text('''"""Dataiku-owned bounded vector build. GENOS never downloads this corpus."""
import json,secrets,time
from .initial_vector import Repository,Encoder,VectorError,decode,profile,vector_sql
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
      text=title+'\\n'+body[pos:pos+800]
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
 def build(self,*,activate=True,items=None):
  r,s,a=self.repo.r,self.repo.s,self.repo.a;pub=self.pub;q=self.request.release_id
  head=self.repo.active(q);expected=head['REVISION'] if head else 0
  self.execute(f"BEGIN INSERT INTO {r}(PUB_ID,QUERY_ID,PROFILE_JSON,MANIFEST_JSON,STATUS) VALUES(:p,:q,:profile,:manifest,'BUILDING'); EXCEPTION WHEN DUP_VAL_ON_INDEX THEN NULL; END;",[('p',pub,'VARCHAR2'),('q',q,'VARCHAR2'),('profile',json.dumps(self.profile),'CLOB'),('manifest',json.dumps(self.manifest),'CLOB')])
  row=self.repo.read(pub)
  if row['MANIFEST_JSON']!=self.manifest:raise VectorError('VECTOR_BUILD: conflicting manifest')
  ready=row['STATUS']=='READY'
  # A crashed Dataiku job requires explicit unlock after verifying the old job stopped.
  # No lease expiry may permit two embedding writers silently.
  if not ready:
   self.execute(f"UPDATE {r} SET LEASE_ID=:lease WHERE PUB_ID=:p AND LEASE_ID IS NULL AND STATUS='BUILDING'; IF SQL%ROWCOUNT<>1 THEN RAISE_APPLICATION_ERROR(-20001,'VECTOR_BUILD_BUSY'); END IF;",[('p',pub,'VARCHAR2'),('lease',self.lease,'VARCHAR2')])
  count=0;reused=0;chain='0'*64
  try:
   batch=[]
   def flush():
    nonlocal reused
    if not batch:return
    missing=[]
    for item in batch:
     old=self.sql.query(f'SELECT INPUT_HASH,META_JSON FROM {s} WHERE PUB_ID=:p AND SEG_ID=:id',[('p',pub,'VARCHAR2'),('id',item['id'],'VARCHAR2')],limit=1)
     if old:
      if old[0]['INPUT_HASH']!=item['meta']['input_sha256'] or decode(old[0]['META_JSON'])!=item['meta']:raise VectorError('VECTOR_BUILD: existing row mismatch')
      reused+=1
     else:missing.append(item)
    if ready and missing:raise VectorError('VECTOR_BUILD: READY publication incomplete')
    if missing:
     vectors=self.encoder.encode([i['text'] for i in missing])
     for item,vector in zip(missing,vectors,strict=True):
      expr=vector_sql(vector,self.profile['dimensions']);m=item['meta']
      self.execute(f"INSERT INTO {s}(PUB_ID,SEG_ID,DOC_ID,SOURCE_ID,INPUT_HASH,META_JSON,EMBEDDING) SELECT :p,:id,:doc,:sid,:hash,:meta,{expr} FROM {r} WHERE PUB_ID=:p AND LEASE_ID=:lease AND STATUS='BUILDING'; IF SQL%ROWCOUNT<>1 THEN RAISE_APPLICATION_ERROR(-20002,'VECTOR_LEASE_LOST'); END IF;",[('p',pub,'VARCHAR2'),('id',item['id'],'VARCHAR2'),('doc',m['document_id'],'VARCHAR2'),('sid',m['source_id'],'VARCHAR2'),('hash',m['input_sha256'],'VARCHAR2'),('meta',json.dumps(m),'CLOB'),('lease',self.lease,'VARCHAR2')])
    batch.clear();self.save({'status':'BUILDING','publication_id':pub,'seen':count,'reused':reused,'embedding_calls':self.encoder.calls})
   for item in segments(self.request) if items is None else items:
    count+=1;chain=digest([chain,item['id'],item['meta']]);batch.append(item)
    if len(batch)==16:flush()
   flush()
   actual=int(self.sql.query(f'SELECT COUNT(*) AS N FROM {s} WHERE PUB_ID=:p',[('p',pub,'VARCHAR2')],limit=1)[0]['N'])
   if actual!=count or not count:raise VectorError('VECTOR_BUILD: incomplete/empty corpus')
   if not ready:
    self.execute(f"UPDATE {r} SET STATUS='READY',EXPECTED_COUNT=:n,ACTUAL_COUNT=:n,LEASE_ID=NULL WHERE PUB_ID=:p AND LEASE_ID=:lease AND STATUS='BUILDING'; IF SQL%ROWCOUNT<>1 THEN RAISE_APPLICATION_ERROR(-20002,'VECTOR_LEASE_LOST'); END IF;",[('n',count,'NUMBER'),('p',pub,'VARCHAR2'),('lease',self.lease,'VARCHAR2')])
   if activate:
    if expected:
     self.execute(f"UPDATE {a} SET PUB_ID=:p,REVISION=REVISION+1 WHERE QUERY_ID=:q AND REVISION=:expected; IF SQL%ROWCOUNT<>1 THEN RAISE_APPLICATION_ERROR(-20003,'VECTOR_ACTIVE_CONFLICT'); END IF;",[('p',pub,'VARCHAR2'),('q',q,'VARCHAR2'),('expected',expected,'NUMBER')]) if head['PUB_ID']!=pub else None
    else:self.execute(f'INSERT INTO {a}(QUERY_ID,PUB_ID,REVISION) VALUES(:q,:p,1);',[('q',q,'VARCHAR2'),('p',pub,'VARCHAR2')])
   result={'status':'READY','publication_id':pub,'query_release_id':q,'count':count,'chain':chain,'reused':reused,'embedding_calls':self.encoder.calls,'active':activate,'previous':head};self.save(result);return result
  except BaseException as exc:
   self.save({'status':'FAILED','publication_id':pub,'seen':count,'reused':reused,'embedding_calls':self.encoder.calls,'error_type':type(exc).__name__})
   raise
  finally:
   if not ready:
    # Failure here is deliberately not swallowed: uncertain lease release stays diagnosable.
    self.execute(f'UPDATE {r} SET LEASE_ID=NULL WHERE PUB_ID=:p AND LEASE_ID=:lease;',[('p',pub,'VARCHAR2'),('lease',self.lease,'VARCHAR2')])
''')
