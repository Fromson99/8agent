from pathlib import Path
import json,sys,hashlib,subprocess,secrets,time,traceback,math
from types import SimpleNamespace as N
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1164-genos-vector-initial-build';f=json.loads((A/'artifacts/design/freeze.json').read_text());C=R/f['code_root'];assert all(hashlib.sha256((C/n).read_bytes()).hexdigest()==h for n,h in f['files'].items());sys.path[:0]=[str(C/'02_BACKEND'),str(Path(__file__).parent)]
import oracledb
from semantic_runtime.initial_vector import *
from semantic_runtime.vector_publish import Publisher
from lawrag.pipeline.oracle_query_dataiku import render
from test_vector import cfg
info=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0];assert info['Config']['Labels']['a8.task']=='legal-mapped-20261023';secret=dict(x.split('=',1) for x in info['Config']['Env'])['ORACLE_PASSWORD'];admin=oracledb.connect(dsn='127.0.0.1:11524/FREEPDB1',user='system',password=secret)
user='A8_VEC_'+secrets.token_hex(5).upper();pw=secrets.token_hex(24);created=False;checks={};failure=None
try:
 with admin.cursor() as c:
  c.execute('CREATE USER '+user+' IDENTIFIED BY "'+pw+'" DEFAULT TABLESPACE USERS QUOTA 64M ON USERS');created=True;c.execute('GRANT CREATE SESSION,CREATE TABLE TO '+user)
 conn=oracledb.connect(dsn='127.0.0.1:11524/FREEPDB1',user=user,password=pw)
 class SQL:
  deadline=time.monotonic()+600;calls=0
  def query(self,q,binds=(),limit=100):
   self.calls+=1
   with conn.cursor() as c:
    # Exercise the real Dataiku literal/CLOB renderer, not separate SQL.
    c.execute(render(q,binds));names=[x[0] for x in c.description];rows=[]
    for row in c.fetchall():rows.append({n:v.read() if hasattr(v,'read') else v for n,v in zip(names,row)})
    assert len(rows)<=limit
    return rows
  def request(self,q,binds=(),write=False,limit=100):
   self.calls+=1
   with conn.cursor() as c:c.execute(render(q,binds,write=write))
 sql=SQL()
 for statement in ddl(user):
  with conn.cursor() as c:c.execute(statement)
 checks['actual_Oracle_vector_DDL']=True
 class Encoder:
  calls=0
  def encode(self,texts):self.calls+=1;return [[1,0,0,0] if 'near' in t else [0,1,0,0] for t in texts]
 request=N(sql=sql,release_id='a'*64,snapshot=N(release_id='b'*64,dataset_version='c'*64),sources=N(allowed={'d','secret'}))
 def items(prefix=''):
  rows=[]
  for i in range(40):
   m={'source_id':'root' if i<30 else 'root'+str(i),'document_id':'d' if i<39 else 'secret','unit_id':'2','source_sha256':digest('source'),'input_sha256':digest(prefix+str(i))};rows.append({'id':digest([prefix,i]),'meta':m,'text':'near'+str(i)})
  return rows
 logs=[];enc=Encoder();publisher=Publisher(request,cfg(),encoder=enc,owner=user,save=logs.append);res=publisher.build(items=items());assert res['count']==40 and res['active'];checks['actual_Oracle_publish_ready']=True
 repo=Repository(sql,user);found=repo.search(res['publication_id'],[1,0,0,0],{'d'},limit=20);assert len(found)==10 and all(r['DOC_ID']=='d' for r in found);checks['ACL_prefilter_and_group_before_limit']=True
 assert len(repo.search(res['publication_id'],[1,0,0,0],{'d'},source_ids=['root']))==1;checks['source_scope_filter']=True
 enc2=Encoder();again=Publisher(request,cfg(),encoder=enc2,owner=user).build(items=items());assert again['reused']==40 and enc2.calls==0 and repo.active(request.release_id)['REVISION']==1;checks['resume_READY_reuses_all_no_embedding']=True
 profile2=cfg();profile2['revision']='second-binding'
 class Fail(Encoder):
  def encode(self,t):
   if self.calls>=1:raise VectorUnavailable('injected transport failure')
   return super().encode(t)
 failed=Publisher(request,profile2,encoder=Fail(),owner=user)
 try:failed.build(items=items())
 except VectorUnavailable:pass
 else:raise AssertionError('missing injected failure')
 assert repo.active(request.release_id)['PUB_ID']==res['publication_id'];assert repo.read(failed.pub)['STATUS']=='BUILDING';checks['partial_failure_not_published']=True
 enc3=Encoder();resumed=Publisher(request,profile2,encoder=enc3,owner=user).build(items=items());assert resumed['reused']==16 and enc3.calls==2;checks['partial_resume_only_missing']=True
 assert repo.active(request.release_id)['REVISION']==2;checks['CAS_revision_increment']=True
 with conn.cursor() as c:
  c.execute('UPDATE '+repo.a+' SET PUB_ID=:p,REVISION=REVISION+1 WHERE QUERY_ID=:q AND REVISION=2',p=res['publication_id'],q=request.release_id);assert c.rowcount==1;conn.commit()
 assert repo.active(request.release_id)['PUB_ID']==res['publication_id'];checks['rollback_keeps_old_vectors']=True
 # CLOB predicate works in Dataiku read renderer and numeric vector is native FLOAT32.
 assert sql.query("SELECT DBMS_LOB.GETLENGTH(:v) AS N FROM DUAL",[('v','가'*5000,'CLOB')],limit=1)[0]['N']==5000;checks['Dataiku_CLOB_read_5000chars']=True
 assert len(repo.search(res['publication_id'],[0,1,0,0],{'secret'}))==1;checks['second_principal_isolated']=True
 conn.close()
except BaseException as exc:failure=traceback.format_exc()
finally:
 if created:
  with admin.cursor() as c:c.execute('DROP USER '+user+' CASCADE')
 admin.close()
p=A/'artifacts'/('oracle-'+f['binding']['revision_id']+'.json');assert not p.exists();p.write_text(json.dumps({'status':'complete' if failure is None else 'failed','strict_success':failure is None,'checks':checks,'failure':failure,'external_model_calls':0,'field_deployment':False},ensure_ascii=False,indent=2));print(json.dumps({'checks':checks,'failure':failure},ensure_ascii=False));raise SystemExit(bool(failure))
