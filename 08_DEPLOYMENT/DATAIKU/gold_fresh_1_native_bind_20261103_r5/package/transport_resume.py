"""Code-only migration under existing locks, preserving every checkpoint field."""
import time


def migrate(loader, path, state, binding, progress):
    if state['binding'] == binding: return state
    mode = 'reduced' if 'projection_policy' in state['binding'] else 'full'
    parents = loader.read(loader.HERE / 'NATIVE_PARENTS.json')['parents']
    allowed = {p['code_binding'] for p in parents if p['mode'] == mode}
    prior = state['binding']
    if (prior.get('code') not in allowed or
            {k: v for k, v in prior.items() if k != 'code'} !=
            {k: v for k, v in binding.items() if k != 'code'}):
        raise loader.Stop('JOB_BINDING_CHANGED_KEEP_PRIOR_STATE')
    if any((path.parent / 'vectors').glob('*/state.json')):
        raise loader.Stop('VECTOR_ALREADY_STARTED_KEEP_PRIOR_CODE')
    backup = path.with_name('state-before-r5-' + loader.digest(state) + '.json')
    if backup.exists():
        if loader.read(backup) != state: raise loader.Stop('R5_BACKUP_CONFLICT')
    else: loader.atomic(backup, state)
    result = dict(state)
    result['binding'] = binding
    result['code_transitions'] = [*state.get('code_transitions', []), {
        'from': prior['code'], 'to': binding['code'], 'at': time.time(),
        'backup': backup.name, 'prior_state_sha256': loader.digest(state),
        'reason': 'R5 native CLOB binds; insert-only path; checkpoints retained; full readback removed by user',
    }]
    loader.atomic(path, result)
    progress.emit('R5_RESUME_BOUND', mode=mode, backup=backup.name,
                  deadline_unchanged=True, legacy_deadline_enforced=False, pending_preserved=bool(state.get('pending')),
                  source_query_release_unchanged=True)
    return result
