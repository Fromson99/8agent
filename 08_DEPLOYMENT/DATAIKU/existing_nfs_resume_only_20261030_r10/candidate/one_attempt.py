"""One explicit operator grant after three confirmed no-model attempts.

The original deadline and all usage remain unchanged. A grant binds one immutable
checkpoint to the current R10 code; it is neither automatic nor a counter reset.
"""
import hashlib
import io
import json
import math
import re
import time

CONFIRMATION = 'AUTHORIZE_ONE_ADDITIONAL_COMPUTE_ATTEMPT'
R10 = '55ab3cf767199ed70f29475e15403874b7ccacc1e306130f6467da04c5b3499d'
KNOWN_PREVIOUS = {
    '1982ddf7ab401b01ab4a59b37b4006a395adfaead7c7231a4520e2d965c35e5c',
    'f88b1426f29bc16a862a1a67c72bff8a0d15b106a84aa2ca3dc9f80f4820c084',
    'aa73eedbbee5f9f4e842c87e7f0fca2278c2dc56b936390871fbf268efea7c73',
}


def checked(folder, name, latest, identity):
    import controller as c
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', name):
        raise ValueError('JOB_NAME')
    if not latest or c.legacy_state(folder, name) != latest:
        raise ValueError('RECOVERY_CHECKPOINT_CHANGED')
    old = latest['value']
    previous = old['binding'].get('service_code')
    if identity.get('service_code') != R10 or previous not in KNOWN_PREVIOUS or old['binding'] != {**identity, 'service_code': previous}:
        raise ValueError('RECOVERY_INPUT_TARGET_OR_CODE_CHANGED')
    compute, observed = old.get('compute') or {}, old.get('last_observed') or {}
    if (old.get('phase') not in {'FAILED', 'CANCELLED'} or observed.get('state') != old['phase']
            or not compute.get('handle') or observed.get('handle') != compute['handle']
            or compute.get('code_sha256') != previous):
        raise ValueError('RECOVERY_REQUIRES_CONFIRMED_TERMINAL')
    if any(old.get(k) for k in ('result_blob', 'return_receipt', 'oracle_written')):
        raise ValueError('RECOVERY_RETURN_EXISTS_PRESERVE_RESULT')
    if type(old.get('attempt_count')) is not int or old['attempt_count'] != 3:
        raise ValueError('RECOVERY_REQUIRES_EXACTLY_THREE_PRIOR_ATTEMPTS')
    if type(old.get('deadline')) not in (int, float) or not math.isfinite(old['deadline']):
        raise ValueError('RECOVERY_DEADLINE_INVALID')
    if time.time() >= old['deadline']:
        raise ValueError('ORIGINAL_DEADLINE_EXHAUSTED')
    for key in ('reserved_sql_calls', 'reserved_http_calls'):
        count = old.get(key, 0)
        if type(count) is not int or not 0 <= count < 1000000:
            raise ValueError('ORIGINAL_USAGE_BUDGET_EXHAUSTED')
    if old.get('operator_attempt_history'):
        raise ValueError('RECOVERY_ONE_TIME_GRANT_ALREADY_USED')
    if not re.fullmatch(r'[0-9a-f]{64}', latest['sha256']):
        raise ValueError('RECOVERY_CHECKPOINT_HASH')
    return old


def path_for(name, latest):
    return 'controls/' + name + '/one-attempt/' + latest['sha256'] + '.json'


def expected_fields(name, latest, identity):
    old = latest['value']
    return {'schema_version': 'explicit-compute-attempt-grant-v1', 'job_name': name,
        'checkpoint_path': latest['path'], 'checkpoint_sha256': latest['sha256'],
        'from_code': old['binding']['service_code'], 'to_code': identity['service_code'],
        'previous_attempt_count': 3, 'authorized_attempt_count': 4,
        'original_deadline': old['deadline'],
        'reserved_sql_calls': old.get('reserved_sql_calls', 0),
        'reserved_http_calls': old.get('reserved_http_calls', 0),
        'authorization': CONFIRMATION}


