"""Carry the exact failed R3 preparation deadline forward, never unknown work."""
import copy
from gold_io import Stop, digest


def inherit_preparation(job, directory, loader):
    if job.path.exists():
        return
    parent = loader.read(loader.HERE/'VECTOR_STRUCTURE_PARENT.json')
    previous = copy.deepcopy(job.state['binding'])
    previous['code'] = parent['code_binding']
    previous['manifest']['segment_profile'] = parent['policy']
    old = directory/'vectors-structure-r3'/digest(previous['manifest'])/'state.json'
    if not old.exists():
        return
    state = loader.read(old)
    if state['binding'] != previous:
        raise Stop('VECTOR_R3_PREPARATION_BINDING_CHANGED')
    if (any(state.get(k) for k in ('rows','embedding_calls','next_batch','insert_requests',
                                 'pending_key_queries','pending','embedding_pending','cursor'))
            or state['status'] != 'NEW' or (old.parent/'previous-vector-reset.json').exists()):
        raise Stop('VECTOR_R3_HAS_EXTERNAL_WORK_REVIEW_REQUIRED')
    loader.atomic(job.work/'previous-r3-preparation-state.json', state)
    job.state['deadline'] = state['deadline']
    job.state['max_calls'] = state['max_calls']
    job.state['previous_preparation'] = {'path':str(old), 'sha256':digest(state)}
    job.progress.emit('VECTOR_R3_PREPARATION_INHERITED', model_calls=0,
                      original_deadline=state['deadline'], previous_state=str(old))
