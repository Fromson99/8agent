"""Control from DSS notebook. Cancellation intent and observation are saved in S3."""
import io
import json
import time
import uuid
import dataiku
import controller as c
from updater import config


def run(action,root,work):
    if action not in ('status','cancel','retry'):raise ValueError('ACTION')
    project=dataiku.api_client().get_project('LEGAL_RAG')
    cfg=config(project.get_recipe('LEGAL_02_STRUCTURE_GENOS_R1').get_settings().get_code(),'structure')
    variables=dataiku.get_custom_variables();name=variables.get('LEGAL_RECIPE_JOB_NAME','recipes_20261027_r1')
    folder=c.Scope(dataiku.Folder(cfg['structured']))
    latest=c.legacy_state(folder,name)
    if not latest:
        print('NOT_SUBMITTED');return {'status':'NOT_SUBMITTED'}
    state=latest['value'];compute=state.get('compute')
    if not compute:
        print('NOT_SUBMITTED');return {'status':'NOT_SUBMITTED'}
    if action=='status':
        summary={'status':state['phase'],'last_observed':state.get('last_observed'),
                 'logs_s3_prefix':c.NAMESPACE+'attempts/'+compute['handle']+'/logs/',
                 'result_saved':bool(state.get('result_blob'))}
        print(json.dumps(summary,ensure_ascii=False),flush=True)
        return summary
    if action=='retry':
        if state['phase'] not in {'FAILED','CANCELLED'}:
            raise ValueError('RETRY_REQUIRES_CONFIRMED_TERMINAL; UNKNOWN is not stopped')
        if state.get('attempt_count',1)>=3 or time.time()>=state['deadline']:
            raise ValueError('ORIGINAL_BUDGET_EXHAUSTED')
        marker={'handle':compute['handle'],'requested_at':time.time()}
        body=json.dumps(marker).encode();path='controls/'+name+'/retry.json'
        folder.upload_stream(path,io.BytesIO(body))
        with folder.get_download_stream(path) as f:
            if f.read()!=body:raise ValueError('RETRY_INTENT_READBACK')
        print('RETRY_PREPARED: stopped recipe 02를 다시 실행. 기존 기한/예산 유지',flush=True)
        return {'status':'RETRY_PREPARED'}
    # Immutable control attempt audit; no concurrent checkpoint sequence writer.
    ident=uuid.uuid4().hex;prefix='controls/'+name+'/'
    marker={'handle':compute['handle'],'requested_at':time.time(),'request_id':ident}
    c.r.put_json(folder,prefix+'requests/'+ident+'.json',marker,work)
    body=json.dumps(marker).encode()
    folder.upload_stream(prefix+'cancel.json',io.BytesIO(body))
    with folder.get_download_stream(prefix+'cancel.json') as f:
        if f.read()!=body:raise ValueError('CANCEL_INTENT_READBACK')
    wire=c.remote(variables);summary={'status':'CANCEL_REQUESTED','handle':compute['handle']}
    try:
        observation=wire.call('CANCEL',**c.auth(compute))
        for _ in range(5):
            if observation['state']!='RUNNING':break
            time.sleep(2);observation=wire.call('POLL',**c.auth(compute))
        terminal=observation['state']
        summary.update(status=('CANCELLED' if terminal=='CANCELLED' else
                      'ALREADY_COMPLETED' if terminal=='COMPLETE' else
                      'FAILED' if terminal=='FAILED' else 'CANCEL_REQUESTED'),observation=observation)
    except Exception as exc:
        summary.update(status='CANCEL_UNCONFIRMED',error_type=type(exc).__name__)
    c.r.put_json(folder,prefix+'observations/'+ident+'.json',summary,work)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    return summary
