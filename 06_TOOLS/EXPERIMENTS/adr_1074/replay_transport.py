"""Exact recorded transport responses, with a fail-closed offline boundary.

No identity substitution or request normalization is permitted. A first request
that differs is a prefix diagnostic only, never a completed service replay.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import socket

from common import ROOT, read, sha, canonical_digest


class ReplayBoundary(BaseException):
    def __init__(self, code, **details):
        super().__init__(code)
        self.code, self.details = code, details


def require(value, message):
    if not value:
        raise ReplayBoundary('REPLAY_INTEGRITY_FAILURE', detail=message)


def checked_file(item):
    path = (ROOT / item['path']).resolve()
    require(path.is_relative_to(ROOT.resolve()) and path.is_file()
            and sha(path) == item['sha256'], 'frozen replay source changed')
    return path


class RecordedTransport:
    """One frozen cell's ordered requests and successful response envelopes."""
    def __init__(self, frozen, cell, arm):
        contract = frozen['replay_contract']
        self.inventory_path = checked_file({'path':contract['inventory_path'],
                                           'sha256':contract['inventory_sha256']})
        inventory = read(self.inventory_path)
        require(inventory.get('schema_version') == 'exact-service-replay-inputs-v1'
                and contract.get('allow_prefix_diagnostic') is True,
                'replay inventory contract changed')
        matches = [r for r in inventory['cells'] if r['case_id'] == cell['case_id']
                   and r['arm'] == cell['arm']]
        require(len(matches) == 1, 'replay cell missing or duplicated')
        self.source = matches[0]
        require(bool(self.source.get('calls')), 'replay has no recorded calls')
        numbers = [row['call'] for row in self.source['calls']]
        require(numbers == list(range(1, len(numbers)+1)), 'replay call order changed')
        self.calls, self.visits, self.matches = 0, 0, []
        self.arm, self.out = arm, None
        for item in self.source['calls']:
            checked_file(item['request'])
            checked_file(item['response_receipt'])
            checked_file(item['response'])
        self.outer_request = read(checked_file(self.source['outer_request']))
        self.policy = read(ROOT / frozen['code_root'] / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')
        self.proxy = self.policy
        self.failover_spec = None

    def reply(self, payload):
        self.visits += 1
        if self.calls >= len(self.source['calls']):
            raise ReplayBoundary('REPLAY_RECORDS_EXHAUSTED', matched_responses=self.calls)
        item = self.source['calls'][self.calls]
        expected = read(checked_file(item['request']))
        receipt = {'visit':self.visits, 'recorded_call':item['call'],
                   'expected_sha256':canonical_digest(expected),
                   'actual_sha256':canonical_digest(payload),
                   'exact_match':payload == expected, 'external_model_calls':0}
        self.matches.append(receipt)
        require(self.out is not None, 'replay output was not reserved')
        path = self.out / f'replay-request-{self.visits:03d}.json'
        with path.open('x', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        if payload != expected:
            raise ReplayBoundary('REPLAY_PREFIX_DIAGNOSTIC' if self.calls == 0 else 'REPLAY_REQUEST_DIVERGED',
                                 **receipt, matched_responses=self.calls)
        envelope = read(checked_file(item['response_receipt']))
        body = read(checked_file(item['response']))
        require(envelope.get('status_code') == 200 and envelope.get('body_json') == body
                and envelope.get('stream_complete') is True
                and envelope.get('stream_receipt', {}).get('complete') is True,
                'recorded response is not a completed successful response')
        require(body.get('provider') == 'Parasail'
                and str(body.get('model', '')).startswith('qwen/qwen3.8-27b')
                and len(body.get('choices', [])) == 1
                and body['choices'][0].get('finish_reason') == 'stop',
                'recorded response model/provider/output contract changed')
        self.calls += 1
        return deepcopy(envelope)

    def receipt(self):
        return {'schema_version':'exact-service-replay-receipt-v1', 'arm':self.arm,
                'inventory_path':str(self.inventory_path.relative_to(ROOT)),
                'inventory_sha256':sha(self.inventory_path), 'transport_visits':self.visits,
                'recorded_responses_used':self.calls, 'recorded_responses_available':len(self.source['calls']),
                'external_model_calls':0, 'request_checks':self.matches,
                'request_identity_normalization':False, 'network_allowed':False}


@contextmanager
def offline_network():
    """Block INET sockets; keep asyncio's local Unix socketpair usable."""
    originals = {name:getattr(socket.socket, name) for name in ('connect', 'connect_ex', 'sendto')}
    def guarded(name):
        def call(sock, *args, **kwargs):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                raise ReplayBoundary('REPLAY_NETWORK_FORBIDDEN', operation=name)
            return originals[name](sock, *args, **kwargs)
        return call
    for name in originals:
        setattr(socket.socket, name, guarded(name))
    try:
        yield
    finally:
        for name, original in originals.items():
            setattr(socket.socket, name, original)


@contextmanager
def offline_credential(policy):
    """Avoid even reading .env while constructing the unchanged transport."""
    import os
    key = policy['key_env']
    previous = os.environ.get(key)
    os.environ[key] = 'OFFLINE_REPLAY_NO_NETWORK'
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous
