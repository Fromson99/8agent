"""Known no-model R1/R2 failures -> R3, preserving append-only history/budgets."""
import time
from managed_job import ManagedJob

PREVIOUS_CODE = '868b23d7b0b4ac0d825a1a38644a582966118caad7796ca8b6e780df9f322dfa'
PREVIOUS_CODES = {'aa73eedbbee5f9f4e842c87e7f0fca2278c2dc56b936390871fbf268efea7c73', 'f88b1426f29bc16a862a1a67c72bff8a0d15b106a84aa2ca3dc9f80f4820c084', '1982ddf7ab401b01ab4a59b37b4006a395adfaead7c7231a4520e2d965c35e5c', '31a3d3dd1b2be7b4618e40153bd08e4df8f12c768e57cb1458e856d985ddf548', '78811f3b4620c91057a995eaf567cf078c886c6090d3ea02061f3bef2ec5901c', '8789724175dbe2177eb52c535a6e6b2279af7a4687d7fb0ec24c28a241e52685', '8be91b1939678d31f7e881417091d6a46b9e706704b316044f5ccb6af2752ee1', PREVIOUS_CODE, '6903032227143a1b94fe0eec8a701592d819a2e08f061ce76453b42df687121c'}


def open_store(folder, name, identity, latest):
    if not latest or latest['value']['binding'] == identity:
        return ManagedJob(folder, name, identity)
    old = latest['value']
    previous_code = old['binding'].get('service_code')
    previous_binding = {**identity, 'service_code': previous_code}
    if previous_code not in PREVIOUS_CODES or old['binding'] != previous_binding:
        raise ValueError('UPGRADE_INPUT_DATABASE_OR_SERVICE_BINDING_CHANGED')
    phase = old.get('phase')
    compute = old.get('compute') or {}
    observed = old.get('last_observed') or {}
    if (phase not in {'FAILED', 'CANCELLED'} or observed.get('state') != phase
            or not compute.get('handle') or observed.get('handle') != compute['handle']
            or compute.get('code_sha256') != previous_code):
        raise ValueError('UPGRADE_REQUIRES_CONFIRMED_TERMINAL')
    if any(old.get(key) for key in ('result_blob', 'return_receipt', 'oracle_written')):
        raise ValueError('UPGRADE_RETURN_EXISTS_PRESERVE_RESULT')
    count = old.get('attempt_count', 1)
    if type(count) is not int or count < 1:
        raise ValueError('COMPUTE_ATTEMPT_BUDGET_EXHAUSTED')
    grant = None
    if count >= 3:
        from one_attempt import read_grant
        grant = read_grant(folder, name, latest, identity)
    if time.time() >= old['deadline']:
        raise ValueError('ORIGINAL_DEADLINE_EXHAUSTED')
    store = ManagedJob(folder, name, previous_binding)
    proof = None
    if previous_code in {'31a3d3dd1b2be7b4618e40153bd08e4df8f12c768e57cb1458e856d985ddf548', '78811f3b4620c91057a995eaf567cf078c886c6090d3ea02061f3bef2ec5901c', '8be91b1939678d31f7e881417091d6a46b9e706704b316044f5ccb6af2752ee1','8789724175dbe2177eb52c535a6e6b2279af7a4687d7fb0ec24c28a241e52685'}:
        from upgrade_review import require_zero_review
        proof = require_zero_review(store,old)
    if previous_code in {'1982ddf7ab401b01ab4a59b37b4006a395adfaead7c7231a4520e2d965c35e5c', 'f88b1426f29bc16a862a1a67c72bff8a0d15b106a84aa2ca3dc9f80f4820c084', 'aa73eedbbee5f9f4e842c87e7f0fca2278c2dc56b936390871fbf268efea7c73'}:
        if old.get('audit_blob'):
            from upgrade_review import require_zero_review
            proof = require_zero_review(store,old)
        else:
            proof = {'basis':'SEALED_R7_R8_R9_FIXED_SKIP_NO_MODEL_PATH', 'code_sha256':previous_code,
                     'audit_available':False, 'field_calls_measured':False}
    # Check the snapshot again before appending. Scenario concurrency remains 1;
    # S3 managed-folder listing is not a distributed CAS lock.
    if store.value != old:
        raise ValueError('UPGRADE_CHECKPOINT_CHANGED')
    keep = {k: v for k, v in old.items() if k in {
        'deadline', 'reserved_sql_calls', 'reserved_http_calls',
        'migration_checked', 'legacy_checkpoint', 'upgrade_history', 'operator_attempt_history'}}
    keep.update(binding=identity, phase='NEW', attempt_count=count + 1,
                previous_handle=compute['handle'])
    keep['upgrade_history'] = list(keep.get('upgrade_history', [])) + [{
        'checkpoint_path': latest['path'], 'checkpoint_sha256': latest['sha256'],
        'from_code_sha256': previous_code, 'to_code_sha256': identity['service_code'],
        'previous_phase': phase, 'previous_handle': compute['handle'],
        'zero_review_proof': proof, 'prior_audit_blob': old.get('audit_blob'), 'reason': ('EXPLICIT_ONE_ADDITIONAL_R10_ATTEMPT' if grant else 'SINGLE_CPU_WORKER_CONFIGURATION'), 'upgraded_at': time.time()}]
    if grant:
        keep['operator_attempt_history'] = list(keep.get('operator_attempt_history', [])) + [grant]
    store.value = keep
    store.save()
    return store
