"""Explicit R1 -> R2 code binding migration; row offsets survive batch tuning."""
from itertools import islice
import os
import time


def limits():
    rows = int(os.environ.get('G19_QUERY_BATCH_ROWS', '10000'))
    size = int(os.environ.get('G19_QUERY_BATCH_BYTES', str(4 * 1024**2)))
    if not 1 <= rows <= 10000 or not 65536 <= size <= 4 * 1024**2:
        raise ValueError('QUERY_BATCH_LIMIT: rows 1..10000; bytes 65536..4194304')
    return rows, size


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
    backup = path.with_name('state-before-r2-' + loader.digest(state) + '.json')
    if backup.exists():
        if loader.read(backup) != state:
            raise loader.Stop('R2_BACKUP_CONFLICT')
    else:
        loader.atomic(backup, state)
    result = dict(state)
    result['binding'] = binding
    result['code_transitions'] = [*state.get('code_transitions', []), {
        'from': prior['code'], 'to': binding['code'], 'at': time.time(),
        'backup': backup.name, 'prior_state_sha256': loader.digest(state),
        'reason': 'R2 offset resume and configurable query batches',
    }]
    loader.atomic(path, result)
    progress.emit('R1_TO_R2_RESUME_BOUND', backup=backup.name,
                  deadline_unchanged=True, pending_preserved=bool(state.get('pending')))
    return result


def remaining(loader, iterator, completed, guard):
    if type(completed) is not int or completed < 0:
        raise loader.Stop('QUERY_CURSOR_INVALID')
    seen = 0
    for row in iterator:
        if seen == completed:
            yield row
            yield from iterator
            return
        seen += 1
        if seen % 1000 == 0:
            guard()
    if seen != completed:
        raise loader.Stop('QUERY_CURSOR_EXCEEDS_INPUT')


def restore_pending(loader, job, iterator, section, relative, completed, release, verify_only):
    pending = job.state.get('pending')
    if not pending:
        return completed
    count = pending.get('rows')
    if (pending.get('table') != 'SRCH_ROW' or pending.get('section') != section or
            pending.get('slot') != relative or pending.get('verify_only') is not verify_only or
            type(count) is not int or not 1 <= count <= 10000 or
            pending.get('next') != {'rows': completed + count}):
        raise loader.Stop('PENDING_BATCH_BINDING_MISMATCH')
    rows = list(islice(iterator, count))
    if len(rows) != count:
        raise loader.Stop('QUERY_PENDING_EXCEEDS_INPUT')
    values = [loader.query_row(release, row) for row in rows]
    # Existing Job.batch compares the exact hash and metadata before issuing SQL.
    # Unknown INSERT outcomes remain verify-only; missing/conflicting rows stop.
    job.batch('SRCH_ROW', values, next_progress={'rows': completed + count},
              section=section, slot=relative, verify_only=verify_only)
    return completed + count
