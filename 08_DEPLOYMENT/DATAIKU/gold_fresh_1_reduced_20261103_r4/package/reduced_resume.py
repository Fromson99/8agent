"""Fork a separate search checkpoint; preserve the locked parent's complete evidence."""
import copy
import time

from gold_io import Stop, digest
from reduced_projection import POLICY


def validate_parent(loader, parent, binding, query):
    parents = loader.read(loader.HERE / 'PARENTS.json')
    if parent.get('binding', {}).get('code') not in {p['code_binding'] for p in parents['parents']}:
        raise Stop('REDUCED_UNREGISTERED_PARENT_CODE')
    prior = parent['binding']
    expected = {k: v for k, v in binding.items() if k not in {'code', 'query_release', 'projection_policy'}}
    actual = {k: v for k, v in prior.items() if k not in {'code', 'query_release'}}
    if actual != expected or prior.get('query_release') != query['projection_policy']['parent_query_release_id']:
        raise Stop('REDUCED_PARENT_BINDING_CHANGED')
    if type(parent.get('deadline')) not in (int, float) or time.time() >= parent['deadline']:
        raise Stop('ORIGINAL_DEADLINE_EXPIRED')
    for section in ('source', 'verify_source', 'query', 'verify_query'):
        if not isinstance(parent.get(section), dict):
            raise Stop('REDUCED_PARENT_STATE_INVALID')
    pending = parent.get('pending')
    if pending is not None:
        if not isinstance(pending, dict) or pending.get('section') not in {'source', 'verify_source', 'query', 'verify_query', 'publication'}:
            raise Stop('REDUCED_PARENT_PENDING_INVALID')
        if pending['section'] == 'source':
            slot = pending.get('slot')
            if slot not in loader.SOURCE_MAP or pending.get('table') != loader.SOURCE_MAP[slot][0] or pending.get('verify_only') is not False:
                raise Stop('REDUCED_SOURCE_PENDING_INVALID')
    return parent


def prepare(loader, directory, parent_directory, binding, query, progress):
    """Both job locks must be held. Parent state is never changed, including pending."""
    parent = validate_parent(loader, loader.read(parent_directory / 'state.json'), binding, query)
    parent_hash = digest(parent)
    path = directory / 'state.json'
    query_path = directory / 'query-reduced.json'
    backup = directory / ('parent-state-' + parent_hash + '.json')
    if path.exists():
        state = loader.read(path)
        if (state.get('binding') != binding or state.get('parent_state_sha256') != parent_hash
                or state.get('parent_directory') != str(parent_directory)):
            raise Stop('REDUCED_RESUME_BINDING_CHANGED')
        if loader.read(backup) != parent or loader.read(query_path) != query:
            raise Stop('REDUCED_SAVED_PLAN_CHANGED')
        return state
    acknowledged = [v.get('rows', 0) for v in parent['query'].values()]
    if any(type(n) is not int or n < 0 for n in acknowledged):
        raise Stop('REDUCED_PARENT_QUERY_COUNT_INVALID')
    already = sum(acknowledged)
    possible_pending = parent.get('pending') or {}
    uncertain = possible_pending.get('rows', 0) if possible_pending.get('section') == 'query' else 0
    if type(uncertain) is not int or uncertain < 0:
        raise Stop('REDUCED_PARENT_PENDING_COUNT_INVALID')
    # A new release would resend all retained rows. Do not choose that route
    # when the confirmed/possibly committed old prefix cancels the row saving.
    if already + uncertain >= query['projection_policy']['excluded_rows']:
        raise Stop('REDUCED_RESTART_NOT_FEWER_ROWS_USE_EXISTING_R3')
    for target, value in ((backup, parent), (query_path, query)):
        if target.exists():
            if loader.read(target) != value:
                raise Stop('REDUCED_FORK_RECORD_CHANGED')
        else:
            loader.atomic(target, value)
    pending = parent.get('pending')
    source_pending = pending if pending and pending['section'] == 'source' else None
    state = {
        'binding': binding, 'status': 'NEW', 'phase': 'REDUCED_FORK',
        'deadline': parent['deadline'], 'source': copy.deepcopy(parent['source']),
        'verify_source': {}, 'query': {}, 'verify_query': {},
        'pending': copy.deepcopy(source_pending), 'parent_directory': str(parent_directory),
        'parent_state_sha256': parent_hash,
        'parent_pending_preserved': pending is not None,
        'parent_search_rows_acknowledged': already,
        'minimum_fewer_search_rows_than_parent_resume': query['projection_policy']['excluded_rows'] - already - uncertain,
        'projection_policy': POLICY,
    }
    loader.atomic(path, state)
    progress.emit('REDUCED_FORK_CREATED', parent_state_sha256=parent_hash,
                  source_checkpoints_reused=True, search_restarts_in_new_release=True,
                  prior_search_rows_retained=state['parent_search_rows_acknowledged'],
                  fewer_remaining_rows_at_least=state['minimum_fewer_search_rows_than_parent_resume'],
                  prior_pending_preserved=state['parent_pending_preserved'], deadline_unchanged=True)
    return state
