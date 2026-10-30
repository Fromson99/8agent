"""GENOS HTTP embedding and immutable Oracle vector publications. No local model."""
from __future__ import annotations
import hashlib,json,math,os,re,time
from urllib.parse import urlparse
from .oracle_dp_io import DPError,digest

class VectorError(DPError):pass
class VectorUnavailable(VectorError):pass

def mode():
 value=os.environ.get('GENOS_RAG_INITIAL_SEARCH','auto').strip().lower()
 if value not in ('auto','vector','keyword'):raise VectorError('VECTOR_CONFIG: initial search must be auto/vector/keyword')
 return value

def endpoint(env=None):
 e=os.environ if env is None else env
 direct=e.get('GENOS_EMBED_URL','').strip().rstrip('/')
 base=e.get('GENOS_BASE_URL','').strip().rstrip('/')
 sid=e.get('GENOS_EMBED_SERVING_ID','').strip()
 if direct and (base or sid):raise VectorError('VECTOR_CONFIG: use direct embedding URL or base+serving ID')
 if not direct and (not base or not re.fullmatch(r'[A-Za-z0-9_-]+',sid)):raise VectorError('VECTOR_CONFIG: embedding base/serving ID required')
 root=direct or base+'/api/gateway/rep/serving/'+sid
 u=urlparse(root)
 if u.scheme!='https' or not u.netloc or u.username or u.password or u.query or u.fragment:raise VectorError('VECTOR_CONFIG: authenticated HTTPS root required')
 return root

def profile(value):
 keys={'schema_version','model','revision','dimensions','endpoint_sha256','chunk_chars','overlap_chars','normalization','metric'}
 if not isinstance(value,dict) or set(value)!=keys or value['schema_version']!='legal-vector-profile-v1':raise VectorError('VECTOR_PROFILE: fields')
 if any(not isinstance(value[k],str) or not value[k].strip() for k in ('model','revision')):raise VectorError('VECTOR_PROFILE: immutable model/revision required')
 if not re.fullmatch('[0-9a-f]{64}',value['endpoint_sha256']):raise VectorError('VECTOR_PROFILE: endpoint binding')
 if type(value['dimensions']) is not int or not 1<=value['dimensions']<=4096:raise VectorError('VECTOR_PROFILE: dimensions')
 if value['normalization']!='l2' or value['metric']!='COSINE' or value['chunk_chars']!=800 or value['overlap_chars']!=100:raise VectorError('VECTOR_PROFILE: unsupported preprocessing')
 return dict(value)

def normalize(values,dim):
 if not isinstance(values,list) or len(values)!=dim or any(type(x) not in (int,float) or not math.isfinite(x) for x in values):raise VectorError('VECTOR_VALUE: invalid dimensions/numeric values')
 norm=math.sqrt(sum(float(x)**2 for x in values))
 if not math.isfinite(norm) or norm<=0:raise VectorError('VECTOR_VALUE: zero/nonfinite norm')
 return [float(x)/norm for x in values]

def vector_sql(values,dim):
 vals=normalize(values,dim)
 text=json.dumps(vals,separators=(',',':'),allow_nan=False)
 return "TO_VECTOR("+' || '.join("TO_CLOB('"+text[i:i+3000]+"')" for i in range(0,len(text),3000))+", "+str(dim)+", FLOAT32)"

