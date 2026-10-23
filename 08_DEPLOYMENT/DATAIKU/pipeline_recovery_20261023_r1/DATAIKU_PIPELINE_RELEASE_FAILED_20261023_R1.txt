"""Paste after the R2 runner in the same Dataiku notebook. Releases one failed job.

Preserves input archives and exposed failure logs in the restricted managed
folder before ACK. Does not start ingestion or change its checkpoint/budget.
"""
import base64
import contextlib
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

FAILED_JOB_NAME = "run_20261023_01_20261023_01"
RECOVERY_REVISION = "failed-structure-release-20261023-r1"
RECOVERY_CLIENT_SHA = "9d553a32d460b6ddfe4b73a4186dea5501a0b878512ccd622fa7cbae631b9bb3"
RECOVERY_SERVICE_SHA = "771afb12a8fcf8c71417151cc80c8f4a9141e23d621ae27ec58cba67a7a22c46"
RECOVERY_CHUNK = 1024 * 1024


def _rc_bytes(folder, path, limit=1024*1024):
    data = bytearray()
    with folder.get_download_stream(path) as stream:
        while len(data) <= limit:
            block = stream.read(min(65536, limit+1-len(data)))
            if not block:
                break
            data.extend(block)
    if len(data) > limit:
        raise ValueError("RECOVERY_METADATA_SIZE")
    return bytes(data)


def _rc_latest(folder, prefix):
    matches = []
    for i, path in enumerate(folder.list_paths_in_partition()):
        if i >= 100000:
            raise ValueError("RECOVERY_PATH_LIMIT")
        match = re.fullmatch(re.escape(prefix) + r"(\d{10})-([0-9a-f]{64})\.json", path.lstrip("/"))
        if match:
            matches.append((int(match[1]), match[2], path))
    if not matches:
        return None
    seq, sha, path = max(matches)
    if sum(n == seq for n, _, _ in matches) != 1:
        raise ValueError("RECOVERY_CONCURRENT_STATE")
    raw = _rc_bytes(folder, path)
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError("RECOVERY_CHECKPOINT_HASH")
    return seq, json.loads(raw), {"path": path, "sha256": sha, "bytes": len(raw)}


def _rc_checkpoint(folder, name, url_hash):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", name):
        raise ValueError("RECOVERY_JOB_NAME")
    found = _rc_latest(folder, "_pipeline/jobs/"+name+"/checkpoint-")
    if found is None:
        raise ValueError("RECOVERY_CHECKPOINT_MISSING: "+name)
    _, checkpoint, receipt = found
    binding = checkpoint["binding"]
    source = binding["input"]
    if (source["folder_id"] != folder.get_id() or source["project"] != "LEGAL_RAG"
            or source["client_sha256"] != RECOVERY_CLIENT_SHA
            or binding["service_code"] != RECOVERY_SERVICE_SHA
            or binding["service_url_sha256"] != url_hash):
        raise ValueError("RECOVERY_BINDING_MISMATCH")
    state = checkpoint["client"]
    if (not re.fullmatch(r"[a-f0-9]{32}", state["job_id"])
            or not re.fullmatch(r"[a-f0-9]{64}", state["job_token"])
            or state["code_sha256"] != RECOVERY_SERVICE_SHA):
        raise ValueError("RECOVERY_CLIENT_STATE")
    return checkpoint, receipt


