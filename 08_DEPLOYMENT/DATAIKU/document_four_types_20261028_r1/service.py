"""Ephemeral compute/transfer handles. Durable jobs, logs and retries belong to DSS."""
import asyncio
import base64
import hashlib
import hmac
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import transport as t
import worker
import parser_config
import review_audit
import sample_worker
import probe_runtime

ROOT = Path(__file__).resolve().parent
PROTOCOL = 'dataiku-owned-compute-v1'
INSTANCE = uuid.uuid4().hex  # Process lifetime only; never written to disk.
HANDLES = {}
GUARD = threading.RLock()
LEASE_SECONDS = 900
MAX_HANDLES = 4
MAX_RUNNING = 1


def digest_file(path):
    return {'sha256': t.sha(path), 'bytes': path.stat().st_size}


def stop_child(child):
    if child is not None and child.poll() is None:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)


def resource_check(h):
    if h['cancel'].is_set():
        raise RuntimeError('CANCELLED')
    if time.time() >= h['deadline']:
        raise RuntimeError('DEADLINE_EXHAUSTED')
    if time.monotonic() >= h['lease_until']:
        raise RuntimeError('LEASE_EXPIRED')
    if shutil.disk_usage(h['folder']).free < 512*t.CHUNK:
        raise RuntimeError('DISK_LOW')