class Encoder:
 def __init__(self,config,*,env=None,post=None,deadline=None):
  self.profile=profile(config);e=os.environ if env is None else env;self.root=endpoint(e)
  if hashlib.sha256(self.root.encode()).hexdigest()!=config['endpoint_sha256']:raise VectorError('VECTOR_BINDING: endpoint differs from published profile')
  self.key=e.get('GENOS_EMBED_KEY','').strip()
  if not self.key:raise VectorError('VECTOR_CONFIG: GENOS_EMBED_KEY required')
  self.deadline=deadline or time.monotonic()+3600;self.calls=0;self.post=post
 def encode(self,texts):
  if not texts or len(texts)>16 or any(not isinstance(x,str) or not x.strip() or len(x)>16000 for x in texts):raise VectorError('VECTOR_INPUT: bounded nonempty inputs required')
  remaining=self.deadline-time.monotonic()
  if remaining<=0:raise VectorUnavailable('VECTOR_TIMEOUT: request deadline')
  if self.post is None:
   import requests
   session=requests.Session();session.trust_env=False;send=session.post
  else:session=None;send=self.post
  self.calls+=1
  try:
   response=send(self.root+'/embeddings',headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'},json={'model':self.profile['model'],'input':texts},timeout=min(10,remaining),allow_redirects=False)
   if response.status_code in (429,500,502,503,504):raise VectorUnavailable('VECTOR_TRANSPORT: '+str(response.status_code))
   if response.status_code!=200:raise VectorError('VECTOR_HTTP: '+str(response.status_code))
   data=response.json();rows=data.get('data')
  except VectorError:raise
  except Exception as exc:raise VectorUnavailable('VECTOR_TRANSPORT: '+type(exc).__name__) from None
  finally:
   if session is not None:session.close()
  if not isinstance(rows,list) or len(rows)!=len(texts) or any(not isinstance(r,dict) or type(r.get('index')) is not int for r in rows) or {r['index'] for r in rows}!=set(range(len(texts))):raise VectorError('VECTOR_RESPONSE: incomplete/duplicate index')
  return [normalize(r.get('embedding'),self.profile['dimensions']) for r in sorted(rows,key=lambda r:r['index'])]

TABLES={'release':'LGL_VCTR_SET_S','segment':'LGL_VCTR_ITEM_S'}

def table(key,owner='SIDDS'):
 if not re.fullmatch('[A-Z][A-Z0-9_]{0,29}',owner):raise VectorError('VECTOR_SCHEMA: invalid owner')
 return owner+'.'+TABLES[key]

def jvalue(column,path,typ='VARCHAR2(64)'):
 return f"JSON_VALUE({column}, '$.{path}' RETURNING {typ} ERROR ON ERROR)"

QUERY=jvalue('PAYLOAD_JSON','manifest.query_id')
STATUS=jvalue('PAYLOAD_JSON','status','VARCHAR2(16)')
LEASE=jvalue('PAYLOAD_JSON','lease').replace('ERROR ON ERROR)', 'ERROR ON ERROR NULL ON EMPTY)')
REVISION=jvalue('PAYLOAD_JSON','active_revision','NUMBER').replace('ERROR ON ERROR)', 'ERROR ON ERROR NULL ON EMPTY)')
ACTIVE_KEY=f'CASE WHEN {REVISION} IS NOT NULL THEN {QUERY} END'
DOC=jvalue('META_JSON','document_id','VARCHAR2(512)')
SOURCE=jvalue('META_JSON','source_id','VARCHAR2(512)')

def ddl(owner='SIDDS'):
 r,s=[table(k,owner) for k in ('release','segment')]
 return [f"CREATE TABLE {r} (PUB_ID VARCHAR2(64 BYTE) PRIMARY KEY, PAYLOAD_JSON CLOB NOT NULL, CONSTRAINT LVM_SET_JSON CHECK(PAYLOAD_JSON IS JSON WITH UNIQUE KEYS))",
 f"CREATE TABLE {s} (PUB_ID VARCHAR2(64 BYTE) NOT NULL, SEG_ID VARCHAR2(64 BYTE) NOT NULL, META_JSON CLOB NOT NULL, EMBEDDING VECTOR(*,FLOAT32) NOT NULL, CONSTRAINT LVM_ITEM_PK PRIMARY KEY(PUB_ID,SEG_ID), CONSTRAINT LVM_ITEM_FK FOREIGN KEY(PUB_ID) REFERENCES {r}(PUB_ID), CONSTRAINT LVM_ITEM_JSON CHECK(META_JSON IS JSON WITH UNIQUE KEYS))",
 f"CREATE INDEX {owner}.LGL_VCTR_ITEM_IX_S ON {s}(PUB_ID,{DOC},{SOURCE})",
 f"CREATE UNIQUE INDEX {owner}.LGL_VCTR_SET_ACT_IX_S ON {r}({ACTIVE_KEY})"]

def decode(value):
 if hasattr(value,'read'):value=value.read()
 return value if isinstance(value,dict) else json.loads(value)

class Repository:
 def __init__(self,sql,owner='SIDDS'):
  self.sql=sql;self.owner=owner;self.r=table('release',owner);self.s=table('segment',owner)
 def active(self,query_id):
  rows=self.sql.query(f'SELECT PUB_ID,{REVISION} AS REVISION FROM {self.r} WHERE {ACTIVE_KEY}=:q',[('q',query_id,'VARCHAR2')],limit=1)
  return rows[0] if rows else None
 def read(self,pub):
  rows=self.sql.query(f'SELECT PUB_ID,PAYLOAD_JSON FROM {self.r} WHERE PUB_ID=:p',[('p',pub,'VARCHAR2')],limit=1)
  if len(rows)!=1:raise VectorError('VECTOR_RELEASE: missing publication')
  payload=decode(rows[0]['PAYLOAD_JSON']);manifest=payload.get('manifest',{});config=profile(manifest.get('profile'))
  if (digest(manifest)!=pub or manifest.get('schema_version')!='legal-vector-publication-v1'
      or manifest.get('profile')!=config or payload.get('status') not in ('BUILDING','READY')
      or not re.fullmatch('[0-9a-f]{64}',str(manifest.get('query_id','')))):
   raise VectorError('VECTOR_RELEASE: manifest hash/binding/state')
  revision=payload.get('active_revision')
  if revision is not None and (type(revision) is not int or revision<1 or payload['status']!='READY'):
   raise VectorError('VECTOR_RELEASE: invalid active state')
  return {'PUB_ID':pub,'QUERY_ID':manifest['query_id'],'MANIFEST_JSON':manifest,'PROFILE_JSON':config,
          'STATUS':payload['status'],'LEASE_ID':payload.get('lease'),'PAYLOAD_JSON':payload}
 def search(self,pub,query,documents,source_ids=None,limit=100):
  if type(limit) is not int or not 1<=limit<=300:raise VectorError('VECTOR_LIMIT:1..300')
  if not documents or source_ids==[]:return []
  release=self.read(pub)
  if release['STATUS']!='READY':raise VectorError('VECTOR_RELEASE: not READY')
  expr=vector_sql(query,release['PROFILE_JSON']['dimensions'])
  binds=[('p',pub,'VARCHAR2')];where=['PUB_ID=:p']
  # Numeric-free quoted literals are SQL-generated from trusted scope using escaping;
  # bounded groups avoid ORDS CLOB bind fallback and Oracle IN1000 limits.
  def scope(column,values):
   values=sorted(set(values))
   if any(not isinstance(x,str) or not x or len(x.encode())>512 for x in values):raise VectorError('VECTOR_SCOPE: invalid ID')
   return '('+' OR '.join(column+' IN ('+','.join("'"+x.replace("'","''")+"'" for x in values[i:i+500])+')' for i in range(0,len(values),500))+')'
  where.append(scope(DOC,documents))
  if source_ids is not None:where.append(scope(SOURCE,source_ids))
  # Group before top-k: one long article cannot consume the root candidate budget.
  sql=f"SELECT {DOC} AS DOC_ID,{SOURCE} AS SOURCE_ID,MIN(VECTOR_DISTANCE(EMBEDDING,{expr},COSINE)) AS DISTANCE FROM {self.s} WHERE "+' AND '.join(where)+f' GROUP BY {DOC},{SOURCE} ORDER BY DISTANCE,DOC_ID,SOURCE_ID FETCH FIRST {limit} ROWS ONLY'
  rows=self.sql.query(sql,binds,limit=limit)
  if any(r['DOC_ID'] not in documents or source_ids is not None and r['SOURCE_ID'] not in source_ids or not math.isfinite(float(r['DISTANCE'])) for r in rows):raise VectorError('VECTOR_SCOPE: returned invalid row')
  return rows

class Retriever:
 def __init__(self,request,*,encoder_factory=Encoder,owner='SIDDS'):
  self.request=request;self.repo=Repository(request.sql,owner);self.encoder_factory=encoder_factory;self.pin=None;self.cache={}
 def search(self,question,documents,source_ids=None):
  documents=set(documents)
  if not documents<=self.request.sources.allowed:raise VectorError('VECTOR_SCOPE: cannot widen request')
  if self.pin is None:
   pointer=self.repo.active(self.request.release_id)
   if not pointer:raise VectorUnavailable('VECTOR_NOT_PUBLISHED: build selected source release first')
   release=self.repo.read(pointer['PUB_ID'])
   if release['STATUS']!='READY' or release['QUERY_ID']!=self.request.release_id:raise VectorError('VECTOR_RELEASE: wrong source/status')
   self.pin=(pointer,release)
  pointer,release=self.pin
  key=digest([question,sorted(documents),None if source_ids is None else sorted(source_ids),pointer])
  if key not in self.cache:
   enc=self.encoder_factory(release['PROFILE_JSON'],deadline=self.request.sql.deadline)
   q=enc.encode([question])[0]
   self.cache[key]={'publication_id':pointer['PUB_ID'],'revision':pointer['REVISION'],'rows':self.repo.search(pointer['PUB_ID'],q,documents,source_ids),'embedding_calls':enc.calls,'truncated':False}
   self.cache[key]['truncated']=len(self.cache[key]['rows'])==100
  return self.cache[key]
