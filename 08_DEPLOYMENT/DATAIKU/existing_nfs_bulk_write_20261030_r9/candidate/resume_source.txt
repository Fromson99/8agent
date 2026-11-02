"""Resume the existing batch and its budget before materializing any raw files."""
import copy
import hashlib
import json
import re
import time


class ReservedStart:
    """Deliver the checked START reply once to the unchanged upload client."""
    def __init__(self, remote, fields, reply):
        self.remote, self.fields, self.reply = remote, fields, reply

    def call(self, operation, **fields):
        if operation == 'START' and self.reply is not None:
            if fields != self.fields:
                raise ValueError('RESUME_START_CHANGED')
            reply, self.reply = self.reply, None
            return reply
        return self.remote.call(operation, **fields)


def validate_saved(r, store, receipts):
    state = store.value['client']
    if (state.get('code_sha256') != r.EXPECTED
            or state.get('deadline') != store.value['deadline']
            or state.get('archives', {}).get('support') !=
                {k: receipts['PIPELINE_SUPPORT.zip'][k] for k in ('sha256', 'bytes')}):
        raise ValueError('RESUME_CLIENT_BINDING')
    for key, expected in [('raw_blob', state['archives']['raw'])]:
        blob = store.value.get(key, {})
        if (any(blob.get(k) != expected[k] for k in ('sha256', 'bytes'))
                or blob.get('path') != '_pipeline/blobs/' + expected['sha256'] + '.zip'):
            raise ValueError('RESUME_RAW_CHECKPOINT_REQUIRED')
    if state.get('status') == 'DOWNLOADED':
        result, blob = state.get('result', {}), store.value.get('result_blob', {})
        if (not result or any(blob.get(k) != result.get(k) for k in ('sha256', 'bytes'))
                or blob.get('path') != '_pipeline/blobs/' + result['sha256'] + '.zip'):
            raise ValueError('RESUME_RESULT_BINDING')
    return state


def install_resume(r):
    if getattr(r.structure, '_resume_revision', None) == 'resume-20261027-r3':
        return
    original = r.structure

    def structure(cfg, folders, variables, work, job_name):
        receipts = r.input_receipts(folders['landing'])
        oracle, binding, remote, identity = r.context(cfg, receipts, variables)
        store = r.ManagedJob(folders['structured'], job_name, identity)
        if store.value.get('phase') == 'STRUCTURED':
            record = r.structured_record(store)
            r.put_json(folders['structured'], 'jobs/'+job_name+'/structured.json', record, work)
            return {k:v for k,v in record.items() if k != 'binding'}
        if 'client' not in store.value:
            # No durable client exists yet. Keep the original first-run contract.
            print('FIRST_PREPARATION: 기존 방식으로 입력을 준비합니다.', flush=True)
            return original(cfg, folders, variables, work, job_name)
        state = validate_saved(r, store, receipts)
        if time.time() >= store.value['deadline']:
            raise ValueError('JOB_DEADLINE_EXHAUSTED')
        job = work / 'job'
        job.mkdir(parents=True, exist_ok=True)
        r.t.write(job/'client.json', state)
        wrapped, status = remote, 'DOWNLOADED'
        if state['status'] != 'DOWNLOADED':
            fields = {k:state[k] for k in ('job_id','job_token','instance','code_sha256')}
            fields.update(archives=state['archives'], deadline=state['deadline'])
            # Same job/capability, exact archives, original deadline. BUSY exits
            # before any raw/support blob download or SQL preflight reservation.
            reply = remote.call('START', **fields)
            if (not isinstance(reply, dict)
                    or any(reply.get(k) != fields[k] for k in
                           ('job_id','instance','code_sha256','archives','deadline'))):
                raise ValueError('RESUME_REMOTE_BINDING')
            status = reply.get('status')
            if status not in {'UPLOADING','RUNNING','COMPLETE'}:
                if status not in {'FAILED','CANCELLED','INTERRUPTED','RELEASED'}:
                    raise ValueError('RESUME_REMOTE_STATUS')
                state.update(status=status, remote=reply)
                store.value.update(client=state, phase=status)
                store.save()
                raise RuntimeError('PIPELINE_' + status + ': 기존 작업 상태 확인이 필요합니다.')
            wrapped = ReservedStart(remote, fields, reply)
        print('RESUME_REMOTE', status, 'JOB_NAME', job_name,
              '개별 원문 재다운로드=0; 새 작업 ID 생성=0', flush=True)
        from semantic_runtime import oracle_dp_io as dbio
        bounded = r.BudgetClient(oracle, store)
        oracle.schema_map.preflight(dbio.SQL(bounded, journal=work/'preflight.jsonl', binding=binding))
        support_path = work/'PIPELINE_SUPPORT.zip'
        if status == 'UPLOADING':
            print('RESUME_ZIP_RESTORE: 저장된 입력 ZIP을 복원하고 미전송 부분부터 전송합니다.', flush=True)
            store.get_blob(store.value['raw_blob'], job/'RAW_INPUT.zip')
            support = receipts['PIPELINE_SUPPORT.zip']
            r.legacy.download(folders['landing'], support['remote'], support_path,
                              support['sha256'], support['bytes'], work)
        elif status == 'DOWNLOADED':
            store.get_blob(store.value['result_blob'], job/'result.zip')
        # process reads client.json first. RUNNING/COMPLETE require no raw or
        # support local files; DOWNLOADED needs only the verified result blob.
        r.client.process(wrapped, work/'inputs', support_path, job,
                         expected_code_sha256=r.EXPECTED,
                         checkpoint=store.checkpoint_client, deadline=store.value['deadline'])
        store.value['phase'] = 'STRUCTURED'
        store.save()
        record = r.structured_record(store)
        r.put_json(folders['structured'], 'jobs/'+job_name+'/structured.json', record, work)
        return {k:v for k,v in record.items() if k != 'binding'}

    structure._resume_revision = 'resume-20261027-r3'
    r.structure = structure