def run_compute(h):
    """The existing pure batch transform; no job journal or server-side retries."""
    folder = h['folder']
    try:
        resource_check(h)
        import json
        command=[sys.executable,'-B',str(ROOT/'worker.py'),'--compute',str(folder),'dku-'+h['id'],
                 json.dumps(h['archives'],sort_keys=True),h['parser_config_sha256']]
        if h['purpose']==sample_worker.PURPOSE:
            command=[sys.executable,'-B',str(ROOT/'sample_worker.py'),str(folder),json.dumps(h['archives'],sort_keys=True),h['parser_config_sha256']]
        with (folder/'compute.log').open('ab',buffering=0) as output:
            child=subprocess.Popen(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
            with GUARD:
                h['child']=child;h['phase']='DOCUMENT_PROBE' if h['purpose']==sample_worker.PURPOSE else 'NATIVE_PIPELINE'
            try:
                while child.poll() is None:
                    resource_check(h)
                    if worker.process_group_rss(child.pid)>h['max_rss_mb']*t.CHUNK:
                        raise RuntimeError('MEMORY_LIMIT')
                    if (folder/'compute.log').stat().st_size>512*t.CHUNK:
                        raise RuntimeError('LOG_LIMIT')
                    time.sleep(.2)
                resource_check(h)
                if child.returncode: raise RuntimeError('NATIVE_PIPELINE_FAILED')
            finally:
                stop_child(child)
                with GUARD: h['child']=None
        worker.verify_code(ROOT)
        result = digest_file(folder/'result.zip')
        with GUARD:
            h.update(state='COMPLETE', phase='RETURN', result=result)
    except BaseException as exc:
        code = str(exc)
        if not re.fullmatch(r'[A-Z_]{1,80}', code):
            code = 'COMPUTE_FAILED_'+type(exc).__name__.upper()
        # Publish a terminal state only after the final audit snapshot is ready.
        try:
            if h['purpose']==sample_worker.PURPOSE:sample_worker.export_partial(folder)
            else:review_audit.export(folder)
            h['audit'] = digest_file(folder/'audit.zip')
        except Exception as audit_error:
            h['audit_error'] = 'AUDIT_EXPORT_' + type(audit_error).__name__.upper()
        with GUARD:
            h.update(state='CANCELLED' if code=='CANCELLED' else 'FAILED', error=code)
    finally:
        with GUARD:
            h['ended'] = time.time()
            # Keep transfer buffers for the existing lease, not an indefinitely blocking job.


def reap():
    while True:
        time.sleep(1)
        with GUARD:
            expired = [h for h in HANDLES.values() if time.monotonic() >= h['lease_until']]
            for h in expired:
                h['cancel'].set()
                if h['state'] != 'RUNNING':
                    shutil.rmtree(h['folder'], ignore_errors=True)
                    HANDLES.pop(h['id'], None)


threading.Thread(target=reap, daemon=True, name='compute-lease').start()


def public(h):
    return {'protocol':PROTOCOL, 'instance':INSTANCE, 'handle':h['id'], 'state':h['state'],
            'phase':h.get('phase',''), 'error':h.get('error'), 'result':h.get('result'),
            'parser_config_sha256':h['parser_config_sha256'],
            'audit':h.get('audit'), 'audit_error':h.get('audit_error'),
            'received':dict(h['received']), 'lease_seconds':LEASE_SECONDS,
            'log_bytes':(h['folder']/'compute.log').stat().st_size}


def auth(data):
    if data.get('code_sha256') != t.sha(ROOT/'CODE_PINS.json'):
        raise ValueError('CODE_MISMATCH')
    if data.get('instance') != INSTANCE:
        raise ValueError('COMPUTE_INSTANCE_CHANGED')
    h = HANDLES.get(data.get('handle'))
    if h is None:
        raise ValueError('COMPUTE_HANDLE_GONE')
    if not hmac.compare_digest(h['token'], str(data.get('handle_token',''))):
        raise ValueError('COMPUTE_AUTH')
    if time.monotonic() >= h['lease_until']:
        h['cancel'].set()
        raise ValueError('COMPUTE_LEASE_EXPIRED')
    h['lease_until'] = time.monotonic()+LEASE_SECONDS
    return h


def handle(data):
    if not isinstance(data,dict):
        raise ValueError('REQUEST_OBJECT')
    op = data.get('API_TYPE')
    if op in {'HEALTH','PROBE_HEALTH'}:
        worker.verify_code(ROOT)
        return {'protocol':PROTOCOL, 'instance':INSTANCE, 'code_sha256':t.sha(ROOT/'CODE_PINS.json'),
                'chunk_bytes':t.CHUNK, 'lease_seconds':LEASE_SECONDS, 'durable_jobs':False,
                's3_access':False, 'cancel_supported':True, 'replicas':1, 'workers':1,
                'probe_purpose':sample_worker.PURPOSE,
                'preprocessor':probe_runtime.inspect(ROOT) if op=='PROBE_HEALTH' else parser_config.inspect(ROOT)}
    with GUARD:
        if op == 'OPEN':
            if data.get('code_sha256') != t.sha(ROOT/'CODE_PINS.json'):
                raise ValueError('CODE_MISMATCH')
            if data.get('instance') != INSTANCE:
                raise ValueError('COMPUTE_INSTANCE_CHANGED')
            ident, token = data.get('handle',''), data.get('handle_token','')
            if not re.fullmatch('[0-9a-f]{32}',ident) or not re.fullmatch('[0-9a-f]{64}',token):
                raise ValueError('HANDLE_FORMAT')
            archives = data.get('archives')
            if not isinstance(archives,dict) or set(archives) != {'raw','support'}:
                raise ValueError('ARCHIVES')
            for item in archives.values():
                if (set(item) != {'sha256','bytes'} or not re.fullmatch('[0-9a-f]{64}',str(item['sha256']))
                        or type(item['bytes']) is not int or not 0 < item['bytes'] <= 64*1024*t.CHUNK):
                    raise ValueError('ARCHIVE_LIMIT')
            deadline = data.get('deadline')
            if not isinstance(deadline,(int,float)) or not time.time() < deadline <= time.time()+7*86400:
                raise ValueError('DEADLINE')
            memory = data.get('max_rss_mb',6144)
            if type(memory) is not int or not 256 <= memory <= 6144:
                raise ValueError('MEMORY_BUDGET')
            purpose=data.get('purpose','pipeline')
            if purpose not in {'pipeline',sample_worker.PURPOSE}:raise ValueError('COMPUTE_PURPOSE')
            parser = (probe_runtime if purpose==sample_worker.PURPOSE else parser_config).require(ROOT)
            if data.get('parser_config_sha256') != parser['config_sha256']:
                raise ValueError('PREPROCESSOR_CONFIG_CHANGED')
            if ident in HANDLES:
                h = auth(data)
                if h['purpose'] != purpose or h['archives'] != archives or h['deadline'] != deadline or h['max_rss_mb'] != memory or h['parser_config_sha256'] != parser['config_sha256']:
                    raise ValueError('HANDLE_BINDING')
                return public(h)
            if len(HANDLES) >= MAX_HANDLES:
                raise ValueError('COMPUTE_CAPACITY')
            folder = Path(tempfile.mkdtemp(prefix='legal-compute-'))
            os.chmod(folder,0o700)
            (folder/'compute.log').touch()
            h = dict(id=ident, token=token, folder=folder, archives=archives, deadline=deadline, purpose=purpose,
                     parser_config_sha256=parser['config_sha256'], max_rss_mb=memory, state='RECEIVING', received={'raw':0,'support':0}, child=None,
                     cancel=threading.Event(), lease_until=time.monotonic()+LEASE_SECONDS)
            HANDLES[ident] = h
            return public(h)
        h = auth(data)
        if op == 'PUT':
            if h['state'] != 'RECEIVING':
                raise ValueError('NOT_RECEIVING')
            slot, offset = data.get('slot'), data.get('offset')
            if slot not in ('raw','support') or type(offset) is not int or offset < 0:
                raise ValueError('UPLOAD_OFFSET')
            try:
                block = base64.b64decode(data['content'],validate=True)
            except Exception:
                raise ValueError('CHUNK_FORMAT') from None
            if not 0 < len(block) <= t.CHUNK or hashlib.sha256(block).hexdigest() != data.get('sha256'):
                raise ValueError('CHUNK_HASH')
            path = h['folder']/(slot+'.zip')
            if offset < h['received'][slot]:
                with path.open('rb') as f:
                    f.seek(offset)
                    if f.read(len(block)) != block:
                        raise ValueError('CHUNK_CONFLICT')
            else:
                if offset != h['received'][slot] or offset+len(block) > h['archives'][slot]['bytes']:
                    raise ValueError('UPLOAD_OFFSET')
                resource_check(h)
                with path.open('ab') as f:
                    f.write(block)
                h['received'][slot] += len(block)
        elif op == 'RUN':
            if h['state'] == 'RECEIVING':
                (probe_runtime if h['purpose']==sample_worker.PURPOSE else parser_config).require(ROOT, h['parser_config_sha256'])
                if any(h['received'][s] != v['bytes'] for s,v in h['archives'].items()):
                    raise ValueError('INPUT_INCOMPLETE')
                if sum(x['state']=='RUNNING' for x in HANDLES.values()) >= MAX_RUNNING:
                    raise ValueError('COMPUTE_CAPACITY')
                h['state']='RUNNING'
                threading.Thread(target=run_compute,args=(h,),daemon=True).start()
            # Duplicate RUN only returns the same computation; it never starts another.
        elif op == 'CANCEL':
            h['cancel'].set()
            if h['state'] == 'RECEIVING':
                h.update(state='CANCELLED',error='CANCELLED')
            # For RUNNING, supervisor confirms child termination before CANCELLED.
        elif op == 'READ':
            kind, offset = data.get('kind'), data.get('offset')
            if kind not in ('log','result','audit') or type(offset) is not int or offset < 0:
                raise ValueError('READ_RANGE')
            if kind=='result' and h['state'] != 'COMPLETE':
                raise ValueError('RESULT_NOT_READY')
            if kind=='audit' and (h['state'] not in {'FAILED','CANCELLED'} or not h.get('audit')):
                raise ValueError('AUDIT_NOT_READY')
            path = h['folder']/({'log':'compute.log','result':'result.zip','audit':'audit.zip'}[kind])
            size = path.stat().st_size
            if offset > size:
                raise ValueError('READ_RANGE')
            with path.open('rb') as f:
                f.seek(offset); block=f.read(t.CHUNK)
            return {'offset':offset,'bytes':len(block),'sha256':hashlib.sha256(block).hexdigest(),
                    'content':base64.b64encode(block).decode(), 'total_bytes':size}
        elif op == 'CLOSE':
            if h['state']=='RUNNING':
                raise ValueError('COMPUTE_STILL_RUNNING')
            if h['state']=='COMPLETE' and data.get('result_sha256') != h['result']['sha256']:
                raise ValueError('RESULT_RECEIPT_REQUIRED')
            if h.get('audit') and data.get('audit_sha256') != h['audit']['sha256']:
                raise ValueError('AUDIT_RECEIPT_REQUIRED')
            result = public(h)
            shutil.rmtree(h['folder'])
            HANDLES.pop(h['id'])
            return {**result,'closed':True}
        elif op != 'POLL':
            raise ValueError('UNKNOWN_API_TYPE')
        return public(h)


async def service(config, data):
    try:
        return {'code':0,'data':await asyncio.to_thread(handle,data)}
    except Exception as exc:
        code = str(exc)
        if not re.fullmatch('[A-Z_]{1,80}',code):
            code = 'COMPUTE_REQUEST_FAILED'
        return {'code':1,'error':code,'error_type':type(exc).__name__}


service.service = service
