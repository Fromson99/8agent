"""Literal MAIN104 responses; comparisons never rewrite product input/output."""
from contextlib import contextmanager
from copy import deepcopy
import gzip
import hashlib
import json
import re
import socket

from common import ROOT, read, sha

class ReplayBoundary(BaseException):
    pass

def require(condition, message):
    if not condition:
        raise ReplayBoundary(message)

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def checked(item):
    path = (ROOT / item['path']).resolve()
    require(path.is_relative_to(ROOT) and sha(path) == item['sha256'], 'Frozen input changed')
    return path

def load(item):
    path = checked(item)
    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf8') as stream:
            return json.load(stream)
    return read(path)

def comparable(body):
    result = deepcopy(body)
    messages = result.get('messages', [])
    require(len(messages) == 2 and [m['role'] for m in messages] == ['system', 'user'],
            'Unknown messages layout')
    user = json.loads(messages[1]['content'])
    require(isinstance(user, dict) and isinstance(user.get('view'), dict), 'Unknown user layout')
    view = user['view']
    if re.fullmatch(r'V[0-9a-f]{32}', str(view.get('view_id', ''))):
        view.pop('view_id')
    messages[1]['content'] = user
    return result

def compare_request(expected, actual):
    return {'whole_request_exact': digest(expected) == digest(actual),
            'protected_request_exact': digest(comparable(expected)) == digest(comparable(actual)),
            'expected_protected_sha256': digest(comparable(expected)),
            'actual_protected_sha256': digest(comparable(actual)),
            'schema_exact': expected.get('response_format') == actual.get('response_format'),
            'system_exact': expected['messages'][0] == actual['messages'][0],
            'expected_phase': json.loads(expected['messages'][1]['content'])['view'].get('source_stage'),
            'actual_phase': json.loads(actual['messages'][1]['content'])['view'].get('source_stage')}

def answer_content(body):
    answer = deepcopy(body['answer'])
    require(answer['id'] == 'answer:' + body['run_id'] and answer['query_id'] == body['query']['id'],
            'Answer identity is not bound to native run/query')
    answer.pop('id')
    answer.pop('query_id')
    return answer

class RecordedTransport:
    def __init__(self, inventory):
        self.inventory = inventory
        self.calls = 0
        self.checks = []
        require(len(inventory['calls']) == 38, 'Expected exactly 38 recorded responses')

    def reply(self, body):
        require(self.calls < 38, 'Unexpected extra model request')
        item = self.inventory['calls'][self.calls]
        expected, response = load(item['wire']), load(item['response'])
        receipt = compare_request(expected, body)
        receipt['call'] = self.calls + 1
        self.checks.append(receipt)
        require(receipt['schema_exact'] and receipt['system_exact'] and
                receipt['expected_phase'] == receipt['actual_phase'], 'Replay phase/schema mismatch')
        # All protected fields must match before literal evidence is delivered.
        require(receipt['protected_request_exact'], 'Protected request differs from historical input')
        require(response['model'] == 'qwen/qwen3.8-27b' and response['provider'] == 'Parasail'
                and len(response['choices']) == 1 and response['choices'][0]['finish_reason'] == 'stop',
                'Recorded response is not a complete expected-provider response')
        self.calls += 1
        return {'status_code': 200, 'body_json': response, 'acceptance': 'ACCEPTED'}

@contextmanager
def offline_network():
    originals = {n: getattr(socket.socket, n) for n in ('connect', 'connect_ex', 'sendto')}
    resolver = socket.getaddrinfo
    def denied(*args, **kwargs):
        raise ReplayBoundary('Offline replay forbids network resolution')
    def guard(name):
        def call(sock, *args, **kwargs):
            require(sock.family not in (socket.AF_INET, socket.AF_INET6), 'Offline replay forbids network')
            return originals[name](sock, *args, **kwargs)
        return call
    for name in originals:
        setattr(socket.socket, name, guard(name))
    socket.getaddrinfo = denied
    try:
        yield
    finally:
        for name, value in originals.items():
            setattr(socket.socket, name, value)
        socket.getaddrinfo = resolver