class _Recovery:
    def __init__(self, folder, client, identity, local):
        self.folder, self.client, self.identity, self.local = folder, client, identity, local
        self.prefix = "_pipeline/recovery/"+identity["old_job_id"]+"/"
        previous = _rc_latest(folder, self.prefix+"event-")
        if previous:
            self.seq, self.state, _ = previous
            if self.state["identity"] != identity:
                raise ValueError("RECOVERY_IDENTITY_CHANGED")
        else:
            self.seq = 0
            self.state = {"identity": identity, "revision": RECOVERY_REVISION,
                          "deadline": time.time()+1800, "api_calls": 0, "phase": "CREATED"}
            self.save()

    def check(self):
        if time.time() >= self.state["deadline"]:
            raise ValueError("RECOVERY_DEADLINE_EXHAUSTED: 원문·기존 복구 기록 보존")

    def save(self):
        raw = (json.dumps(self.state, sort_keys=True, ensure_ascii=False, indent=2)+"\n").encode()
        sha = hashlib.sha256(raw).hexdigest()
        name = self.prefix+f"event-{self.seq+1:010d}-{sha}.json"
        self.folder.upload_stream(name, io.BytesIO(raw))
        if _rc_bytes(self.folder, name) != raw:
            raise ValueError("RECOVERY_EVENT_READBACK")
        self.seq += 1

    def call(self, operation, **fields):
        self.check()
        if self.state["api_calls"] >= 100:
            raise ValueError("RECOVERY_API_BUDGET_EXHAUSTED")
        self.state["api_calls"] += 1
        self.state["last_operation"] = operation
        self.save()  # Reserve durably before the API call, including ACK.
        return self.client.call(operation, **fields)

    def stream_hash(self, stream, expected, label):
        h, size, notice = hashlib.sha256(), 0, time.monotonic()
        for block in iter(lambda: stream.read(RECOVERY_CHUNK), b""):
            self.check(); size += len(block)
            if size > expected["bytes"]:
                raise ValueError("RECOVERY_ARCHIVE_SIZE: "+label)
            h.update(block)
            if time.monotonic()-notice >= 10:
                print("RECOVERY_VERIFY", label, size, "/", expected["bytes"], flush=True)
                notice = time.monotonic()
        if size != expected["bytes"] or h.hexdigest() != expected["sha256"]:
            raise ValueError("RECOVERY_ARCHIVE_HASH: "+label)

    def verify_remote(self, info, label):
        with self.folder.get_download_stream(info["path"]) as stream:
            self.stream_hash(stream, info, label)

    def preserve_file(self, path, expected, label):
        path = safe_path(path)
        remote = self.prefix+"files/"+expected["sha256"]+".bin"
        if remote not in {p.lstrip('/') for p in self.folder.list_paths_in_partition()}:
            with path.open('rb') as stream:
                self.stream_hash(stream, expected, label+" local")
            self.check()
            print("RECOVERY_PRESERVE", label, expected["bytes"], "bytes", flush=True)
            with path.open('rb') as stream:
                self.folder.upload_stream(remote, stream)
        info = {"path": remote, **expected}
        self.verify_remote(info, label+" managed")
        return info

    def preserve_inputs(self, checkpoint):
        state = checkpoint["client"]
        raw = checkpoint["raw_blob"]
        if {k: raw[k] for k in ('sha256','bytes')} != state['archives']['raw']:
            raise ValueError("RECOVERY_RAW_BINDING")
        if raw['path'].lstrip('/') != '_pipeline/blobs/'+raw['sha256']+'.zip':
            raise ValueError("RECOVERY_RAW_PATH")
        self.verify_remote(raw, 'old RAW_INPUT.zip')
        expected = state['archives']['support']
        paths = {p.lstrip('/') for p in self.folder.list_paths_in_partition()}
        support = None
        content_address = '_pipeline/blobs/'+expected['sha256']+'.zip'
        if content_address in paths:
            support = {'path':content_address, **expected}
        elif 'PIPELINE_SUPPORT.zip.receipt.json' in paths:
            receipt = json.loads(_rc_bytes(self.folder,'PIPELINE_SUPPORT.zip.receipt.json'))
            if all(receipt.get(k) == expected[k] for k in ('sha256','bytes')):
                # Top-level uploads can be replaced next time. Preserve the old
                # bytes under an immutable content-address before removing scratch.
                source = {'path':'PIPELINE_SUPPORT.zip', **expected}
                self.verify_remote(source,'old PIPELINE_SUPPORT.zip upload')
                self.check()
                with self.folder.get_download_stream(source['path']) as stream:
                    self.folder.upload_stream(content_address,stream)
                support = {'path':content_address, **expected}
        if support:
            self.verify_remote(support,'old PIPELINE_SUPPORT.zip')
        else:
            support = self.preserve_file(state['support_zip'], expected, 'old PIPELINE_SUPPORT.zip')
        return {'raw':raw, 'support':support}

    def preserve_logs(self, auth):
        logs, total = {}, 0
        for name in ('worker.log','structure.log','prepare.log','index.log','return.log'):
            target = safe_path(self.local/(name+'.partial'))
            offset, h, missing = 0, hashlib.sha256(), False
            with target.open('wb') as output:
                os.chmod(target,0o600)
                while True:
                    try:
                        part = self.call('DOWNLOAD',**auth,file_name=name,offset=offset)
                    except RuntimeError as exc:
                        # Only the sealed service's explicit ENOENT at offset zero
                        # is optional-log absence. A failed request is not evidence.
                        if (offset == 0 and name not in ('worker.log','structure.log')
                                and str(exc).startswith('PIPELINE_REPLY: [Errno 2] No such file or directory:')):
                            logs[name]={'status':'NOT_CREATED_ENOENT'}; missing=True; break
                        raise
                    block=base64.b64decode(part['file_content_base64'],validate=True)
                    if (part.get('file_name') != name or part['offset'] != offset
                            or part['bytes'] != len(block) or len(block)>RECOVERY_CHUNK
                            or hashlib.sha256(block).hexdigest()!=part['sha256']):
                        raise ValueError('RECOVERY_LOG_CHUNK_HASH')
                    if not block: break
                    total += len(block)
                    if total > 64*RECOVERY_CHUNK: raise ValueError('RECOVERY_LOG_LIMIT')
                    if shutil.disk_usage(self.local).free < 512*RECOVERY_CHUNK+len(block):
                        raise ValueError('RECOVERY_DISK_LOW')
                    output.write(block);h.update(block);offset += len(block)
                output.flush();os.fsync(output.fileno())
            if not missing:
                logs[name]={'status':'PRESERVED', **self.preserve_file(target,{'sha256':h.hexdigest(),'bytes':offset},name)}
        return logs