def inspect_jobs(r, folders, variables, limit=20):
    """Read only known Flow folders; HEALTH/STATUS, never START/CANCEL/ACK."""
    remote = r.remote_client(variables)
    health = remote.call('HEALTH')
    if health.get('code_sha256') != r.EXPECTED:
        raise ValueError('DEPLOYED_CODE_MISMATCH')
    endpoint = hashlib.sha256(remote.url.encode()).hexdigest()
    pattern = re.compile(r'_pipeline/jobs/([A-Za-z0-9_-]{1,80})/checkpoint-(\d{10})-([0-9a-f]{64})\.json')
    latest = {}
    for folder_id, folder in folders.items():
        for index, path in enumerate(folder.list_paths_in_partition()):
            if index >= 100000:
                raise ValueError('INSPECTION_PATH_LIMIT')
            m = pattern.fullmatch(path.lstrip('/'))
            if not m:
                continue
            key, seq = (folder_id, m[1]), int(m[2])
            if key not in latest or seq > latest[key][0]:
                latest[key] = (seq, m[3], path, 1)
            elif seq == latest[key][0]:
                previous = latest[key]
                latest[key] = (*previous[:3], previous[3]+1)
    if len(latest) > limit:
        raise ValueError('INSPECTION_JOB_LIMIT')
    rows, responses = [], {}
    for (folder_id, name), (_, sha, path, count) in sorted(latest.items()):
        if count != 1:
            raise ValueError('CONCURRENT_JOB_CHECKPOINT')
        with folders[folder_id].get_download_stream(path) as stream:
            raw = r.bounded_read(stream, 1024*1024)
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError('CHECKPOINT_HASH')
        checkpoint = json.loads(raw)
        binding, state = checkpoint.get('binding', {}), checkpoint.get('client')
        row = {'folder_id':folder_id, 'job_name':name, 'checkpoint':path,
               'local_phase':checkpoint.get('phase')}
        if not state:
            row['status'] = 'NO_CLIENT_CHECKPOINT'
        elif (binding.get('service_url_sha256') != endpoint
                or binding.get('service_code') != r.EXPECTED
                or state.get('code_sha256') != r.EXPECTED):
            row['status'] = 'BINDING_DIFFERS_NO_CALL'
        elif state.get('instance') != health.get('instance'):
            row['status'] = 'INSTANCE_DIFFERS_NO_CALL'
        else:
            row['job_id'] = state['job_id']
            auth = {k:state[k] for k in ('job_id','job_token','instance','code_sha256')}
            key = r.t.digest(auth)
            if key not in responses:
                try:
                    reply = remote.call('STATUS', **auth)
                    if any(reply.get(k) != auth[k] for k in ('job_id','instance','code_sha256')):
                        raise ValueError('STATUS_BINDING')
                    if reply.get('status') not in {'UPLOADING','RUNNING','COMPLETE','FAILED','CANCELLED','INTERRUPTED','RELEASED'}:
                        raise ValueError('STATUS_CONTRACT')
                    phase = reply.get('phase')
                    responses[key] = {'status':reply['status'], 'phase':phase if phase in
                        {'VERIFY_INPUTS','STRUCTURE','PREPARE','INDEX','QUERY','RETURN','RETURN_READY','PACKAGE'} else None}
                except Exception as exc:
                    # CheckedClient never prints server text or credentials.
                    public = str(exc).split(':',1)[0]
                    if not re.fullmatch(r'GENOS_[A-Z0-9_]+|GENOS_REPLY_[0-9a-f]{16}', public):
                        public = 'STATUS_ERROR_' + type(exc).__name__
                    responses[key] = {'status':'STATUS_UNCONFIRMED','error':public}
            row.update(responses[key])
        rows.append(row)
        print('GENOS_JOB', json.dumps(row, ensure_ascii=False, sort_keys=True), flush=True)
    print('JOB_INSPECTION_COMPLETE: HEALTH/STATUS만 조회했습니다. 자동 취소·ACK·삭제·배치 실행 없음.', flush=True)
    print('STATUS_UNCONFIRMED/목록 없음은 기존 작업이 없다는 뜻이 아닙니다.', flush=True)
    return rows
