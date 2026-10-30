"""Inspect the existing notebook and Flow checkpoints; never submit/release work."""
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

PROJECT = 'LEGAL_RAG'
LANDING = 'ehA8dpVm'
SERVICE_SHA = '771afb12a8fcf8c71417151cc80c8f4a9141e23d621ae27ec58cba67a7a22c46'
CLIENT_SHAS = {
    '9d553a32d460b6ddfe4b73a4186dea5501a0b878512ccd622fa7cbae631b9bb3',
    '4f0f301f37208624fc51a5dde9bab84333eb2eeed1f5f7fd217d831e5c2bfef5',
}
PATTERN = re.compile(r'_pipeline/jobs/([A-Za-z0-9_-]{1,80})/checkpoint-(\d{10})-([0-9a-f]{64})\.json')
STATUSES = {'NEW', 'UPLOADING', 'RUNNING', 'FAILED', 'CANCELLED', 'INTERRUPTED',
            'COMPLETE', 'RELEASED', 'DOWNLOADED', 'STRUCTURED', 'LOAD_VERIFIED',
            'LOAD_VERIFIED_ACK_PENDING', 'STOPPED'}
ERRORS = {'BUSY', 'JOB_LOST', 'UNKNOWN_JOB', 'INSTANCE_CHANGED', 'INSTANCE_MISMATCH',
          'CODE_BINDING_CHANGED', 'JOB_CODE_CHANGED', 'JOB_AUTH', 'STAGE_FAILED',
          'WORKER_LOST', 'DEADLINE_EXHAUSTED', 'INVALID_JOB_CREDENTIALS'}


class InspectionError(RuntimeError):
    pass


def read_small(stream):
    parts, total = [], 0
    while True:
        block = stream.read(min(65536, 1024 * 1024 + 1 - total))
        if not block:
            return b''.join(parts)
        total += len(block)
        if total > 1024 * 1024:
            raise InspectionError('RECORD_TOO_LARGE')
        parts.append(block)


def error_code(value):
    code = str(value).split(':', 1)[0]
    return code if code in ERRORS else 'DETAIL_WITHHELD'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class StatusClient:
    def __init__(self, variables):
        self.url = variables.get('LEGAL_PIPELINE_URL', '')
        self.token = variables.get('LEGAL_PIPELINE_TOKEN', '')
        if not isinstance(self.url, str) or not isinstance(self.token, str) or not self.token.strip():
            raise InspectionError('PROJECT_VARIABLE_REQUIRED')
        parsed = urllib.parse.urlsplit(self.url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                or parsed.password or parsed.fragment):
            raise InspectionError('HTTPS_ENDPOINT_REQUIRED')
        self.endpoint_sha = hashlib.sha256(self.url.encode()).hexdigest()
        self.deadline = time.monotonic() + 120
        self.calls = 0

    def call(self, operation, **fields):
        if operation not in {'HEALTH', 'STATUS'}:
            raise InspectionError('INSPECTION_OPERATION_ONLY')
        remaining = self.deadline - time.monotonic()
        if remaining <= 0 or self.calls >= 41:
            raise InspectionError('INSPECTION_BUDGET')
        self.calls += 1
        request = urllib.request.Request(self.url, method='POST',
            data=json.dumps({'API_TYPE': operation, **fields}).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.token})
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=min(15, remaining)) as response:
                raw = read_small(response)
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise InspectionError('GENOS_HTTP_' + str(code)) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise InspectionError('GENOS_TRANSPORT_UNCONFIRMED') from None
        try:
            reply = json.loads(raw)
        except (ValueError, UnicodeError):
            raise InspectionError('GENOS_NOT_JSON') from None
        if not isinstance(reply, dict):
            raise InspectionError('GENOS_REPLY_CONTRACT')
        if reply.get('code') != 0:
            raise InspectionError(error_code(reply.get('error', ''))) from None
        if not isinstance(reply.get('data'), dict):
            raise InspectionError('GENOS_REPLY_CONTRACT')
        return reply['data']


def latest_checkpoints(folder):
    latest = {}
    for index, path in enumerate(folder.list_paths_in_partition()):
        if index >= 100000:
            raise InspectionError('CHECKPOINT_PATH_LIMIT')
        clean = path.lstrip('/')
        match = PATTERN.fullmatch(clean)
        if not match:
            if clean.startswith('_pipeline/jobs/') and '/checkpoint-' in clean:
                raise InspectionError('CHECKPOINT_NAME')
            continue
        name, seq, sha = match[1], int(match[2]), match[3]
        if name not in latest or seq > latest[name][0]:
            latest[name] = (seq, [(sha, path)])
        elif seq == latest[name][0]:
            latest[name][1].append((sha, path))
    if len(latest) > 20:
        raise InspectionError('CHECKPOINT_JOB_LIMIT')
    for name, (_, records) in sorted(latest.items()):
        if len(records) != 1:
            raise InspectionError('CONCURRENT_JOB_CHECKPOINT')
        sha, path = records[0]
        with folder.get_download_stream(path) as stream:
            raw = read_small(stream)
        if hashlib.sha256(raw).hexdigest() != sha:
            raise InspectionError('CHECKPOINT_HASH')
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            raise InspectionError('CHECKPOINT_JSON') from None
        if not isinstance(value, dict):
            raise InspectionError('CHECKPOINT_CONTRACT')
        yield name, value


