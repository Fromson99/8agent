"""Three DSS recipe entry points. Only the third recipe writes the destination."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
import uuid

import agent_stage as stage
import pipeline_coverage as coverage
import transport as t

ROOT = Path(__file__).resolve().parent
CODE = (ROOT/'SERVER_PIN.txt').read_text().strip()
NAMES = {'raw': 'RAW_INPUT.zip', 'support': 'PIPELINE_SUPPORT.zip'}


def read(folder, path):
    with folder.get_download_stream(path) as stream:
        b = stream.read(65537)
    if len(b) > 65536:
        raise ValueError('RECEIPT_TOO_LARGE')
    return json.loads(b)


def saved(folder, path):
    if path not in {p.lstrip('/') for p in folder.list_paths_in_partition()}:
        return None
    return read(folder,path)


def put(folder, path, record):
    existing = saved(folder,path)
    if existing is None:
        folder.upload_stream(path, io.BytesIO(json.dumps(record,sort_keys=True).encode()))
    if read(folder,path) != record:
        raise ValueError('RECEIPT_CONFLICT')


def archives(raw,folder,mounted):
    result = {}
    for slot,name in NAMES.items():
        if slot=='raw':
            value=raw
        elif folder is not None:
            value=read(folder,name+'.receipt.json')
        elif mounted:
            value=dict(mounted,archive=name)
        else:
            raise ValueError('CONFIGURE_GENOS_SUPPORT_MOUNT_OR_SUPPORT_FOLDER_ID')
        if (value['archive'] != name or type(value['bytes']) is not int or
                not 0 < value['bytes'] <= 64*1024**3 or not re.fullmatch('[0-9a-f]{64}',value['sha256'])):
            raise ValueError('INPUT_RECEIPT_INVALID:'+name)
        result[slot] = {k:value[k] for k in ('sha256','bytes')}
    return result


def layer_query(connection):
    import dataiku
    executor = dataiku.SQLExecutor2(connection=connection)
    def query(sql):
        frame = executor.query_to_df(sql)
        frame.columns = [str(k).upper() for k in frame.columns]
        return frame.to_dict('records')
    return query


def wire(variables):
    from stage_wire import Wire
    return Wire(variables['AGENT_PIPELINE_URL'],variables['AGENT_PIPELINE_TOKEN'])


def submit(cfg, paths, folders, variables, trial):
    from document_input import snapshot
    raw = snapshot(folders['input'],paths,cfg['DOCUMENT_PREFIX'])
    prior = saved(folders['submit'],trial+'/intent.json')
    private = paths/'request.json'
    previous = t.read(private)['intent'] if private.exists() else prior
    remote = wire(variables)
    health = None
    mounted = None
    if 'support' not in folders:
        if previous:
            mounted=previous['context']['archives']['support']
        else:
            health=remote.call('HEALTH')
            mounted=health.get('mounted_support')
    declared = archives(raw,folders.get('support'),mounted)
    context = {'code': CODE, 'archives': declared, 'project': cfg['project'],
               'input': cfg['INPUT_FOLDER_ID'], 'support':cfg['SUPPORT_FOLDER_ID'], 'endpoint': hashlib.sha256(remote.url.encode()).hexdigest(),
               'agent_connection':cfg['AGENT_CONNECTION'], 'trial':trial}
    if not private.exists():
        if prior:
            finished = stage.ready(layer_query(cfg['AGENT_CONNECTION']),prior['job'],prior['binding'])
            if finished and prior['context']==context:
                put(folders['submit'],trial+'/submitted.json',prior)
                return prior
            raise ValueError('RESTORE_ORIGINAL_WORK_DIR_BEFORE_RESUME')
        health = health or remote.call('HEALTH')
        if health.get('code_sha256') != CODE or health.get('protocol') != 'genos-agent-layer-v1' or not health['preprocessor']['ready']:
            raise ValueError('AGENT_SERVICE_REVISION_OR_PARSER')
        job = uuid.uuid4().hex
        intent = {'job':job, 'context':context, 'binding':stage.binding(job,declared,CODE)}
        auth = {'handle':job,'handle_token':secrets.token_hex(32),'instance':health['instance'],
                'code_sha256':CODE,'parser_config_sha256':health['preprocessor']['config_sha256']}
        t.write(private,{'intent':intent,'auth':auth,'deadline':time.time()+7*86400})
    state = t.read(private)
    intent,auth = state['intent'],state['auth']
    if intent['context'] != context:
        raise ValueError('TRIAL_ALREADY_BOUND_TO_DIFFERENT_INPUT_OR_ENDPOINT')
    put(folders['submit'],trial+'/intent.json',intent)
    if stage.ready(layer_query(cfg['AGENT_CONNECTION']),intent['job'],intent['binding']):
        put(folders['submit'],trial+'/submitted.json',intent)
        return intent
    # Repeating OPEN is safe only on the bound process, with all original parameters.
    if state.get('opened'):
        current = remote.call('POLL',**auth)
    else:
        current = remote.call('OPEN',**auth,archives=declared,deadline=state['deadline'])
        state['opened']=True
        t.write(private,state)
    if current['state']=='RECEIVING':
        for slot,name in NAMES.items():
            accepted = current['received'][slot]
            if slot=='support' and 'support' not in folders:
                if accepted!=declared[slot]['bytes']:
                    raise ValueError('SERVER_SUPPORT_MOUNT_REQUIRED')
                continue
            h = hashlib.sha256()
            offset = 0
            with ((paths/name).open('rb') if slot=='raw' else folders['support'].get_download_stream(name)) as src:
                while block := src.read(t.CHUNK):
                    if offset+len(block)>declared[slot]['bytes'] or time.time()>=state['deadline']:
                        raise ValueError('INPUT_SIZE_OR_DEADLINE')
                    h.update(block)
                    if offset+len(block)>accepted:
                        start=max(accepted-offset,0)
                        part=block[start:]
                        current=remote.call('PUT',**auth,slot=slot,offset=offset+start,
                                            content=base64.b64encode(part).decode(),sha256=hashlib.sha256(part).hexdigest())
                        if current['received'][slot] != offset+len(block):
                            raise ValueError('UPLOAD_OFFSET')
                    offset+=len(block)
            if declared[slot] != {'sha256':h.hexdigest(),'bytes':offset}:
                raise ValueError('INPUT_HASH_OR_SIZE_CHANGED')
        current = remote.call('RUN',**auth)
    if current['state'] not in ('RUNNING','COMPLETE'):
        raise ValueError('COMPUTE_'+current['state']+':'+str(current.get('error')))
    put(folders['submit'],trial+'/submitted.json',intent)
    return intent


def wait_ready(cfg, paths, folders, variables, trial):
    intent=read(folders['submit'],trial+'/submitted.json')
    validate_intent(intent,cfg,trial)
    query=layer_query(cfg['AGENT_CONNECTION'])
    remote=None
    previous=None
    while True:
        receipt=stage.ready(query,intent['job'],intent['binding'])
        if receipt:
            record={'intent':intent,'result':receipt}
            put(folders['wait'],trial+'/ready.json',record)
            return record
        state=t.read(paths/'request.json')
        if state['intent']!=intent or time.time()>=state['deadline']:
            raise ValueError('REQUEST_BINDING_OR_DEADLINE')
        if remote is None:
            remote=wire(variables)
            if hashlib.sha256(remote.url.encode()).hexdigest()!=intent['context']['endpoint']:
                raise ValueError('GENOS_ENDPOINT_CHANGED')
        current=remote.call('POLL',**state['auth'])
        message=(current['state'],current['phase'])
        if message!=previous:
            print(intent['job'],*message,flush=True)
            previous=message
        if current['state'] in ('CANCELLED','FAILED','COMPLETE'):
            if stage.ready(query,intent['job'],intent['binding']):
                continue
            raise ValueError('COMPUTE_WITHOUT_READY:'+str(current.get('error') or current['state']))
        time.sleep(5)


def validate_intent(intent,cfg,trial):
    ctx = intent['context']
    if (ctx['trial']!=trial or ctx['code']!=CODE or ctx['project']!=cfg['project'] or
            ctx['input']!=cfg['INPUT_FOLDER_ID'] or ctx['support']!=cfg['SUPPORT_FOLDER_ID'] or ctx['agent_connection']!=cfg['AGENT_CONNECTION'] or
            intent['binding']!=stage.binding(intent['job'],ctx['archives'],CODE)):
        raise ValueError('RECEIPT_BINDING_CHANGED')


def load(cfg, paths, folders, variables, trial):
    record=read(folders['wait'],trial+'/ready.json')
    intent=record['intent']
    validate_intent(intent,cfg,trial)
    query=layer_query(cfg['AGENT_CONNECTION'])
    target_root=paths/('load-'+t.digest({k:v for k,v in cfg.items() if k!='folders'})[:24])
    target_root.mkdir(exist_ok=True)
    path=target_root/'result.zip'
    stage.restore(query,intent['job'],intent['binding'],record['result'],path)
    cov,_=coverage.read(path,CODE)
    cov_summary=coverage.summary(cov)
    coverage.display(cov)
    manifest=t.unpack(path,target_root/'restored',prefixes=('generation/','SEARCH_SELECTION/','query/','audit/'))
    generation=target_root/'restored/generation'
    coverage.verify_generation(generation,cov)
    input_documents=t.read(target_root/'restored/audit/input-raw.json')['metadata']['document_count']
    for slot in NAMES:
        source=t.read(target_root/f'restored/audit/input-{slot}.json')
        if t.digest(source)!=manifest['metadata']['input_manifest_hashes'][slot]:
            raise ValueError('RETURN_INPUT_MANIFEST_CHANGED')
    if manifest['metadata']['archives']!=intent['context']['archives']:
        raise ValueError('RETURN_INPUT_CHANGED')
    sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'engine/vendor'),str(ROOT/'engine/vendor/02_BACKEND')]
    from prod_config import target
    import prod_pipeline as prod
    params=dict(TARGET_MODE='DEV_1' if cfg['ENVIRONMENT']=='DEV' else 'GOLD',
                GOLD_OWNER=cfg['GOLD_OWNER'],ORACLE_CONNECTION=cfg['TARGET_CONNECTION'],
                EXPECTED_DB_USER=cfg['EXPECTED_DB_USER'],EMBED_MODEL=cfg['EMBED_MODEL'],
                EMBED_DIMENSIONS=cfg['EMBED_DIMENSIONS'],ACTIVATE_NEW_VECTOR_HEAD=False)
    config={'params':params,'project':cfg['project'],'target':target(params)}
    prod.fixed(target_root/'restore.json',{'generation':str(generation),'agent':record,'coverage':cov_summary})
    for step in ('inspect','prepare','source','search','publish','vector','report'):
        print('TARGET',cfg['ENVIRONMENT'],step,flush=True)
        report=prod.execute(step,config,target_root)
    result={'status':cfg['ENVIRONMENT']+'_LOADED','target_layer':'Silver' if cfg['ENVIRONMENT']=='DEV' else 'Gold',
            'job':intent['job'],'input_documents':input_documents,'archive':record['result'],'coverage':cov_summary,'counts':report['counts'],
            'query_release_id':report['query_release_id'],'source_release_id':report['source_release_id'],
            'vector_publication_id':report['vector']['publication_id'],'checks':report['row_counts_and_publications_verified']}
    if not result['checks']:
        raise ValueError('TARGET_READBACK_INCOMPLETE')
    put(folders['load'],trial+'/report.json',result)
    return result


def run(operation,cfg):
    import dataiku
    from flow_install import validate
    validate(cfg)
    project=dataiku.api_client().get_default_project().project_key
    if cfg['project']!=project:
        raise ValueError('FLOW_PROJECT_MISMATCH')
    variables=dataiku.get_custom_variables()
    trial=variables.get('AGENT_FLOW_TRIAL','trial-001')
    if not isinstance(trial,str) or not re.fullmatch('[a-zA-Z0-9_-]{1,64}',trial):
        raise ValueError('TRIAL_ID_INVALID')
    inputs={'submit':{'input','submit','support'},'wait':{'submit','wait'},'load':{'wait','load'}}[operation]
    ids=dict(cfg['folders'],input=cfg['INPUT_FOLDER_ID'],support=cfg['SUPPORT_FOLDER_ID'])
    folders={k:dataiku.Folder(ids[k]) for k in inputs if ids[k]}
    paths=Path(cfg['WORK_DIR'])/'agent-layer-r1'/project/cfg['ENVIRONMENT']/trial
    paths.mkdir(parents=True,exist_ok=True,mode=0o700)
    with t.lock(paths/'flow.lock'):
        result={'submit':submit,'wait':wait_ready,'load':load}[operation](cfg,paths,folders,variables,trial)
    print(operation,result.get('job') or result.get('intent',{}).get('job'),flush=True)
    return result
