"""DSS waits for the Agent READY receipt; only the load recipe writes Gold."""
import hashlib
import time

import agent_stage as stage
import transport as t


def context(cfg, paths, folders, variables, trial):
    from flow_runtime import read, validate_intent, layer_query
    intent = read(folders['submit'], trial + '/submitted.json')
    validate_intent(intent, cfg, trial)
    query = layer_query(cfg['AGENT_CONNECTION'])
    return intent, query


def remote_state(intent, paths, variables):
    from flow_runtime import wire
    path = paths / 'request.json'
    if not path.is_file():
        raise ValueError('ORIGINAL_SHARED_WORK_DIR_REQUIRED')
    state = t.read(path)
    if state['intent'] != intent:
        raise ValueError('REQUEST_BINDING_CHANGED')
    if time.time() >= state['deadline']:
        raise ValueError('ORIGINAL_JOB_DEADLINE_EXCEEDED')
    remote = wire(variables)
    if hashlib.sha256(remote.url.encode()).hexdigest() != intent['context']['endpoint']:
        raise ValueError('GENOS_ENDPOINT_CHANGED')
    return remote, state


def receive(cfg, paths, folders, variables, trial):
    from flow_runtime import put
    intent, query = context(cfg, paths, folders, variables, trial)
    remote = state = None
    previous = None
    while True:
        # A durable READY receipt takes precedence over a lost process/HTTP ACK.
        receipt = stage.ready(query, intent['job'], intent['binding'])
        if receipt:
            record = {'intent': intent, 'result': receipt}
            put(folders['wait'], trial + '/ready.json', record)
            return record
        if remote is None:
            remote, state = remote_state(intent, paths, variables)
        if time.time() >= state['deadline']:
            raise ValueError('ORIGINAL_JOB_DEADLINE_EXCEEDED')
        current = remote.call('POLL', **state['auth'])
        if current.get('handle') != intent['job'] or current.get('instance') != state['auth']['instance']:
            raise ValueError('RETURN_HANDLE_CHANGED')
        phase = current['state'], current['phase']
        if phase != previous:
            print(intent['job'], *phase, flush=True)
            previous = phase
        if current['state'] == 'STAGE_PENDING':
            # Deliberately no automatic PUBLISH after an unconfirmed write.
            raise ValueError('AGENT_STAGE_PENDING_EXPLICIT_RESUME_REQUIRED')
        if current['state'] == 'COMPLETE':
            # Query once more: the READY commit can occur between our query/POLL.
            receipt = stage.ready(query, intent['job'], intent['binding'])
            if receipt:
                continue
            raise ValueError('GENOS_COMPLETE_WITHOUT_AGENT_READY')
        if current['state'] != 'RUNNING':
            raise ValueError('COMPUTE_WITHOUT_AGENT_RESULT:' + str(current.get('error') or current['state']))
        time.sleep(5)


def resume(cfg, paths, folders, variables, trial):
    intent, query = context(cfg, paths, folders, variables, trial)
    if not stage.ready(query, intent['job'], intent['binding']):
        remote, state = remote_state(intent, paths, variables)
        current = remote.call('POLL', **state['auth'])
        if current.get('handle') != intent['job'] or current.get('instance') != state['auth']['instance']:
            raise ValueError('RETURN_HANDLE_CHANGED')
        if current['state'] == 'STAGE_PENDING':
            remote.call('PUBLISH', **state['auth'])
        elif current['state'] not in ('RUNNING', 'COMPLETE'):
            raise ValueError('NO_SAVED_RESULT_TO_RESUME')
    return receive(cfg, paths, folders, variables, trial)
