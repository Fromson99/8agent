"""Separate GENOS code serving: Dataiku push -> native full build -> returned files.

Platform authentication is required. One replica, one concurrent temporary job.
No RAG endpoint, reverse Dataiku connection, database credentials or corpus cache.
"""
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
import time
import uuid
import transport as t

ROOT = Path(__file__).resolve().parent
SLOTS = {'raw': 'RAW_INPUT.zip', 'support': 'PIPELINE_SUPPORT.zip'}
MAX_BYTES = 100 * 1024**3


def pid_identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] == 'Z':
            return None
        return [pid, fields[19], Path('/proc/sys/kernel/random/boot_id').read_text().strip()]
    except FileNotFoundError:
        return None


def code_pin():
    return t.sha(ROOT / 'CODE_PINS.json')


def scratch():
    value = os.environ.get('PIPELINE_SCRATCH')
    if not value or not Path(value).is_absolute():
        raise ValueError('PIPELINE_SCRATCH: explicit absolute ephemeral disk directory required')
    root = Path(value)
    root.mkdir(parents=True, exist_ok=True)
    t.checked(root.parent, root.name)
    with t.lock(root / 'instance.lock'):
        marker = root / 'instance.json'
        if not marker.exists():
            t.write(marker, {'instance': uuid.uuid4().hex})
    return root


def public(state):
    return {k: v for k, v in state.items() if k not in {'token_hash', 'worker', 'child'}}


def child_running(state):
    child = state.get('child')
    if not child or child[2] != Path('/proc/sys/kernel/random/boot_id').read_text().strip():
        return False
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            parts = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
            if parts[0] != 'Z' and int(parts[2]) == child[0] and proc.stat().st_uid == os.getuid():
                return True
        except (FileNotFoundError, ProcessLookupError):
            continue
    return False


def refresh(folder, state):
    if state['status'] == 'RUNNING' and state.get('worker') != pid_identity(state.get('worker', [0])[0]):
        state.update(status='INTERRUPTED', error='WORKER_LOST: input remains in Dataiku; preserve this attempt, start a new job')
        t.write(folder / 'state.json', state)
    return state


