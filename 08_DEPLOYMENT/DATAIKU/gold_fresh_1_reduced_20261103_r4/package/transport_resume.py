"""Exact R1 checkpoint migration. Call only under the existing job.lock."""
import time

def migrate(loader, path, state, binding, progress):
    """Called with the existing job.lock held, after current DB/input checks."""
    if state['binding'] == binding:
        return state
    predecessor = loader.read(loader.HERE / 'PREDECESSOR.json')
    prior = state['binding']
    if (prior.get('code') != predecessor['code_binding'] or
            prior.get('contract') != predecessor['contract_sha256'] or
            {k: v for k, v in prior.items() if k != 'code'} !=
            {k: v for k, v in binding.items() if k != 'code'}):
        raise loader.Stop('JOB_BINDING_CHANGED_KEEP_PRIOR_STATE')
    if any((path.parent / 'vectors').glob('*/state.json')):
        raise loader.Stop('R1_VECTOR_ALREADY_STARTED_KEEP_R1_CODE')
    backup = path.with_name('state-before-r3-' + loader.digest(state) + '.json')
    if backup.exists():
        if loader.read(backup) != state:
            raise loader.Stop('R3_BACKUP_CONFLICT')
    else:
        loader.atomic(backup, state)
    result = dict(state)
    result['binding'] = binding
    result['code_transitions'] = [*state.get('code_transitions', []), {
        'from': prior['code'], 'to': binding['code'], 'at': time.time(),
        'backup': backup.name, 'prior_state_sha256': loader.digest(state),
        'reason': 'R3 lossless gzip/base64 transport and early temporary LOB release',
    }]
    loader.atomic(path, result)
    progress.emit('R1_TO_R3_RESUME_BOUND', backup=backup.name,
                  deadline_unchanged=True, pending_preserved=bool(state.get('pending')))
    return result

