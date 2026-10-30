"""Load receipt -> pinned Oracle source -> GENOS embeddings -> silver publication."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

from semantic_runtime.initial_vector import Encoder, VectorError, endpoint, profile
from semantic_runtime.oracle_dp_io import SQL, digest
from semantic_runtime.oracle_query import Snapshot
from semantic_runtime.oracle_query_catalog import select_release
from semantic_runtime.oracle_query_request import _request
from semantic_runtime.oracle_silver_reads import rewrite
from semantic_runtime.physical_mapping import SchemaMap
from lawrag.pipeline.oracle_query_dataiku import DataikuClient
from .publisher import Publisher
from .schema import ensure, validate

MAX_SQL = 1000000
SQL_RESERVATION = 128
MAX_EMBED = 20000

def read_json(folder, path, *, optional=False):
    if optional and path.lstrip('/') not in {p.lstrip('/') for p in folder.list_paths_in_partition()}:
        return {}
    with folder.get_download_stream(path) as stream:
        raw = stream.read(1024*1024+1)
    if len(raw)>1024*1024:
        raise VectorError('VECTOR_STATE_SIZE')
    value = json.loads(raw)
    if not isinstance(value,dict):
        raise VectorError('VECTOR_STATE_OBJECT')
    return value

def completion(folder, variables):
    explicit = str(variables.get('LEGAL_VECTOR_LOAD_RECEIPT','')).strip().lstrip('/')
    paths = [p.lstrip('/') for p in folder.list_paths_in_partition() if p.lstrip('/').startswith('jobs/') and p.endswith('/complete.json')]
    if explicit:
        paths = [p for p in paths if p==explicit]
    qid = str(variables.get('LEGAL_VECTOR_QUERY_RELEASE','')).strip()
    matches = []
    for path in sorted(paths):
        receipt = read_json(folder,path)
        if receipt.get('status')!='COMPLETE' or receipt.get('oracle_written') is not True or receipt.get('target')!='SIDDS.*_S':
            continue
        if any(not re.fullmatch('[0-9a-f]{64}',str(receipt.get(k,''))) for k in ('query_release_id','source_release_id')):
            raise VectorError('VECTOR_LOAD_RECEIPT: invalid release identity')
        if not qid or receipt['query_release_id']==qid:
            matches.append((path,receipt))
    if len(matches)!=1:
        raise VectorError('VECTOR_LOAD_RECEIPT: exactly one completed 03 receipt required; set LEGAL_VECTOR_LOAD_RECEIPT to jobs/<job>/complete.json')
    path,value=matches[0]
    return path,value,digest(value)

class Checkpoint:
    """Reserve SQL calls durably in blocks before use; crashes never reset budget."""
    def __init__(self,folder,path,old):
        self.folder,self.path,self.value=folder,path,dict(old)
        self.upload_seconds=0.0
        self.uploads=0
    def save(self,values):
        self.value.update(values,updated_at=time.time())
        start=time.monotonic()
        self.folder.upload_stream(self.path,json.dumps(self.value,ensure_ascii=False).encode())
        self.upload_seconds+=time.monotonic()-start
        self.uploads+=1
    def sql(self,status,calls):
        if status=='STARTED' and calls>self.value.get('sql_reserved',0):
            reserve=min(MAX_SQL,((calls+SQL_RESERVATION-1)//SQL_RESERVATION)*SQL_RESERVATION)
            self.save({'sql_reserved':reserve,'sql_calls':calls})

def run(cfg, *, action='build'):
    import dataiku
    if action not in ('schema','check','build'):
        raise VectorError('VECTOR_ACTION')
    variables=dataiku.get_custom_variables()
    connection=variables.get('LEGAL_ORACLE_CONNECTION','AIDP')
    root=Path(__file__).resolve().parents[1]
    mapping=SchemaMap.load(root/'00_SYSTEM/ORACLE/physical_mapping.yaml')
    client=DataikuClient(dataiku.SQLExecutor2(connection=connection),connection,
                         dataiku.default_project_key(),schema_map=mapping)
    binding,_=client.identity()
    output=dataiku.Folder(cfg['output'])
    metrics={'sql_seconds':0.0,'embedding_seconds':0.0}
    class BuildSQL(SQL):
        def query(self,statement,binds=(),*,limit=100):
            return super().query(rewrite(statement,self.client.schema_map),binds,limit=limit)
        def request(self,*args,**kwargs):
            start=time.monotonic()
            try:return super().request(*args,**kwargs)
            finally:metrics['sql_seconds']+=time.monotonic()-start
    with tempfile.TemporaryDirectory(prefix='legal-vector-silver-') as tmp:
        if action=='schema':
            sql=BuildSQL(client,journal=Path(tmp)/'sql.jsonl',binding=binding,seconds=600)
            result=ensure(sql)
            output.upload_stream('/schema-check.json',json.dumps(result).encode())
            print('VECTOR_SCHEMA_OK',result)
            return result
        for key in ('GENOS_BASE_URL','GENOS_EMBED_SERVING_ID','GENOS_EMBED_KEY','GENOS_EMBED_URL'):
            if variables.get(key):os.environ[key]=str(variables[key])
            else:os.environ.pop(key,None)
        config=variables.get('LEGAL_VECTOR_PROFILE')
        if isinstance(config,str):config=json.loads(config)
        config=profile(config)
        if hashlib.sha256(endpoint().encode()).hexdigest()!=config['endpoint_sha256']:
            raise VectorError('VECTOR_BINDING: query/build endpoint differs')
        receipt_path,receipt,receipt_hash=completion(dataiku.Folder(cfg['load']),variables)
        work=digest([receipt['query_release_id'],config])
        history='/vector/'+work+'/build-state.json'
        old=read_json(output,history,optional=True)
        if not old and cfg.get('legacy'):
            legacy=read_json(dataiku.Folder(cfg['legacy']),'/vector/build-state.json',optional=True)
            if legacy.get('work_key')==work:
                old={**legacy,'migrated_from':'LEGAL_VECTOR_RESULT_R1',
                     'sql_reserved':legacy.get('sql_calls',0)}
        if old and (old.get('target_binding')!=binding or old.get('work_key')!=work):
            raise VectorError('VECTOR_RESUME: target/source/profile differs')
        if old.get('receipt_sha256') not in (None,receipt_hash):
            raise VectorError('VECTOR_RESUME: upstream receipt changed')
        start=old.get('started_at',time.time())
        deadline=start+7*24*3600
        if time.time()>=deadline:
            raise VectorError('VECTOR_BUDGET: original seven-day deadline exceeded')
        state=Checkpoint(output,history,{**old,'target_binding':binding,'work_key':work,'started_at':start,
                                        'receipt_path':receipt_path,'receipt_sha256':receipt_hash})
        sql=BuildSQL(client,journal=Path(tmp)/'sql.jsonl',binding=binding,max_calls=MAX_SQL,seconds=deadline-time.time(),
                     progress=state if action=='build' else None)
        sql.calls=max(old.get('sql_calls',0),old.get('sql_reserved',0))
        model_start=old.get('embedding_calls',0)
        enc=None
        started=time.monotonic()
        try:
            schema=validate(sql)
            selection=select_release(sql,release_id=receipt['query_release_id'],channel=None)
            manifest=selection['manifest']
            snapshot=Snapshot.open(sql,manifest['source_release_id'])
            if (manifest['source_release_id']!=receipt['source_release_id'] or snapshot.dataset_version!=manifest['dataset_version']
                    or snapshot.manifest!=manifest['source_manifest'] or 'source.integrity' not in manifest['tables']):
                raise VectorError('VECTOR_SOURCE: completion/source/query mismatch')
            docs=set(snapshot.manifest['scope']['document_version_ids'])-snapshot.excluded
            request=_request(sql,selection['release_id'],selection['revision'],snapshot,manifest,docs)
            enc=Encoder(config,deadline=sql.deadline)  # validates credential presence; no HTTP in check
            if action=='check':
                result={'status':'CHECKED','schema':schema,'query_release_id':request.release_id,
                        'source_release_id':snapshot.release_id,'documents':len(docs),'embedding_calls':0,
                        'receipt_path':receipt_path,'receipt_sha256':receipt_hash}
                output.upload_stream('/check-'+work+'.json',json.dumps(result).encode())
                print('VECTOR_CHECK_OK',request.release_id,'documents',len(docs))
                return result
            state.save({'status':'PREPARING','query_release_id':request.release_id,'sql_calls':sql.calls})
            encode=enc.encode
            def bounded_encode(texts):
                if model_start+enc.calls>=MAX_EMBED:
                    raise VectorError('VECTOR_BUDGET: embedding request cap')
                state.save({'embedding_calls':model_start+enc.calls+1,'status':'EMBEDDING_RESERVED'})
                began=time.monotonic()
                try:return encode(texts)
                finally:metrics['embedding_seconds']+=time.monotonic()-began
            enc.encode=bounded_encode
            def progress(value):
                value=dict(value)
                value['embedding_calls']=max(state.value.get('embedding_calls',0),model_start+enc.calls)
                value['sql_calls']=sql.calls
                state.save(value)
            result=Publisher(request,config,encoder=enc,save=progress).build()
            result.update(embedding_calls=model_start+enc.calls,sql_calls=sql.calls,
                          receipt_path=receipt_path,receipt_sha256=receipt_hash)
            state.save(result)
            print('VECTOR_READY',result['publication_id'],'query',result['query_release_id'],'segments',result['count'])
            return result
        except BaseException as exc:
            if action=='build':
                state.save({'status':'FAILED','error_type':type(exc).__name__,'sql_calls':sql.calls,
                            'embedding_calls':max(state.value.get('embedding_calls',0),model_start+(enc.calls if enc else 0))})
            raise
        finally:
            # Timings overlap: SQL includes reservation uploads. Do not sum as independent spans.
            stamp=str(int(time.time()*1000))+'-'+uuid.uuid4().hex[:8]
            log=Path(tmp)/'sql.jsonl'
            if log.exists():
                with log.open('rb') as stream:output.upload_stream('/vector/'+work+'/sql-'+stamp+'.jsonl',stream)
            observation={**metrics,'elapsed_seconds':time.monotonic()-started,'state_upload_seconds':state.upload_seconds,
                         'state_uploads':state.uploads,'sql_calls_this_attempt':sql.calls-max(old.get('sql_calls',0),old.get('sql_reserved',0)),
                         'note':'sql_seconds includes reservation upload time; overlapping spans, do not add',
                         'action':action,'execution_context':'Dataiku recipe; host identity requires external verification'}
            output.upload_stream('/vector/'+work+'/timing-'+stamp+'.json',json.dumps(observation).encode())
