from common import *
import sys,subprocess,secrets,sqlite3,traceback
f=read(DES/'freeze.json');C=ROOT/f['code_root'];assert all(sha(C/n)==h for n,h in f['files'].items())
sys.path[:0]=[str(C/'02_BACKEND'),str(Path(__file__).parent)]
from semantic_runtime.ontology_work.repository import Repository,TABLES
from semantic_runtime.ontology_work.workflow import Workflow
from semantic_runtime.ontology_work.store import DataikuFolderStore
from semantic_runtime.contracts import digest
from test_workflow import fixture,Folder
import oracledb
out=ART/'check-oracle.json';assert not out.exists()
info=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
assert info['Config']['Labels']['a8.task']=='legal-mapped-20261023'
assert info['HostConfig']['PortBindings']['1521/tcp']==[{'HostIp':'127.0.0.1','HostPort':'11524'}]
secret=dict(x.split('=',1) for x in info['Config']['Env'])['ORACLE_PASSWORD']
admin=oracledb.connect(dsn='127.0.0.1:11524/FREEPDB1',user='system',password=secret)
user='A8_ONT_'+secrets.token_hex(6).upper();password=secrets.token_hex(24);checks={};created=False
try:
 with admin.cursor() as c:
  c.execute('CREATE USER '+user+' IDENTIFIED BY "'+password+'" DEFAULT TABLESPACE USERS QUOTA 32M ON USERS');created=True
  c.execute('GRANT CREATE SESSION, CREATE TABLE TO '+user)
 def connect():return oracledb.connect(dsn='127.0.0.1:11524/FREEPDB1',user=user,password=password)
 repo=Repository(connect,dialect='oracle',owner=user);repo.initialize();checks['actual_oracle_ddl']=True
 work,p=fixture();current={digest(x['anchor']):x['text'] for x in work['originals']}
 w=Workflow(repo,DataikuFolderStore(Folder()),actor='local-oracle-test',source_reader=lambda a:current.get(digest(a)))
 row=w.save(work,p,bundle_id='cb-oracle');assert not repo.lookup(work['originals'][0]['anchor'],{'d'});checks['draft_excluded']=True
 w.review(row['bundle_id'],1,row['work_hash'],True,'합성 원문과 두 경로 확인');assert not repo.lookup(work['originals'][0]['anchor'],{'d'});checks['approval_not_published']=True
 receipt=w.publish(row['bundle_id'],1,row['work_hash'],0);assert receipt['active'];checks['transactional_publish']=True
 found=repo.lookup(work['originals'][0]['anchor'],{'d'});assert len(found)==1 and len(found[0]['context']['scenario_package']['paths'])==2;checks['clob_read_and_two_paths']=True
 assert not repo.lookup(work['originals'][0]['anchor'],set());checks['acl_excludes']=True
 assert w.publish(row['bundle_id'],1,row['work_hash'],0)['reused'];assert repo.head(row['bundle_id'])['sequence']==1;checks['idempotent_publish']=True
 repo.activate(row['bundle_id'],None,1,w.actor);assert not repo.lookup(work['originals'][0]['anchor'],{'d'});checks['withdraw']=True
 repo.activate(row['bundle_id'],receipt['publication_id'],2,w.actor);assert repo.lookup(work['originals'][0]['anchor'],{'d'});checks['rollback']=True
 with repo.session() as c:
  c.execute('SELECT COUNT(*) FROM '+user+'.LGL_ONT_PUB_A');assert c.fetchone()[0]==1
 checks['immutable_publication_history']=True
 result={'status':'complete','strict_success':True,'checks':checks,'model_calls':0,'database':'isolated loopback Oracle FREEPDB1','field_connection':False,'dataiku_stream_adapter':'local implementation, actual Oracle DB'}
except Exception as exc:
 result={'status':'failed','strict_success':False,'checks':checks,'error_type':type(exc).__name__,'error':str(exc),'model_calls':0};(ART/'oracle-failure.txt').write_text(traceback.format_exc())
finally:
 if created:
  with admin.cursor() as c:c.execute('DROP USER '+user+' CASCADE')
 admin.close()
put(out,result);print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if result['strict_success'] else 1)
