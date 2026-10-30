from pathlib import Path
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_1164/integrated/snapshot';D=S/'08_DEPLOYMENT/DATAIKU/vector_initial_20261028_r1';D.mkdir(parents=True,exist_ok=True)
(D/'run_recipe.py').write_text('''"""Run on Dataiku only. Existing Oracle source publication -> native vectors."""
from pathlib import Path
import hashlib,json,os,tempfile,time,traceback

def run(output_folder_id,*,action='build'):
 import dataiku
 from lawrag.pipeline.oracle_query_dataiku import DataikuClient
 from semantic_runtime.physical_mapping import SchemaMap
 from semantic_runtime.oracle_dp_io import SQL,digest
 from semantic_runtime.oracle_silver_reads import rewrite
 from semantic_runtime.oracle_query_catalog import select_release
 from semantic_runtime.oracle_query import Snapshot
 from semantic_runtime.oracle_query_request import _request
 from semantic_runtime.initial_vector import ddl,profile,endpoint,Repository,VectorError
 from semantic_runtime.vector_publish import Publisher
 root=Path(__file__).resolve().parents[3];variables=dataiku.get_custom_variables();folder=dataiku.Folder(output_folder_id)
 # Reuse existing project Oracle connection; never print variables/tokens.
 connection=variables.get('LEGAL_ORACLE_CONNECTION','AIDP')
 mapping=SchemaMap.load(root/'00_SYSTEM/ORACLE/physical_mapping.yaml')
 client=DataikuClient(dataiku.SQLExecutor2(connection=connection),connection,dataiku.default_project_key(),schema_map=mapping)
 binding,_=client.identity()
 config=variables.get('LEGAL_VECTOR_PROFILE')
 if isinstance(config,str):config=json.loads(config)
 config=profile(config)
 for key in ('GENOS_BASE_URL','GENOS_EMBED_SERVING_ID','GENOS_EMBED_KEY','GENOS_EMBED_URL'):
  if variables.get(key):os.environ[key]=str(variables[key])
 if hashlib.sha256(endpoint().encode()).hexdigest()!=config['endpoint_sha256']:raise VectorError('VECTOR_PROFILE: query/build endpoint binding differs')
 class BuildSQL(SQL):
  def query(self,statement,binds=(),*,limit=100):return super().query(rewrite(statement,self.client.schema_map),binds,limit=limit)
 history='/vector/build-state.json'
 try:
  with folder.get_download_stream(history) as stream:old=json.load(stream)
 except Exception as exc:
  # Absence only, never silently replace unreadable saved state.
  paths=folder.list_paths_in_partition()
  if history in paths or history.lstrip('/') in paths:raise
  old={}
 if old and old.get('target_binding')!=binding:raise VectorError('VECTOR_RESUME: target connection changed')
 start=old.get('started_at',time.time());deadline=start+7*24*3600
 if time.time()>=deadline:raise VectorError('VECTOR_BUDGET: original seven-day build deadline exceeded')
 with tempfile.TemporaryDirectory(prefix='legal-vector-dataiku-') as tmp:
  sql=BuildSQL(client,journal=Path(tmp)/'sql.jsonl',binding=binding,max_calls=1000000,seconds=deadline-time.time());sql.calls=old.get('sql_calls',0)
  state={**old,'target_binding':binding,'started_at':start,'status':'PREPARING'}
  def save(values):
   state.update(values,sql_calls=sql.calls,updated_at=time.time())
   folder.upload_stream(history,json.dumps(state,ensure_ascii=False).encode())
  try:
   # DDL is Dataiku-owned and idempotent. Existing objects are validated by
   # successful typed insert/read and Oracle constraints, never dropped/recreated.
   for statement in ddl():
    sql.request("BEGIN EXECUTE IMMEDIATE '"+statement.replace("'","''")+"'; EXCEPTION WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF; END;",write=True)
   qid=variables.get('LEGAL_VECTOR_QUERY_RELEASE') or None
   selection=select_release(sql,release_id=qid,channel=None if qid else 'main')
   manifest=selection['manifest'];snapshot=Snapshot.open(sql,manifest['source_release_id'])
   if snapshot.dataset_version!=manifest['dataset_version'] or snapshot.manifest!=manifest['source_manifest']:raise VectorError('VECTOR_SOURCE: query/source release mismatch')
   docs=set(snapshot.manifest['scope']['document_version_ids'])-snapshot.excluded
   request=_request(sql,selection['release_id'],selection['revision'],snapshot,manifest,docs)
   work=digest([request.release_id,config])
   if old.get('work_key') not in (None,work):raise VectorError('VECTOR_RESUME: different source/profile; archive prior job state before starting a new build')
   save({'work_key':work,'query_release_id':request.release_id})
   if action=='check':save({'status':'CHECKED','documents':len(docs)});return state
   if action!='build':raise VectorError('VECTOR_ACTION: expected build/check')
   from semantic_runtime.initial_vector import Encoder
   enc=Encoder(config,deadline=sql.deadline)
   previous_calls=old.get('embedding_calls',0)
   real_encode=enc.encode
   def encode(texts):
    if previous_calls+enc.calls>=20000:raise VectorError('VECTOR_BUDGET: total physical embedding request cap reached')
    save({'embedding_calls':previous_calls+enc.calls+1,'status':'EMBEDDING_RESERVED'})
    return real_encode(texts)
   enc.encode=encode
   def progress(value):
    value=dict(value);value['embedding_calls']=previous_calls+enc.calls;save(value)
   result=Publisher(request,config,encoder=enc,save=progress).build()
   print('VECTOR_READY',result['publication_id'],'segments',result['count'],'GENOS는 같은 query release를 선택해야 합니다.')
   return result
  except BaseException as exc:
   save({'status':'FAILED','error_type':type(exc).__name__})
   raise
  finally:
   if (Path(tmp)/'sql.jsonl').exists():folder.upload_stream('/vector/sql-'+str(int(time.time()*1000))+'.jsonl',(Path(tmp)/'sql.jsonl').read_bytes())
''')
(D/'install_flow.py').write_text('''"""One installation cell adds a single Python Flow recipe, not a new project."""
import json

def install(project,bootstrap,landing_id='ehA8dpVm'):
 name='LEGAL_VECTOR_RESULT_R1';recipe_name='LEGAL_04_VECTOR_INITIAL_R1'
 source=project.get_managed_folder(landing_id).get_settings();params=source.get_raw_params()
 if source.type!='S3':raise ValueError('Landing must be the existing Dataiku S3 folder')
 found=[r for r in project.list_managed_folders() if r['name']==name]
 if len(found)>1:raise ValueError('duplicate vector result folders')
 path='/LEGAL_RAG/vector_initial_20261028_r1/results'
 if found:
  folder=project.get_managed_folder(found[0]['id']);settings=folder.get_settings();current=settings.get_raw_params()
  if settings.type!='S3' or any(current.get(k)!=v for k,v in {'connection':params['connection'],'bucket':params.get('bucket'),'path':path}.items()):raise ValueError('existing vector folder differs; preserved')
 else:
  folder=project.create_managed_folder(name,folder_type='S3',connection_name=params['connection']);settings=folder.get_settings();v=settings.get_raw_params();v['path']=path
  if 'bucket' in params:v['bucket']=params['bucket']
  settings.save()
 code=bootstrap+'\\nfrom run_recipe import run\\nrun('+repr(folder.id)+')\\n'
 recipes={r['name'] for r in project.list_recipes()}
 if recipe_name in recipes:
  settings=project.get_recipe(recipe_name).get_settings()
  if settings.get_code()!=code or set(settings.get_flat_input_refs())!={landing_id} or set(settings.get_flat_output_refs())!={folder.id}:raise ValueError('existing vector recipe differs; preserved')
 else:
  recipe=project.new_recipe('python',recipe_name).with_input(landing_id).with_output(folder.id,append=True).with_script(code).create();settings=recipe.get_settings();settings.set_code_env(inherit=True);settings.save()
 print('설치 완료: LEGAL_04_VECTOR_INITIAL_R1 Run. 구조화/실버 게시가 완료된 release만 읽습니다.')
 return {'recipe':recipe_name,'output':folder.id}
''')
# Dataiku/JDBC does not accept CLOB query binds. Preserve literal boundaries and
# SQL typing while allowing bounded CLOB expressions in reads (not interpolation).
p=S/'02_BACKEND/lawrag/pipeline/oracle_query_dataiku.py';t=p.read_text();t=t.replace("            if not write or not isinstance(value,str):raise DPError('JDBC_CLOB: CLOB only in write blocks')", "            if not isinstance(value,str):raise DPError('JDBC_CLOB: expected string')\n            if not write:\n                values[name]=' || '.join('TO_CLOB('+literal(value[j:j+900])+')' for j in range(0,len(value),900)) if value else \"TO_CLOB('')\"\n                continue");p.write_text(t)
p=S/'02_BACKEND/semantic_runtime/oracle_silver_reads.py';t=p.read_text().replace("'SIDDA.LEGAL_RAG_SOURCE_RELEASE_A':'source_release'","'SIDDA.LEGAL_RAG_RELEASE_A':'source_release'");p.write_text(t)
