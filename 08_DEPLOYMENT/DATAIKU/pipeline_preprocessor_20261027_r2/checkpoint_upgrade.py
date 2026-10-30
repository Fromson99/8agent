"""One explicit R1 failure -> R2 attempt, preserving append-only history/budgets."""
import time
from managed_job import ManagedJob

PREVIOUS_CODE = '868b23d7b0b4ac0d825a1a38644a582966118caad7796ca8b6e780df9f322dfa'


def open_store(folder, name, identity, latest):
    if not latest or latest['value']['binding'] == identity:
        return ManagedJob(folder, name, identity)
    old = latest['value']
    previous_binding = {**identity, 'service_code': PREVIOUS_CODE}
    if old['binding'] != previous_binding:
        raise ValueError('UPGRADE_INPUT_DATABASE_OR_SERVICE_BINDING_CHANGED')
    phase = old.get('phase')
    compute = old.get('compute') or {}
    observed = old.get('last_observed') or {}
    if (phase not in {'FAILED', 'CANCELLED'} or observed.get('state') != phase
            or not compute.get('handle') or observed.get('handle') != compute['handle']
            or compute.get('code_sha256') != PREVIOUS_CODE):
        raise ValueError('UPGRADE_REQUIRES_CONFIRMED_TERMINAL')
    if any(old.get(key) for key in ('result_blob', 'return_receipt', 'oracle_written')):
        raise ValueError('UPGRADE_RETURN_EXISTS_PRESERVE_RESULT')
    count = old.get('attempt_count', 1)
    if type(count) is not int or not 1 <= count < 3:
        raise ValueError('COMPUTE_ATTEMPT_BUDGET_EXHAUSTED')
    if time.time() >= old['deadline']:
        raise ValueError('ORIGINAL_DEADLINE_EXHAUSTED')
    store = ManagedJob(folder, name, previous_binding)
    # Check the snapshot again before appending. Scenario concurrency remains 1;
    # S3 managed-folder listing is not a distributed CAS lock.
    if store.value != old:
        raise ValueError('UPGRADE_CHECKPOINT_CHANGED')
    keep = {k: v for k, v in old.items() if k in {
        'deadline', 'reserved_sql_calls', 'reserved_http_calls',
        'migration_checked', 'legacy_checkpoint', 'upgrade_history'}}
    keep.update(binding=identity, phase='NEW', attempt_count=count + 1,
                previous_handle=compute['handle'])
    keep['upgrade_history'] = list(keep.get('upgrade_history', [])) + [{
        'checkpoint_path': latest['path'], 'checkpoint_sha256': latest['sha256'],
        'from_code_sha256': PREVIOUS_CODE, 'to_code_sha256': identity['service_code'],
        'previous_phase': phase, 'previous_handle': compute['handle'],
        'reason': 'PDF_PREPROCESSOR_RESTORED', 'upgraded_at': time.time()}]
    store.value = keep
    store.save()
    return store