def inspect_folder(folder, role, raw_id, remote, health):
    rows = []
    for name, checkpoint in latest_checkpoints(folder):
        row = {'folder_role': role, 'job_name': name}
        binding = checkpoint.get('binding', {})
        inputs = binding.get('input', {})
        if role == 'legacy':
            match = (inputs.get('project') == PROJECT and inputs.get('folder_id') == LANDING
                     and inputs.get('client_sha256') in CLIENT_SHAS)
        else:
            match = (binding.get('version') == 'recipes-20261027-r1'
                     and inputs.get('landing') == LANDING and inputs.get('raw') == raw_id)
        if not match or binding.get('service_url_sha256') != remote.endpoint_sha or binding.get('service_code') != SERVICE_SHA:
            row['status'] = 'SKIPPED_BINDING'
        elif not checkpoint.get('client'):
            row['status'] = 'NO_CLIENT_STATE'
        else:
            state = checkpoint['client']
            row['saved_status'] = state.get('status') if state.get('status') in STATUSES else 'UNKNOWN'
            if (not re.fullmatch('[0-9a-f]{32}', str(state.get('job_id', '')))
                    or not re.fullmatch('[0-9a-f]{64}', str(state.get('job_token', '')))
                    or state.get('code_sha256') != SERVICE_SHA):
                raise InspectionError('CHECKPOINT_AUTH_BINDING')
            row['job_id'] = state['job_id']
            if state.get('instance') != health['instance']:
                row['status'] = 'INSTANCE_CHANGED'
            else:
                auth = {k: state[k] for k in ('job_id', 'job_token', 'instance', 'code_sha256')}
                try:
                    status = remote.call('STATUS', **auth)
                    if any(status.get(k) != auth[k] for k in ('job_id', 'instance', 'code_sha256')):
                        raise InspectionError('STATUS_BINDING')
                    if status.get('status') not in STATUSES - {'NEW', 'DOWNLOADED', 'STRUCTURED', 'LOAD_VERIFIED', 'LOAD_VERIFIED_ACK_PENDING', 'STOPPED'}:
                        raise InspectionError('STATUS_CONTRACT')
                    row['status'] = status['status']
                    row['phase'] = status.get('phase') if status.get('phase') in {'PREPARE', 'STRUCTURE', 'INDEX', 'QUERY', 'PACKAGE'} else 'UNSPECIFIED'
                    if status.get('error'):
                        row['error_code'] = error_code(status['error'])
                    row['blocks_new_start'] = status['status'] != 'RELEASED'
                except InspectionError as exc:
                    row.update(status='STATUS_UNCONFIRMED', error_code=str(exc))
        rows.append(row)
    return rows


def inspect_all(dataiku):
    if dataiku.default_project_key() != PROJECT:
        raise InspectionError('LEGAL_RAG_PROJECT_REQUIRED')
    remote = StatusClient(dataiku.get_custom_variables())
    health = remote.call('HEALTH')
    if health.get('code_sha256') != SERVICE_SHA:
        raise InspectionError('DEPLOYED_CODE_MISMATCH')
    if not re.fullmatch('[0-9a-f]{32}', str(health.get('instance', ''))):
        raise InspectionError('HEALTH_CONTRACT')
    project = dataiku.api_client().get_project(PROJECT)
    known = project.list_managed_folders()
    def folder_id(name):
        found = [x['id'] for x in known if x['name'] == name]
        if len(found) != 1:
            raise InspectionError('FLOW_FOLDER_MISSING_OR_AMBIGUOUS')
        return found[0]
    raw_id = folder_id('LEGAL_RAW_SOURCE_R1')
    folders = [('legacy', LANDING), ('structured', folder_id('LEGAL_STRUCTURED_RESULT_R1')),
               ('load', folder_id('LEGAL_LGL_LOAD_RESULT_R1'))]
    rows = []
    for role, fid in folders:
        try:
            current = inspect_folder(dataiku.Folder(fid, project_key=PROJECT), role, raw_id, remote, health)
        except InspectionError as exc:
            current = [{'folder_role': role, 'status': 'CHECKPOINT_UNCONFIRMED', 'error_code': str(exc)}]
        rows.extend(current)
        for row in current:
            print(json.dumps(row, ensure_ascii=False), flush=True)
    blockers = sorted({r['job_id'] for r in rows if r.get('blocks_new_start')})
    print(json.dumps({'inspection': 'FINISHED', 'blocking_job_ids': blockers,
        'blocking_job_identified': bool(blockers), 'genos_calls': remote.calls,
        'note': '조회 범위에서 찾은 작업입니다. 빈 목록은 GENOS 작업 부재의 증명이 아닙니다.'}, ensure_ascii=False), flush=True)
    print('ACK·CANCEL·START·EXECUTE·Oracle·S3 쓰기 없음. STATUS는 유실 실행을 INTERRUPTED로 갱신할 수 있습니다.', flush=True)
    return rows


def main():
    import dataiku
    try:
        return inspect_all(dataiku)
    except InspectionError as exc:
        print('INSPECTION_STOPPED: ' + str(exc), flush=True)
    except Exception as exc:
        # SDK exception text may contain URLs or credentials. Keep it out of shared logs.
        print('INSPECTION_STOPPED: SDK_OR_RECORD_ERROR / ' + type(exc).__name__, flush=True)


if __name__ == '__main__':
    PIPELINE_JOBS = main()