def handle(data):
    if not isinstance(data, dict):
        raise ValueError('JSON_OBJECT_REQUIRED')
    op = data.get('API_TYPE')
    root = scratch()
    instance = t.read(root / 'instance.json')['instance']
    if op == 'HEALTH':
        return {'status': 'READY', 'instance': instance, 'code_sha256': code_pin(),
                'python': sys.version.split()[0], 'chunk_bytes': t.CHUNK,
                'disk_free_bytes': shutil.disk_usage(root).free,
                'mode': 'native-no-models', 'replicas_required': 1}
    job = data.get('job_id', '')
    token = data.get('job_token', '')
    if not re.fullmatch(r'[a-f0-9]{32}', job) or not re.fullmatch(r'[a-f0-9]{64}', token):
        raise ValueError('INVALID_JOB_CREDENTIALS')
    if data.get('code_sha256') != code_pin():
        raise ValueError('CODE_BINDING_CHANGED')
    if data.get('instance') != instance:
        raise ValueError('INSTANCE_CHANGED: preserve client state; do not replay automatically')
    folder = root / job
    with t.lock(root / 'dispatch.lock'):
        state_path = folder / 'state.json'
        if op == 'START' and not state_path.exists():
            archives = data['archives']
            if set(archives) != set(SLOTS):
                raise ValueError('INPUT_SLOTS')
            for item in archives.values():
                if (type(item.get('bytes')) is not int or not 0 < item['bytes'] <= MAX_BYTES
                        or not re.fullmatch(r'[a-f0-9]{64}', item.get('sha256', ''))):
                    raise ValueError('INPUT_DECLARATION')
            deadline = data['deadline']
            if type(deadline) not in (int, float) or not time.time() < deadline <= time.time() + 7*86400:
                raise ValueError('DEADLINE')
            for previous in root.glob('*/state.json'):
                old = refresh(previous.parent, t.read(previous))
                if old['status'] != 'RELEASED':
                    raise ValueError('BUSY: retrieve/acknowledge or release the previous temporary job first')
            if shutil.disk_usage(root).free < sum(i['bytes'] for i in archives.values()) + 1024*t.CHUNK:
                raise ValueError('DISK_LOW')
            state = {'job_id': job, 'instance': instance, 'code_sha256': code_pin(),
                     'token_hash': hashlib.sha256(token.encode()).hexdigest(), 'deadline': deadline,
                     'archives': archives, 'status': 'UPLOADING', 'created': time.time(), 'received': {}}
            folder.mkdir(mode=0o700)
            t.write(state_path, state)
        if not state_path.exists():
            raise ValueError('JOB_LOST: resume from Dataiku originals using a new explicit job')
        state = refresh(folder, t.read(state_path))
        if not hmac.compare_digest(state['token_hash'], hashlib.sha256(token.encode()).hexdigest()):
            raise ValueError('JOB_AUTH')
        if state['code_sha256'] != code_pin():
            raise ValueError('JOB_CODE_CHANGED')
        if op in {'START', 'UPLOAD', 'EXECUTE'} and time.time() >= state['deadline']:
            raise ValueError('DEADLINE_EXHAUSTED')
        if op == 'START':
            if state['archives'] != data['archives'] or state['deadline'] != data['deadline']:
                raise ValueError('JOB_INPUT_CONFLICT')
        elif op == 'UPLOAD':
            if state['status'] != 'UPLOADING' or data.get('slot') not in SLOTS:
                raise ValueError('UPLOAD_STATE')
            slot = data['slot']
            encoded = data.get('file_content_base64', '')
            if len(encoded) > 4*((t.CHUNK+2)//3):
                raise ValueError('CHUNK_TOO_LARGE')
            block = base64.b64decode(encoded, validate=True)
            if not block or hashlib.sha256(block).hexdigest() != data['sha256']:
                raise ValueError('CHUNK_HASH')
            offset = data['offset']
            target = folder / SLOTS[slot]
            size = target.stat().st_size if target.exists() else 0
            if type(offset) is not int or offset < 0 or offset > size or offset+len(block) > state['archives'][slot]['bytes']:
                raise ValueError('CHUNK_OFFSET')
            if offset < size:
                with target.open('rb') as f:
                    f.seek(offset)
                    if f.read(len(block)) != block:
                        raise ValueError('CHUNK_CONFLICT')
            else:
                if shutil.disk_usage(root).free < len(block)+512*t.CHUNK:
                    raise ValueError('DISK_LOW')
                with target.open('ab') as f:
                    f.write(block)
                    f.flush()
                    os.fsync(f.fileno())
            state['received'][slot] = target.stat().st_size
            t.write(state_path, state)
        elif op == 'EXECUTE':
            if state['status'] == 'UPLOADING':
                for slot, name in SLOTS.items():
                    path = folder / name
                    if not path.is_file() or path.stat().st_size != state['archives'][slot]['bytes']:
                        raise ValueError('INPUT_INCOMPLETE')
                state.update(status='RUNNING', phase='VERIFY_INPUTS')
                # Process starts behind dispatch lock, so no competing API can see a half-written PID.
                with (folder / 'worker.log').open('ab') as log:
                    proc = subprocess.Popen([sys.executable, '-B', str(ROOT / 'worker.py'), str(folder)],
                                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                state['worker'] = pid_identity(proc.pid)
                t.write(state_path, state)
            elif state['status'] not in {'RUNNING', 'COMPLETE'}:
                raise ValueError('EXECUTION_NOT_REPLAYABLE: preserve this attempt')
        elif op == 'DOWNLOAD':
            name = data.get('file_name', 'result.zip')
            allowed = {'result.zip'} if state['status'] == 'COMPLETE' else {'worker.log', 'structure.log', 'prepare.log', 'index.log', 'return.log'}
            if name not in allowed or state['status'] == 'RUNNING':
                raise ValueError('DOWNLOAD_STATE')
            target = folder / name
            offset = data['offset']
            if type(offset) is not int or not 0 <= offset <= target.stat().st_size:
                raise ValueError('DOWNLOAD_OFFSET')
            with target.open('rb') as f:
                f.seek(offset)
                block = f.read(t.CHUNK)
            return {'file_name': name, 'offset': offset, 'bytes': len(block),
                    'sha256': hashlib.sha256(block).hexdigest(),
                    'file_content_base64': base64.b64encode(block).decode('ascii')}
        elif op == 'CANCEL':
            if state['status'] == 'RUNNING':
                t.write(folder / 'cancel.json', {'requested': time.time()})
            elif child_running(state):
                child = state['child']
                if pid_identity(child[0]) != child:
                    raise ValueError('ORPHAN_CHILD_GROUP: stop the recorded job container before releasing scratch')
                os.killpg(child[0], signal.SIGTERM)
            else:
                state.update(status='CANCELLED')
                t.write(state_path, state)
        elif op == 'ACK':
            if child_running(state):
                raise ValueError('CHILD_STILL_RUNNING: cancel before releasing scratch')
            if state['status'] == 'RELEASED':
                if state.get('result') and data.get('result_sha256') != state['result']['sha256']:
                    raise ValueError('DOWNLOAD_RECEIPT_REQUIRED')
                return public(state)
            if state['status'] == 'RUNNING':
                raise ValueError('WORKER_RUNNING')
            if state['status'] == 'COMPLETE' and data.get('result_sha256') != state['result']['sha256']:
                raise ValueError('DOWNLOAD_RECEIPT_REQUIRED')
            if state['status'] != 'COMPLETE' and not data.get('discard_failed_attempt'):
                raise ValueError('EXPLICIT_FAILED_ATTEMPT_RELEASE_REQUIRED')
            # Delete only this generated job's temporary payload; retain the receipt.
            for child in folder.iterdir():
                if child.name == 'state.json':
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            state.update(status='RELEASED', released=time.time())
            t.write(state_path, state)
        elif op != 'STATUS':
            raise ValueError('UNKNOWN_API_TYPE')
        return public(state)


async def service(config, data):
    try:
        return {'code': 0, 'data': await asyncio.to_thread(handle, data)}
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return {'code': 1, 'error': str(exc), 'error_type': type(exc).__name__}


service.service = service