def _rc_status_identity(status, state):
    if any(status.get(k) != state.get(k) for k in ('job_id','instance','code_sha256','archives','deadline')):
        raise ValueError('RECOVERY_REMOTE_IDENTITY')


def pipeline_release_previous(failed_job_name=FAILED_JOB_NAME):
    import dataiku
    if globals().get('DIAGNOSTIC_REVISION') != 'mapped-notebook-diagnostics-20261023-r2':
        raise ValueError('R2_RUNNER_REQUIRED: 먼저 R2 실행기 전체 셀을 실행하세요.')
    defaults=getattr(globals().get('run'),'__defaults__',None)
    if not defaults or len(defaults)!=4:raise ValueError('R2_RUNNER_SETTINGS')
    _, folder_name, work_dir, current_name = defaults
    if failed_job_name == current_name: raise ValueError('CANNOT_RELEASE_CURRENT_JOB')
    if dataiku.default_project_key()!='LEGAL_RAG':raise ValueError('LEGAL_RAG_REQUIRED')
    folder=dataiku.Folder(folder_name,project_key='LEGAL_RAG')
    variables=dataiku.get_custom_variables()
    module=sys.modules.get('dataiku_run')
    if module is None:raise ValueError('VERIFIED_CLIENT_NOT_LOADED')
    client=module.Client(variables['LEGAL_PIPELINE_URL'],variables['LEGAL_PIPELINE_TOKEN'])
    url_hash=hashlib.sha256(client.url.encode()).hexdigest()
    old, old_receipt=_rc_checkpoint(folder,failed_job_name,url_hash)
    new, _=_rc_checkpoint(folder,current_name,url_hash)
    state, new_state=old['client'],new['client']
    work=safe_path(work_dir)
    local=safe_path(work/'recovery'/state['job_id']);local.mkdir(parents=True,exist_ok=True,mode=0o700)
    auth={k:state[k] for k in ('job_id','job_token','instance','code_sha256')}
    identity={'failed_job_name':failed_job_name,'old_job_id':state['job_id'],
              'old_checkpoint':old_receipt,'current_job_name':current_name,'new_job_id':new_state['job_id'],
              'instance':state['instance'],'service_code':RECOVERY_SERVICE_SHA,'url_sha256':url_hash,
              'old_auth_sha256':hashlib.sha256(state['job_token'].encode()).hexdigest(),
              'new_archives':new_state['archives'],'new_deadline':new_state['deadline']}
    try:
        with (work/'runner.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            recovery=_Recovery(folder,client,identity,local)
            health=recovery.call('HEALTH')
            if (health['code_sha256']!=RECOVERY_SERVICE_SHA or health['instance']!=state['instance']
                    or health['instance']!=new_state['instance']):raise ValueError('RECOVERY_INSTANCE_CHANGED')
            status=recovery.call('STATUS',**auth);_rc_status_identity(status,state)
            if status['status']=='RELEASED':
                if recovery.state.get('preserved') and recovery.state.get('ack_intent'):
                    recovery.state['phase']='RELEASED';recovery.save()
                    print('RECOVERY_RELEASED',failed_job_name,'(기존 ACK 결과 재확인)',flush=True)
                    return {'status':'RELEASED','resumed_job_name':current_name,'ingestion_started':False}
                raise ValueError('ALREADY_RELEASED_WITHOUT_THIS_RECOVERY_RECEIPT')
            if status['status']!='FAILED' or status.get('phase')!='STRUCTURE' or status.get('result'):
                raise ValueError('RECOVERY_NOT_FAILED_STRUCTURE: '+str(status.get('status')))
            if recovery.state.get('ack_intent'):
                raise ValueError('ACK_OUTCOME_UNCERTAIN: 이전 ACK 의도가 기록됐습니다. 자동 재호출하지 않습니다.')
            if (new_state.get('status')!='NEW' or new_state.get('remote') or new.get('result_blob')
                    or time.time()>=new_state['deadline']):raise ValueError('CURRENT_JOB_NOT_UNSTARTED')
            new_auth={k:new_state[k] for k in ('job_id','job_token','instance','code_sha256')}
            try:
                recovery.call('STATUS',**new_auth)
            except RuntimeError as exc:
                if not str(exc).startswith('PIPELINE_REPLY: JOB_LOST:'):raise
            else:
                raise ValueError('CURRENT_JOB_ALREADY_ACCEPTED: 새 작업은 해제 대상이 아닙니다.')
            print('RECOVERY_TARGET',failed_job_name,'FAILED / STRUCTURE',flush=True)
            inputs=recovery.preserve_inputs(old)
            logs=recovery.preserve_logs(auth)
            recovery.state['preserved']={'inputs':inputs,'logs':logs,'old_status':status,
                                         'old_checkpoint':old_receipt,'original_sql_calls':old.get('reserved_sql_calls'),
                                         'original_deadline':old.get('deadline')}
            recovery.state['phase']='PRESERVED';recovery.save()
            # Checkpoint and current remote state must still match after streaming.
            _, fresh_receipt=_rc_checkpoint(folder,failed_job_name,url_hash)
            if fresh_receipt!=old_receipt:raise ValueError('RECOVERY_STALE_CHECKPOINT')
            again=recovery.call('STATUS',**auth);_rc_status_identity(again,state)
            if again['status']!='FAILED' or again.get('phase')!='STRUCTURE' or again.get('result'):
                raise ValueError('RECOVERY_STATE_CHANGED')
            recovery.state['ack_intent']=True;recovery.state['phase']='ACK_INTENT';recovery.save()
            result=recovery.call('ACK',**auth,discard_failed_attempt=True)
            _rc_status_identity(result,state)
            if result['status']!='RELEASED':raise ValueError('ACK_NOT_RELEASED')
            recovery.state['phase']='RELEASED';recovery.save()
            print('RECOVERY_RELEASED',failed_job_name,flush=True)
            print('PRESERVED_IN',recovery.prefix,flush=True)
            print('RESUME_SAME_JOB',current_name,'WORK_DIR',work_dir,flush=True)
            print('다음 셀: PIPELINE_RESULT = run(action="check")',flush=True)
            print('READY 확인 후: PIPELINE_RESULT = run(action="run")',flush=True)
            return {'status':'RELEASED','resumed_job_name':current_name,'ingestion_started':False}
    except Exception as exc:
        report=report_failure(exc,work=work,action='release_failed',job_name=failed_job_name,
                              folder=folder,phase='RECOVERY')
        raise RunError(report['code']+'\n'+'\n'.join(e['message'] for e in report['exceptions'])) from None


if __name__ == '__main__':
    RECOVERY_RESULT = pipeline_release_previous()
