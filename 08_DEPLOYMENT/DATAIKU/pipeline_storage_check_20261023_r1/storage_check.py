"""Paste this WHOLE file in a new cell in the same Dataiku R2 notebook.

Diagnoses SFTP storage using four NEW 2 KiB files. No GENOS API, release, large
upload, original-file changes, or recovery budget reset. Do not restart kernel.
"""
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
import uuid

STORAGE_CHECK_REVISION = 'dataiku-storage-check-20261023-r1'
STORAGE_FAILED_JOB = 'run_20261023_01_20261023_01'
STORAGE_CLIENT_SHA = '9d553a32d460b6ddfe4b73a4186dea5501a0b878512ccd622fa7cbae631b9bb3'
STORAGE_SERVICE_SHA = '771afb12a8fcf8c71417151cc80c8f4a9141e23d621ae27ec58cba67a7a22c46'


def _sc_read(folder, path, limit=1024*1024):
    with folder.get_download_stream(path) as stream:
        data = bytearray()
        while len(data) <= limit:
            block = stream.read(min(65536, limit+1-len(data)))
            if not block:
                break
            data.extend(block)
    if len(data) > limit:
        raise ValueError('STORAGE_METADATA_SIZE: '+path)
    return bytes(data)


def _sc_latest(folder, paths, prefix):
    items = []
    for path in paths:
        match = re.fullmatch(re.escape(prefix)+r'(\d{10})-([0-9a-f]{64})\.json', path)
        if match:
            items.append((int(match[1]), match[2], path))
    if not items:
        return None
    seq, sha, path = max(items)
    if sum(n == seq for n, _, _ in items) != 1:
        raise ValueError('STORAGE_CONCURRENT_CHECKPOINT')
    raw = _sc_read(folder, path)
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError('STORAGE_CHECKPOINT_HASH: '+path)
    return json.loads(raw), {'path': path, 'sha256': sha, 'bytes': len(raw)}


def _sc_clean(value, secrets):
    return _redact(value, secrets)


def _sc_sanitize_tree(value, secrets):
    if isinstance(value, str):
        return _sc_clean(value, secrets)
    if isinstance(value, list):
        return [_sc_sanitize_tree(v, secrets) for v in value]
    if isinstance(value, dict):
        return {k: _sc_sanitize_tree(v, secrets) for k, v in value.items()}
    return value


def _sc_errors(exc, secrets):
    rows, seen = [], set()
    for _ in range(12):
        if not isinstance(exc, BaseException) or id(exc) in seen:
            break
        seen.add(id(exc))
        rows.append({'type': type(exc).__name__, 'message': _sc_clean(str(exc), secrets)[:16384]})
        exc = exc.__cause__ or exc.__context__
    return rows


def _sc_append(path, item):
    raw = (json.dumps(item, ensure_ascii=False, sort_keys=True)+'\n').encode()
    # Persist each intent BEFORE its corresponding storage operation.
    with safe_path(path).open('ab') as out:
        os.chmod(path, 0o600)
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())


def _sc_rows(path):
    with safe_path(path).open('rb') as stream:
        raw = stream.read(512*1024+1)
    if len(raw) > 512*1024:
        raise ValueError('STORAGE_JOURNAL_LIMIT')
    if raw and not raw.endswith(b'\n'):
        raise ValueError('STORAGE_JOURNAL_INCOMPLETE: 쓰기를 반복하지 않습니다.')
    return [json.loads(line) for line in raw.splitlines()]


def _sc_checkpoint(folder, paths, name, url_sha, secrets):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', name):
        raise ValueError('STORAGE_JOB_NAME')
    found = _sc_latest(folder, paths, '_pipeline/jobs/'+name+'/checkpoint-')
    if not found:
        raise ValueError('STORAGE_CHECKPOINT_MISSING: '+name)
    checkpoint, receipt = found
    binding = checkpoint['binding']
    source = binding['input']
    state = checkpoint['client']
    secrets.append(state.get('job_token'))
    if (source['folder_id'] != folder.get_id() or source['project'] != 'LEGAL_RAG'
            or source['client_sha256'] != STORAGE_CLIENT_SHA
            or binding['service_code'] != STORAGE_SERVICE_SHA
            or state['code_sha256'] != STORAGE_SERVICE_SHA
            or binding['service_url_sha256'] != url_sha
            or not re.fullmatch(r'[a-f0-9]{32}', state['job_id'])):
        raise ValueError('STORAGE_BINDING_MISMATCH: '+name)
    return checkpoint, receipt


def _sc_probe(folder, path, data, label, journal, previous, deadline, secrets):
    finished = next((r for r in reversed(previous)
                     if r.get('kind') == 'probe_result' and r.get('label') == label), None)
    if finished:
        print('PROBE_REUSED', label, finished['status'], path, flush=True)
        return finished
    started = any(r.get('kind') == 'probe_intent' and r.get('label') == label for r in previous)
    row = {'kind': 'probe_result', 'label': label, 'path': path,
           'expected_bytes': len(data), 'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'operation': 'READBACK_AFTER_INTERRUPTION' if started else 'UPLOAD', 'status': 'UNKNOWN'}
    begin = time.monotonic()
    if time.time() >= deadline:
        row.update(status='NOT_ATTEMPTED', reason='STORAGE_CHECK_DEADLINE_EXHAUSTED')
    else:
        if not started:
            _sc_append(journal, {'kind': 'probe_intent', 'label': label, 'path': path, 'bytes': len(data)})
        try:
            if not started:
                print('STORAGE_OPERATION UPLOAD', label, path, len(data), 'bytes', flush=True)
                folder.upload_stream(path, io.BytesIO(data))
            row['operation'] = 'READBACK_AFTER_INTERRUPTION' if started else 'READBACK'
            print('STORAGE_OPERATION', row['operation'], label, path, flush=True)
            if _sc_read(folder, path, len(data)) != data:
                raise ValueError('STORAGE_PROBE_READBACK_MISMATCH')
            row.update(status='PASS', sha256=hashlib.sha256(data).hexdigest())
        except Exception as exc:
            row.update(status='FAILED' if not started else 'UNCONFIRMED', errors=_sc_errors(exc, secrets))
    row['elapsed_seconds'] = round(time.monotonic()-begin, 3)
    _sc_append(journal, row)
    print('PROBE_RESULT', json.dumps(row, ensure_ascii=False), flush=True)
    return row


def _sc_diagnosis(probes):
    passed = {p['label'] for p in probes if p['status'] == 'PASS'}
    if len(passed) == 4:
        return ('SMALL_FILES_OK_LARGE_UPLOAD_UNVERIFIED',
                '작은 파일 네 경로는 쓰기·읽기 성공. 2.27GB 보관 가능 여부는 미확인입니다. '
                '원격 여유 공간·사용자 쿼터·파일 크기 제한·최초 실패 시각의 SFTP 로그를 확인해야 합니다.')
    if 'recovery_parent' in passed and 'recovery_files' not in passed:
        return ('RECOVERY_CHILD_PATH_DIFFERS',
                '기존 복구 부모 경로는 성공했지만 files 하위는 실패/미확인입니다. '
                '해당 하위 경로 생성·쓰기 권한과 같은 시각 서버 로그를 확인하세요. 원인 확정은 아닙니다.')
    if not passed:
        return ('STORAGE_WRITE_OR_READBACK_FAILED',
                '검사한 모든 경로에서 쓰기·재조회가 확인되지 않았습니다. 각 operation을 확인하고 '
                'Dataiku 연결 계정의 원격 권한·공간·쿼터·SFTP 로그를 확인하세요.')
    return ('STORAGE_PATH_RESULTS_DIFFER',
            '경로별 결과가 다릅니다. 실패 경로와 operation·원래 오류를 기준으로 원격 저장소를 확인하세요.')


def pipeline_recovery_storage_check(failed_job_name=STORAGE_FAILED_JOB,
                                    check_name='storage-check-20261023-r1'):
    """Four tiny writes at most; no pipeline action, auto-retry, or large archive read."""
    import dataiku
    if globals().get('DIAGNOSTIC_REVISION') != 'mapped-notebook-diagnostics-20261023-r2':
        raise ValueError('R2_RUNNER_REQUIRED: R2 실행기가 있는 같은 노트북·커널에서 실행하세요.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', check_name):
        raise ValueError('STORAGE_CHECK_NAME')
    defaults = getattr(globals().get('run'), '__defaults__', None)
    if not defaults or len(defaults) != 4:
        raise ValueError('R2_RUNNER_SETTINGS')
    _, folder_name, work_dir, current_name = defaults
    if dataiku.default_project_key() != 'LEGAL_RAG' or current_name == failed_job_name:
        raise ValueError('STORAGE_PROJECT_OR_JOB')
    secrets = []
    work = safe_path(work_dir)
    report_path = None
    try:
        variables = dataiku.get_custom_variables()
        secrets.extend(v for k, v in variables.items()
                       if re.search(r'TOKEN|PASSWORD|PASSWD|SECRET|COOKIE|API_KEY', k, re.I))
        # Hash the same endpoint representation as the shipped Client; no request.
        import sys
        module = sys.modules.get('dataiku_run')
        if module is None:
            raise ValueError('VERIFIED_CLIENT_NOT_LOADED')
        client = module.Client(variables['LEGAL_PIPELINE_URL'], variables['LEGAL_PIPELINE_TOKEN'])
        url_sha = hashlib.sha256(client.url.encode()).hexdigest()
        folder = dataiku.Folder(folder_name, project_key='LEGAL_RAG')
        print('STORAGE_CHECK_BEGIN', STORAGE_CHECK_REVISION, 'FOLDER', folder_name,
              'WORK_DIR', work_dir, 'CURRENT_JOB', current_name, flush=True)
        paths = set()
        for i, path in enumerate(folder.list_paths_in_partition()):
            if i >= 100000:
                raise ValueError('STORAGE_PATH_LIMIT')
            paths.add(path.lstrip('/'))
        old, old_receipt = _sc_checkpoint(folder, paths, failed_job_name, url_sha, secrets)
        new, new_receipt = _sc_checkpoint(folder, paths, current_name, url_sha, secrets)
        old_state, new_state = old['client'], new['client']
        prefix = '_pipeline/recovery/'+old_state['job_id']+'/'
        recovery = _sc_latest(folder, paths, prefix+'event-')
        recovery_state = recovery[0] if recovery else None
        if recovery_state and (recovery_state['identity']['old_job_id'] != old_state['job_id']
                               or recovery_state['identity']['current_job_name'] != current_name
                               or recovery_state['identity']['new_job_id'] != new_state['job_id']):
            raise ValueError('STORAGE_RECOVERY_IDENTITY')
        local = safe_path(work/'diagnostics'/'storage-checks')
        local.mkdir(parents=True, exist_ok=True, mode=0o700)
        journal = safe_path(local/(check_name+'.jsonl'))
        identity = {'old_checkpoint': old_receipt, 'new_checkpoint': new_receipt,
                    'folder_id': folder.get_id(), 'url_sha256': url_sha, 'revision': STORAGE_CHECK_REVISION}
        with safe_path(work/'runner.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            previous = _sc_rows(journal) if journal.exists() else []
            if previous:
                header = previous[0]
                if header.get('kind') != 'header' or header.get('identity') != identity:
                    raise ValueError('STORAGE_CHECK_IDENTITY_CHANGED')
            else:
                header = {'kind': 'header', 'identity': identity, 'id': uuid.uuid4().hex,
                          'deadline': time.time()+300, 'max_writes': 4, 'max_write_bytes': 8192}
                _sc_append(journal, header)
            probe_id = header['id']
            data = (json.dumps({'purpose': STORAGE_CHECK_REVISION, 'id': probe_id})+'\n').encode().ljust(2048, b' ')
            probe_paths = [('root', 'pipeline-storage-probe-'+probe_id+'.json'),
                           ('recovery_parent', prefix+'storage-probe-'+probe_id+'.json'),
                           ('recovery_files', prefix+'files/storage-probe-'+probe_id+'.json'),
                           ('diagnostics_child', '_pipeline/diagnostics/'+failed_job_name+'/storage-probe-'+probe_id+'.json')]
            # New names only. A pre-existing path without our persisted intent is a collision.
            for label, path in probe_paths:
                if path in paths and not any(r.get('kind') == 'probe_intent' and r.get('label') == label for r in previous):
                    raise ValueError('STORAGE_PROBE_PATH_EXISTS: '+path)
            probes = [_sc_probe(folder, path, data, label, journal, previous, header['deadline'], secrets)
                      for label, path in probe_paths]
            expected = old_state['archives']['support']
            support_path = safe_path(old_state['support_zip'])
            try:
                stat = support_path.stat()
                local_support = {'path': str(support_path), 'exists': True, 'bytes': stat.st_size,
                                 'size_matches': stat.st_size == expected['bytes'], 'hash_checked': False}
            except OSError as exc:
                local_support = {'path': str(support_path), 'status': 'STAT_FAILED', 'errors': _sc_errors(exc, secrets)}
            old_destination = prefix+'files/'+expected['sha256']+'.bin'
            snapshots = []
            for p in sorted((work/'diagnostics').glob('error-*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:3]:
                try:
                    saved = _read_small_json(p)
                    snapshots.append({'file': str(p), 'code': saved.get('code'), 'action': saved.get('action'),
                                      'operation': saved.get('operation'), 'time': saved.get('time'),
                                      'exceptions': saved.get('exceptions', [])})
                except Exception as exc:
                    snapshots.append({'file': str(p), 'errors': _sc_errors(exc, secrets)})
            code, explanation = _sc_diagnosis(probes)
            report = {'revision': STORAGE_CHECK_REVISION, 'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                      'status': 'CHECK_COMPLETE' if all(p['status'] in ('PASS','FAILED') for p in probes) else 'CHECK_INCOMPLETE',
                      'diagnosis': code, 'explanation': explanation, 'failed_job': failed_job_name,
                      'current_job': current_name, 'probes': probes, 'local_support': local_support,
                      'old_support_expected': expected, 'old_upload_path': old_destination,
                      'old_upload_listed': old_destination in paths, 'old_upload_completeness': 'NOT_VERIFIED',
                      'recovery_record': None if not recovery_state else {
                          'phase': recovery_state.get('phase'), 'deadline': recovery_state.get('deadline'),
                          'deadline_expired': time.time() >= recovery_state['deadline'],
                          'api_calls': recovery_state.get('api_calls'), 'ack_intent': bool(recovery_state.get('ack_intent'))},
                      'current_job_deadline': new_state['deadline'],
                      'current_job_deadline_expired': time.time() >= new_state['deadline'],
                      'current_sql_calls': new.get('reserved_sql_calls'), 'previous_diagnostics': snapshots,
                      'pipeline_api_calls': 0, 'pipeline_released': False, 'large_upload_attempts': 0,
                      'remote_capacity': 'UNKNOWN', 'probe_bytes_per_file': 2048,
                      'journal': str(journal), 'automatic_retry': False}
            # Sanitize all imported exception text before displaying/storing.
            raw = (json.dumps(_sc_sanitize_tree(report, secrets), ensure_ascii=False, indent=2)+'\n').encode()
            print('STORAGE_CHECK_REPORT_BEGIN\n'+raw.decode()+'STORAGE_CHECK_REPORT_END', flush=True)
            report_path = safe_path(local/(check_name+'-report-'+uuid.uuid4().hex+'.json'))
            with report_path.open('xb') as output:
                os.chmod(report_path, 0o600)
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            print('STORAGE_REPORT_LOCAL', report_path, flush=True)
            print('NEXT_STEP: 이 결과를 확인한 뒤 복구합니다. 원래 release/run 셀을 아직 반복하지 마세요.', flush=True)
            if recovery_state and time.time() >= recovery_state['deadline']:
                print('RECOVERY_DEADLINE_EXHAUSTED: 기존 복구 기한은 만료됐습니다. 값을 고치거나 기록을 삭제하지 않았습니다.', flush=True)
            print('NO_GENOS_CALL_NO_ACK_NO_LARGE_UPLOAD', flush=True)
            # Do not return unsanitized exception strings to the notebook display.
            return {'status': report['status'], 'diagnosis': code, 'report_file': str(report_path),
                    'pipeline_released': False, 'pipeline_api_calls': 0}
    except Exception as exc:
        errors = _sc_errors(exc, secrets)
        print('STORAGE_CHECK_ABORTED', json.dumps(errors, ensure_ascii=False), flush=True)
        # Use the already-installed detailed reporter, but do not attempt another
        # write to the managed folder whose storage is being diagnosed.
        exc._pipeline_secrets = tuple(secrets)
        report_failure(exc, work=work, action='storage_check', job_name=failed_job_name,
                       folder=None, phase='MANAGED_STORAGE')
        raise RunError('STORAGE_CHECK_ABORTED: '+errors[0]['message']) from None


if __name__ == '__main__':
    STORAGE_CHECK_RESULT = pipeline_recovery_storage_check()