def read_grant(folder, name, latest, identity):
    import controller as c
    checked(folder, name, latest, identity)
    path = path_for(name, latest)
    if path not in {p.lstrip('/') for p in folder.list_paths_in_partition()}:
        raise ValueError('COMPUTE_ATTEMPT_BUDGET_EXHAUSTED: explicit one-attempt authorization required')
    with folder.get_download_stream(path) as stream:
        raw = c.bounded_read(stream, 8192)
    grant = json.loads(raw)
    expected = expected_fields(name, latest, identity)
    if (set(grant) != set(expected) | {'reason', 'authorized_at'}
            or any(grant.get(k) != v for k, v in expected.items())
            or not isinstance(grant['reason'], str) or not 1 <= len(grant['reason']) <= 300
            or type(grant['authorized_at']) not in (int, float)
            or not 0 < grant['authorized_at'] <= time.time()
            or grant['authorized_at'] >= grant['original_deadline']):
        raise ValueError('RECOVERY_GRANT_CHANGED')
    return {**grant, 'grant_path': path, 'grant_sha256': hashlib.sha256(raw).hexdigest()}


def authorize(folder, name, latest, identity, confirmation, reason):
    if confirmation != CONFIRMATION:
        raise ValueError('EXPLICIT_ONE_ATTEMPT_CONFIRMATION_REQUIRED')
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 300:
        raise ValueError('RECOVERY_REASON_REQUIRED')
    checked(folder, name, latest, identity)
    path = path_for(name, latest)
    if path in {p.lstrip('/') for p in folder.list_paths_in_partition()}:
        return read_grant(folder, name, latest, identity)
    grant = {**expected_fields(name, latest, identity), 'reason': reason.strip(), 'authorized_at': time.time()}
    raw = json.dumps(grant, sort_keys=True, ensure_ascii=False).encode()
    folder.upload_stream(path, io.BytesIO(raw))
    with folder.get_download_stream(path) as stream:
        if stream.read(8193) != raw:
            raise ValueError('RECOVERY_GRANT_READBACK')
    return read_grant(folder, name, latest, identity)


def run(action, confirmation='', reason=''):
    import dataiku
    import controller as c
    from updater import config
    if action not in ('inspect', 'authorize_one_attempt'):
        raise ValueError('ACTION')
    project = dataiku.api_client().get_project('LEGAL_RAG')
    cfg = config(project.get_recipe('LEGAL_02_STRUCTURE_GENOS_R1').get_settings().get_code(), 'structure')
    variables = dataiku.get_custom_variables()
    name = variables.get('LEGAL_RECIPE_JOB_NAME', 'recipes_20261027_r1')
    folder = c.Scope(dataiku.Folder(cfg['structured']))
    latest = c.legacy_state(folder, name)
    if not latest:
        raise ValueError('RECOVERY_SAVED_JOB_NOT_FOUND')
    old = latest['value']
    # Inspection reads only the stored checkpoint and recipe configuration.
    summary = {'job_name': name, 'saved_phase': old.get('phase'), 'attempt_count': old.get('attempt_count', 1),
        'normal_attempt_limit': 3, 'deadline_seconds_remaining': round(old['deadline'] - time.time()),
        'reserved_sql_calls': old.get('reserved_sql_calls', 0), 'reserved_http_calls': old.get('reserved_http_calls', 0),
        'result_saved': bool(old.get('result_blob')), 'saved_code': old['binding'].get('service_code'),
        'target_code': c.EXPECTED, 'checkpoint_sha256': latest['sha256'],
        'additional_attempt_authorized': False, 'compute_started': False}
    if old.get('operator_attempt_history'):
        summary.update(additional_attempt_authorized=True, authorization_consumed=True)
    elif path_for(name, latest) in {p.lstrip('/') for p in folder.list_paths_in_partition()}:
        saved_identity = {**old['binding'], 'service_code': c.EXPECTED}
        grant = read_grant(folder, name, latest, saved_identity)
        summary.update(additional_attempt_authorized=True, authorization_consumed=False,
            grant_path=grant['grant_path'], grant_sha256=grant['grant_sha256'])
    if action == 'authorize_one_attempt':
        if confirmation != CONFIRMATION:
            raise ValueError('EXPLICIT_ONE_ATTEMPT_CONFIRMATION_REQUIRED')
        receipts = c.r.input_receipts(dataiku.Folder(cfg['landing']))
        _, _, wire, identity = c.context(cfg, receipts, variables)
        checked(folder, name, latest, identity)
        c.health(wire)  # Read-only current R10 deployment check, never OPEN/RUN.
        grant = authorize(folder, name, latest, identity, confirmation, reason)
        summary.update(additional_attempt_authorized=True, authorized_attempt_count=4,
            grant_path=grant['grant_path'], grant_sha256=grant['grant_sha256'])
    print('ONE_ATTEMPT_SUMMARY_BEGIN')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('ONE_ATTEMPT_SUMMARY_END')
    return summary
