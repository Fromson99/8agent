"""Fetch a finished GENOS computation over its signed handle and publish with DSS AIDP."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace
import zipfile

import agent_stage as stage
import pipeline_coverage
import transport as t


def check_deadline(deadline):
    if time.time() >= deadline:
        raise ValueError('ORIGINAL_JOB_DEADLINE_EXCEEDED')


def download(remote, state, receipt, directory):
    size=receipt.get('bytes')
    if type(size) is not int or not 0<size<=100*1024**3 or not re.fullmatch('[0-9a-f]{64}',str(receipt.get('sha256',''))):
        raise ValueError('INVALID_RESULT_RECEIPT')
    path=directory/'genos-result.zip'
    if path.exists():
        if path.stat().st_size!=size or t.sha(path)!=receipt['sha256']:
            raise ValueError('SAVED_GENOS_RESULT_HASH')
        return path
    tmp=directory/'genos-result.partial'
    offset=tmp.stat().st_size if tmp.exists() else 0
    if offset>size:
        raise ValueError('RETURN_OFFSET_OUT_OF_BOUNDS')
    with tmp.open('ab') as out:
        while offset<size:
            check_deadline(state['deadline'])
            row=remote.call('READ',**state['auth'],kind='result',offset=offset)
            data=base64.b64decode(row['content'],validate=True)
            if (row['offset']!=offset or row['total_bytes']!=size or row['bytes']!=len(data)
                    or not 0<len(data)<=min(t.CHUNK,size-offset) or hashlib.sha256(data).hexdigest()!=row['sha256']):
                raise ValueError('RETURN_CHUNK_INVALID')
            out.write(data)
            offset+=len(data)
        out.flush()
        os.fsync(out.fileno())
    if t.sha(tmp)!=receipt['sha256']:
        raise ValueError('RETURN_ARCHIVE_HASH')
    os.replace(tmp,path)
    return path


class StageWriter:
    def __init__(self, connection):
        import dataiku
        self.db=SimpleNamespace(calls=0,executor=dataiku.SQLExecutor2(connection=connection))

    def request(self,statement,binds,*,write,limit):
        from jdbc_transport import block
        if not write or limit!=1:
            raise ValueError('STAGE_WRITE_CONTRACT')
        return block(self.db,statement,binds,transaction_managed=True)


def receive(cfg, paths, folders, variables, trial):
    from flow_runtime import read, put, validate_intent, layer_query, wire, CODE
    intent=read(folders['submit'],trial+'/submitted.json')
    validate_intent(intent,cfg,trial)
    query=layer_query(cfg['AGENT_CONNECTION'])
    def finish(receipt):
        record={'intent':intent,'result':receipt}
        put(folders['wait'],trial+'/ready.json',record)
        return record
    receipt=stage.ready(query,intent['job'],intent['binding'])
    if receipt:
        return finish(receipt)
    private=paths/'request.json'
    if not private.is_file():
        raise ValueError('ORIGINAL_SHARED_WORK_DIR_REQUIRED: '+str(paths))
    state=t.read(private)
    if state['intent']!=intent:
        raise ValueError('REQUEST_BINDING_CHANGED')
    remote=wire(variables)
    if hashlib.sha256(remote.url.encode()).hexdigest()!=intent['context']['endpoint']:
        raise ValueError('GENOS_ENDPOINT_CHANGED')
    proof=paths/'genos-return.json'
    if proof.exists():
        reply=t.read(proof)
        if reply['intent']!=intent:
            raise ValueError('RETURN_JOB_CHANGED')
        result=reply['result']
    else:
        previous=None
        while True:
            check_deadline(state['deadline'])
            current=remote.call('POLL',**state['auth'])
            if current.get('handle')!=intent['job'] or current.get('instance')!=state['auth']['instance']:
                raise ValueError('RETURN_HANDLE_CHANGED')
            phase=current['state'],current['phase']
            if phase!=previous:
                print(intent['job'],*phase,flush=True)
                previous=phase
            if current['state']=='COMPLETE':
                result=current['result']
                t.write(proof,{'intent':intent,'result':result})
                break
            if current['state']!='RUNNING':
                raise ValueError('COMPUTE_WITHOUT_RESULT:'+str(current.get('error') or current['state']))
            time.sleep(5)
    archive=download(remote,state,result,paths)
    pipeline_coverage.read(archive,CODE)
    with zipfile.ZipFile(archive) as z:
        meta=json.loads(z.read('TRANSPORT.json'))['metadata']
    if meta['archives']!=intent['context']['archives']:
        raise ValueError('RETURN_INPUT_CHANGED')
    sys.path.insert(0,str(Path(__file__).resolve().parent/'engine'))
    stage.write_result(StageWriter(cfg['AGENT_CONNECTION']),archive,intent['job'],intent['binding'],
                       result,lambda:check_deadline(state['deadline']))
    receipt=stage.ready(query,intent['job'],intent['binding'])
    if not receipt or any(receipt[k]!=result[k] for k in ('bytes','sha256')):
        raise ValueError('AGENT_LAYER_READBACK_FAILED')
    record=finish(receipt)
    try:
        remote.call('CLOSE',**state['auth'],result_sha256=result['sha256'])
    except (OSError,RuntimeError,ValueError):
        print('SIDDA_READY; GENOS 임시 작업 정리는 만료 시 처리됩니다.',flush=True)
    return record
