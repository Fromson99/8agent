"""Dataiku owns durable lifecycle, byte receipts, cancellation and publication."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
import time
import uuid
import recipes_runtime as r
import transport as t
from managed_job import ManagedJob, BudgetClient, bounded_read

PROTOCOL = 'dataiku-owned-compute-v1'
NAMESPACE = '_pipeline/dataiku-owned-v1/'
EXPECTED = (Path(__file__).parent/'COMPUTE_CODE_SHA256.txt').read_text().strip()


class Scope:
    def __init__(self, folder): self.folder=folder
    def list_paths_in_partition(self):
        return ['/'+p.lstrip('/')[len(NAMESPACE):] for p in self.folder.list_paths_in_partition()
                if p.lstrip('/').startswith(NAMESPACE)]
    def get_download_stream(self, name): return self.folder.get_download_stream(NAMESPACE+name.lstrip('/'))
    def upload_stream(self,name,stream): return self.folder.upload_stream(NAMESPACE+name.lstrip('/'),stream)


class Wire(r.CheckedClient):
    def call(self, operation, **fields):
        # Parent already enforces TLS, no redirects, bounded replies and no HTTP retry.
        return super().call(operation, **fields)


def remote(variables):
    for key in ('LEGAL_PIPELINE_URL','LEGAL_PIPELINE_TOKEN'):
        if not isinstance(variables.get(key),str) or not variables[key].strip():
            raise ValueError('PROJECT_VARIABLE_REQUIRED: '+key)
    return Wire(variables['LEGAL_PIPELINE_URL'],variables['LEGAL_PIPELINE_TOKEN'])


def health(remote):
    value=remote.call('HEALTH')
    if value.get('code_sha256') != EXPECTED or value.get('protocol') != PROTOCOL:
        raise ValueError('STATELESS_COMPUTE_DEPLOYMENT_REQUIRED')
    if value.get('s3_access') is not False or value.get('durable_jobs') is not False or not value.get('cancel_supported'):
        raise ValueError('COMPUTE_CONTRACT')
    if not re.fullmatch('[0-9a-f]{32}',value.get('instance','')):
        raise ValueError('COMPUTE_INSTANCE')
    return value


def legacy_state(folder,job_name):
    """Read old history only. Never contact or ACK an old GENOS job."""
    prefix='_pipeline/jobs/'+job_name+'/checkpoint-'
    rows=[]
    for path in folder.list_paths_in_partition():
        name=path.lstrip('/')
        if not name.startswith(prefix): continue
        match=re.fullmatch(re.escape(prefix)+r'(\d{10})-([0-9a-f]{64})\.json',name)
        if not match: raise ValueError('LEGACY_CHECKPOINT_NAME')
        rows.append((int(match[1]),match[2],path))
    if not rows: return None
    seq,sha,path=max(rows)
    if sum(s==seq for s,_,_ in rows)!=1: raise ValueError('LEGACY_CONCURRENT_CHECKPOINT')
    with folder.get_download_stream(path) as stream: raw=bounded_read(stream,t.CHUNK)
    if hashlib.sha256(raw).hexdigest()!=sha: raise ValueError('LEGACY_CHECKPOINT_HASH')
    return {'sha256':sha,'path':path,'value':json.loads(raw)}


def open_store(folder,name,identity):
    store=ManagedJob(Scope(folder),name,identity)
    if 'migration_checked' not in store.value:
        old=legacy_state(folder,name)
        if old:
            v=old['value']; prior=v['binding']
            if prior['input'] != identity['input'] or prior['database'] != identity['database'] or prior['service_url_sha256'] != identity['service_url_sha256']:
                raise ValueError('LEGACY_INPUT_OR_TARGET_CHANGED')
            if v.get('result_blob') or v.get('phase') in {'STRUCTURED','COMPLETE','LOAD_VERIFIED'}:
                raise ValueError('LEGACY_RETURN_EXISTS_PRESERVE_AND_LOAD_OLD_RESULT')
            store.value.update(deadline=v['deadline'],reserved_sql_calls=v['reserved_sql_calls'],
                legacy_checkpoint={'path':old['path'],'sha256':old['sha256'],'phase':v.get('phase'),
                                   'remote_state':'NOT_QUERIED'})
        store.value['migration_checked']=True
        store.save()
    return store


def context(cfg,receipts,variables):
    # Reuse the exact split-layer Oracle mapping and target identity implementation.
    oracle,binding,_,identity=r.context(cfg,receipts,variables)
    identity={**identity,'version':PROTOCOL,'service_code':EXPECTED}
    return oracle,binding,remote(variables),identity


def budget_call(store,wire,op,**fields):
    if op not in ('CANCEL','CLOSE') and time.time()>=store.value['deadline']:
        raise ValueError('ORIGINAL_DEADLINE_EXHAUSTED')
    count=store.value.get('reserved_http_calls',0)
    if count>=1000000: raise ValueError('HTTP_BUDGET_EXHAUSTED')
    # Reserve small blocks in S3; restarting can only spend the remaining budget.
    local=getattr(store,'http_credit',0)
    if not local:
        grant=min(64,1000000-count)
        store.value['reserved_http_calls']=count+grant;store.save();store.http_credit=grant
    store.http_credit-=1
    return wire.call(op,**fields)


def auth(state):
    return {k:state[k] for k in ('instance','handle','handle_token','code_sha256')}


def save_chunk(store,path,block):
    digest=hashlib.sha256(block).hexdigest()
    names={x.lstrip('/') for x in store.folder.list_paths_in_partition()}
    if path not in names:
        store.folder.upload_stream(path,io.BytesIO(block))
    with store.folder.get_download_stream(path) as f: actual=bounded_read(f,len(block))
    if actual!=block: raise ValueError('DATAIKU_CHUNK_READBACK')
    return {'path':path,'bytes':len(block),'sha256':digest}


def read_chunk(store,wire,state,kind,offset):
    response=budget_call(store,wire,'READ',**auth(state),kind=kind,offset=offset)
    try: block=base64.b64decode(response['content'],validate=True)
    except Exception: raise ValueError('RETURN_CHUNK_ENCODING') from None
    if (response['offset']!=offset or response['bytes']!=len(block) or len(block)>t.CHUNK
            or hashlib.sha256(block).hexdigest()!=response['sha256']):
        raise ValueError('RETURN_CHUNK_HASH')
    return block


def drain_log(store,wire,state,total):
    offset=store.value.get('log_offset',0)
    while offset<total:
        block=read_chunk(store,wire,state,'log',offset)
        if not block: raise ValueError('EMPTY_LOG_CHUNK')
        path='attempts/'+state['handle']+'/logs/'+str(offset).zfill(16)+'.log'
        save_chunk(store,path,block)
        offset+=len(block)
        store.value['log_offset']=offset;store.save()


def cancelled(store,name):
    path='controls/'+name+'/cancel.json'
    if path not in {p.lstrip('/') for p in store.folder.list_paths_in_partition()}: return False
    record=r.read_json(store.folder,path,t.CHUNK)
    return record.get('handle')==store.value.get('compute',{}).get('handle')


def transfer_inputs(store,wire,state,landing,receipts,current):
    for slot,name in [('raw','RAW_INPUT.zip'),('support','PIPELINE_SUPPORT.zip')]:
        receipt=receipts[name];offset=current['received'][slot]
        # No raw extraction/materialization or repacking on Dataiku. Only a 1 MiB buffer.
        h=hashlib.sha256();position=0
        with landing.get_download_stream(receipt['remote']) as source:
            while True:
                block=source.read(t.CHUNK)
                if not block: break
                if position+len(block)>receipt['bytes']: raise ValueError('INPUT_SIZE')
                h.update(block)
                if position+len(block)>offset:
                    start=max(0,offset-position);part=block[start:]
                    current=budget_call(store,wire,'PUT',**auth(state),slot=slot,offset=position+start,
                        content=base64.b64encode(part).decode(),sha256=hashlib.sha256(part).hexdigest())
                    if current['received'][slot]!=position+len(block): raise ValueError('UPLOAD_OFFSET')
                position+=len(block)
                if cancelled(store,store.name): raise InterruptedError('CANCEL_REQUESTED')
        if position!=receipt['bytes'] or h.hexdigest()!=receipt['sha256']: raise ValueError('INPUT_HASH')
        print('INPUT_TRANSFERRED',name,position,flush=True)
    return current


def collect_result(store,wire,state,result,work):
    prefix='attempts/'+state['handle']+'/result/'
    receipt_path=prefix+'receipt.json'
    prior=store.value.get('return_receipt')
    if prior and prior!=result: raise ValueError('RETURN_CHANGED')
    if not prior:
        store.value['return_receipt']=result;store.save()
        r.put_json(store.folder,receipt_path,result,work)
    # Chunk objects are immutable; a local file loss resumes from Dataiku S3.
    offset=0;whole=hashlib.sha256();target=work/'result.zip'
    known={p.lstrip('/') for p in store.folder.list_paths_in_partition()}
    with target.open('wb') as output:
        while offset<result['bytes']:
            path=prefix+str(offset).zfill(16)+'.chunk'
            meta_path=path+'.json'
            if meta_path in known:
                meta=r.read_json(store.folder,meta_path,t.CHUNK)
                with store.folder.get_download_stream(path) as f: block=bounded_read(f,t.CHUNK)
                if meta != {'path':path,'bytes':len(block),'sha256':hashlib.sha256(block).hexdigest()}:
                    raise ValueError('RESULT_CHUNK_CHANGED')
            else:
                block=read_chunk(store,wire,state,'result',offset)
                if not block: raise ValueError('EMPTY_RESULT_CHUNK')
                meta=save_chunk(store,path,block)
                r.put_json(store.folder,meta_path,meta,work)
            if offset+len(block)>result['bytes']: raise ValueError('RESULT_SIZE')
            output.write(block);whole.update(block);offset+=len(block)
    if whole.hexdigest()!=result['sha256']: raise ValueError('RESULT_ARCHIVE_HASH')
    # Authoritative reusable artifact is published only after whole-archive verification.
    store.value.update(result_blob=store.put_blob(target),phase='STRUCTURED')
    store.save()


def structured_record(store):
    return {'status':'STRUCTURED','state_sha256':t.digest(store.value),'binding':store.value['binding'],
            'result_blob':store.value['result_blob'],'deadline':store.value['deadline'],'oracle_written':False}


def apply_retry(store,name,work):
    path='controls/'+name+'/retry.json'
    if path not in {p.lstrip('/') for p in store.folder.list_paths_in_partition()}:return
    marker=r.read_json(store.folder,path,t.CHUNK)
    current=store.value.get('compute',{}).get('handle')
    if marker.get('handle')!=current:return
    if store.value.get('phase') not in {'FAILED','CANCELLED'}:
        raise ValueError('RETRY_REQUIRES_CONFIRMED_TERMINAL')
    count=store.value.get('attempt_count',1)
    if count>=3:raise ValueError('COMPUTE_ATTEMPT_BUDGET_EXHAUSTED')
    if time.time()>=store.value['deadline']:raise ValueError('ORIGINAL_DEADLINE_EXHAUSTED')
    r.put_json(store.folder,'attempts/'+current+'/controller-checkpoint.json',store.value,work)
    keep={k:v for k,v in store.value.items() if k in
          {'binding','deadline','reserved_sql_calls','reserved_http_calls','migration_checked','legacy_checkpoint'}}
    keep.update(phase='NEW',attempt_count=count+1,previous_handle=current)
    store.value=keep;store.save()


def structure(cfg,folders,variables,work,name):
    receipts=r.input_receipts(folders['landing'])
    oracle,binding,wire,identity=context(cfg,receipts,variables)
    store=open_store(folders['structured'],name,identity);store.name=name
    apply_retry(store,name,work)
    if store.value.get('phase')=='STRUCTURED':
        record=structured_record(store)
        r.put_json(store.folder,'jobs/'+name+'/structured.json',record,work)
        return {'status':'STRUCTURED','reused':True}
    if store.value.get('phase') in {'FAILED','CANCELLED','HANDLE_LOST'}:
        raise ValueError('ATTEMPT_'+store.value['phase']+'_PRESERVED')
    state=store.value.get('compute')
    try:
        if not state:
            h=health(wire)
            r.raw_manifest(folders['raw'],receipts['RAW_INPUT.zip'])
            from semantic_runtime import oracle_dp_io as dbio
            oracle.schema_map.preflight(dbio.SQL(BudgetClient(oracle,store),journal=work/'preflight.jsonl',binding=binding))
            state={'handle':uuid.uuid4().hex,'handle_token':secrets.token_hex(32),'instance':h['instance'],
                   'code_sha256':EXPECTED,'archives':{
                       slot:{k:receipts[n][k] for k in ('sha256','bytes')}
                       for slot,n in [('raw','RAW_INPUT.zip'),('support','PIPELINE_SUPPORT.zip')]}}
            store.value.update(compute=state,phase='OPEN_INTENT');store.save()
        if store.value['phase']=='OPEN_INTENT':
            current=budget_call(store,wire,'OPEN',**auth(state),archives=state['archives'],deadline=store.value['deadline'])
        else:
            current=budget_call(store,wire,'POLL',**auth(state))
        if cancelled(store,name) and current['state'] in {'RECEIVING','RUNNING'}:
            current=budget_call(store,wire,'CANCEL',**auth(state))
        if current['state']=='RECEIVING':
            store.value['phase']='TRANSFERRING';store.save()
            current=transfer_inputs(store,wire,state,folders['landing'],receipts,current)
            store.value['phase']='RUN_INTENT';store.save()
            current=budget_call(store,wire,'RUN',**auth(state))
        previous=None
        while True:
            phase=current['state']+'/'+current.get('phase','')
            if phase!=previous:
                print('COMPUTE',phase,flush=True);previous=phase
                store.value.update(phase='COMPUTING',last_observed=current);store.save()
            drain_log(store,wire,state,current['log_bytes'])
            if current['state']!='RUNNING': break
            if cancelled(store,name):
                store.value['phase']='CANCEL_REQUESTED';store.save()
                current=budget_call(store,wire,'CANCEL',**auth(state))
            time.sleep(3)
            current=budget_call(store,wire,'POLL',**auth(state))
        if current['state']!='COMPLETE':
            store.value.update(phase=current['state'],last_observed=current);store.save()
            budget_call(store,wire,'CLOSE',**auth(state))
            raise ValueError('COMPUTE_'+current['state'])
        collect_result(store,wire,state,current['result'],work)
        # Release only temporary transfer storage. No job ACK or workflow state in GENOS.
        try: budget_call(store,wire,'CLOSE',**auth(state),result_sha256=current['result']['sha256'])
        except Exception: print('TEMP_RELEASE_UNCONFIRMED; lease expiry will reclaim it',flush=True)
        r.put_json(store.folder,'jobs/'+name+'/structured.json',structured_record(store),work)
        return {'status':'STRUCTURED','oracle_written':False,'logs':'Dataiku managed folder'}
    except BaseException as exc:
        if isinstance(exc,(KeyboardInterrupt,InterruptedError)) or str(exc)=='ORIGINAL_DEADLINE_EXHAUSTED':
            store.value['phase']='CANCEL_REQUESTED'
            try:
                store.save()
                if state: budget_call(store,wire,'CANCEL',**auth(state))
            except Exception: pass
        elif str(exc) in {'GENOS_COMPUTE_HANDLE_GONE','GENOS_COMPUTE_INSTANCE_CHANGED','GENOS_COMPUTE_LEASE_EXPIRED'}:
            store.value['phase']='HANDLE_LOST'
        elif store.value.get('phase') not in {'FAILED','CANCELLED','STRUCTURED'}:
            # Preserve OPEN_INTENT so a response loss can reconcile the same handle/token.
            prior=store.value['phase']
            store.value['uncertain_phase']=prior
            if prior!='OPEN_INTENT': store.value['phase']='UNKNOWN'
        store.value['last_error_type']=type(exc).__name__
        store.save()
        raise


def load(cfg,folders,variables,work,name):
    # Existing exact Oracle loader, without a GENOS capability or ACK step.
    receipts=r.input_receipts(folders['landing'])
    oracle,binding,wire,identity=context(cfg,receipts,variables)
    upstream=ManagedJob(r.ReadOnlyFolder(Scope(folders['structured'])),name,identity)
    proof=r.read_json(upstream.folder,'jobs/'+name+'/structured.json')
    if upstream.value.get('phase')!='STRUCTURED' or proof!=structured_record(upstream):
        raise ValueError('UPSTREAM_NOT_STRUCTURED_OR_CHANGED')
    store=ManagedJob(Scope(folders['load']),name,{**identity,'structured_state':proof['state_sha256']})
    if 'seeded_from' not in store.value:
        store.value.update(deadline=upstream.value['deadline'],reserved_sql_calls=upstream.value['reserved_sql_calls'],
                           seeded_from=proof['state_sha256']);store.save()
    if store.value['seeded_from']!=proof['state_sha256'] or store.value['deadline']!=upstream.value['deadline']:
        raise ValueError('LOAD_SOURCE_CHANGED')
    job=work/'job';job.mkdir(exist_ok=True)
    upstream.get_blob(proof['result_blob'],job/'result.zip')
    returned=job/'returned'
    manifest=t.unpack(job/'result.zip',returned,prefixes=('generation/','SEARCH_SELECTION/','query/','audit/'))
    if manifest['metadata']['code_sha256']!=EXPECTED: raise ValueError('RETURN_CODE_BINDING')
    t.write(returned/'transport-manifest.json',manifest)
    attempt=job/'oracle-attempt'
    try:
        result=r.client.load_oracle(BudgetClient(oracle,store),returned,attempt,target_binding=binding,deadline=store.value['deadline'])
        snapshot=job/'receipts.zip'
        t.pack({str(p.relative_to(attempt)):p for p in t.files(attempt) if p.suffix in ('.json','.jsonl')},snapshot,
               metadata={'target':binding,'result_sha256':proof['result_blob']['sha256']})
        store.value.update(phase='COMPLETE',oracle_written=True,load_receipt=result,receipt_blob=store.put_blob(snapshot));store.save()
        summary={'status':'COMPLETE','oracle_written':True,'source_release_id':result['source_release_id'],
                 'query_release_id':result['query']['release_id'],'query_rows':result['query']['rows'],
                 'target':'SIDDS.*_S','active_changed':False,'genos_calls':0}
        r.put_json(store.folder,'jobs/'+name+'/complete.json',summary,work)
        return summary
    except BaseException as exc:
        store.value.update(phase='STOPPED',last_error_type=type(exc).__name__)
        if attempt.exists():
            snapshot=job/'failure-receipts.zip'
            t.pack({str(p.relative_to(attempt)):p for p in t.files(attempt) if p.suffix in ('.json','.jsonl')},snapshot,
                   metadata={'failure':type(exc).__name__})
            store.value['failure_receipt_blob']=store.put_blob(snapshot)
        store.save();raise


def connection(variables,out,work):
    result=health(remote(variables))
    public={k:v for k,v in result.items() if k!='instance'}
    public.update(status='CONNECTED_COMPUTE_CODE_MATCH',oracle_written=False,documents_sent=0)
    r.put_json(out,'checks/'+uuid.uuid4().hex+'.json',public,work)
    print(json.dumps(public),flush=True)
    return public


def execute(stage,cfg,work):
    # The baseline executor creates the same declared folders and failure reports.
    r.connection=connection;r.structure=structure;r.load=load
    return r.execute(stage,cfg,work)
