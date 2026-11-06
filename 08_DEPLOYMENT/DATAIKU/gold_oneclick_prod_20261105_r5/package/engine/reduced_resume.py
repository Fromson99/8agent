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
        if (state.get('parent_state_sha256') != parent_hash
                or state.get('parent_directory') != str(parent_directory)):
            raise Stop('REDUCED_RESUME_BINDING_CHANGED')
        if loader.read(backup) != parent or loader.read(query_path) != query:
            raise Stop('REDUCED_SAVED_PLAN_CHANGED')
        from transport_resume import migrate
        state = migrate(loader, path, state, binding, progress)
        return state
    raise Stop('R5_EXISTING_REDUCED_CHECKPOINT_REQUIRED')
