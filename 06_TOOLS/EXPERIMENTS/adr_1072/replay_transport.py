"""Literal recorded responses for a schema- and content-bound reconstruction.

This is not a byte-identical HTTP replay. Schema, phase/order and the unchanged
response's current-schema validity gate response delivery. Other input changes
are retained as independent equivalence failures, not repaired or hidden.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
import re
import socket

from jsonschema import validators
from common import ROOT, read, sha, canonical_digest

VIEW_UUID = re.compile(r'V[0-9a-f]{32}\Z')
EXPECTED_PHASES = ['request-entry'] + [
    f'source-law-navigation-{n}-read-choice' for n in range(1, 9)
] + ['memory-assess', 'memory-compose']
EXEMPT_PATHS = ['/view/view_id', '/step_state/budget_at_decision_start/seconds_remaining']
SOURCE_FIELDS = {'sources', 'exact_evidence', 'evidence_options', 'references'}
ACTION_FIELDS = {'tool_options', 'action_scopes', 'read_candidates', 'article_candidates',
                 'connection_scope_choices', 'available_action_types', 'law_matches',
                 'document_structures'}


class ReplayBoundary(BaseException):
    """A fatal harness mismatch; never interpreted as a successful prefix."""
    def __init__(self, code, **details):
        super().__init__(code)
        self.code, self.details = code, details


def require(value, message):
    if not value:
        raise ReplayBoundary('RECONSTRUCTION_INTEGRITY_FAILURE', detail=message)


def checked_file(item):
    path = (ROOT / item['path']).resolve()
    require(path.is_relative_to(ROOT.resolve()) and path.is_file()
            and sha(path) == item['sha256'], 'frozen reconstruction source changed')
    return path


def user_payload(request):
    messages = request.get('messages')
    require(isinstance(messages, list) and len(messages) == 2
            and [m.get('role') for m in messages] == ['system', 'user'],
            'unknown message layout')
    require(all(isinstance(m.get('content'), str) for m in messages), 'non-text message')
    try:
        value = json.loads(messages[1]['content'])
    except (TypeError, ValueError) as exc:
        raise ReplayBoundary('RECONSTRUCTION_INPUT_JSON_INVALID') from exc
    require(isinstance(value, dict) and isinstance(value.get('view'), dict)
            and isinstance(value.get('step_state'), dict), 'unknown user payload')
    return value


def comparison_payload(value):
    """Return a comparison copy; never alter the actual request or response."""
    result = deepcopy(value)
    ident = result['view'].get('view_id')
    # V1 is a deterministic projection alias, not a generated UUID.
    if isinstance(ident, str) and VIEW_UUID.fullmatch(ident):
        result['view'].pop('view_id')
    budget = result['step_state'].get('budget_at_decision_start')
    require(isinstance(budget, dict), 'missing decision budget')
    seconds = budget.get('seconds_remaining')
    require(type(seconds) is int and 0 <= seconds <= 1800, 'invalid remaining-seconds value')
    budget.pop('seconds_remaining')
    return result


def different_paths(expected, actual, path='', limit=40):
    """Bounded field names only, without copying source text into diagnostics."""
    out = []
    def visit(a, b, loc):
        if len(out) >= limit or canonical_digest(a) == canonical_digest(b):
            return
        if type(a) is dict and type(b) is dict:
            for key in sorted(set(a) | set(b)):
                child = loc + '/' + str(key).replace('~', '~0').replace('/', '~1')
                if key not in a or key not in b:
                    out.append(child)
                else:
                    visit(a[key], b[key], child)
                if len(out) >= limit:
                    break
        elif type(a) is list and type(b) is list and len(a) == len(b):
            for n, (x, y) in enumerate(zip(a, b)):
                visit(x, y, loc + '/' + str(n))
                if len(out) >= limit:
                    break
        else:
            out.append(loc or '/')
    visit(expected, actual, path)
    return out


def validate_exchange(expected, actual, envelope, response, ordinal):
    """Pure transport contract, also used by the synthetic tests."""
    require(type(ordinal) is int and 1 <= ordinal <= len(EXPECTED_PHASES), 'call ordinal out of range')
    expected_user, actual_user = user_payload(expected), user_payload(actual)
    expected_phase = expected_user['view'].get('source_stage')
    actual_phase = actual_user['view'].get('source_stage')
    expected_schema = expected.get('response_format')
    actual_schema = actual.get('response_format')
    require(isinstance(expected_schema, dict) and isinstance(actual_schema, dict), 'missing response schema')
    schema_equal = canonical_digest(expected_schema) == canonical_digest(actual_schema)
    expected_comparison = comparison_payload(expected_user)
    actual_comparison = comparison_payload(actual_user)
    protected_equal = canonical_digest(expected_comparison) == canonical_digest(actual_comparison)
    expected_parameters = {k:v for k,v in expected.items() if k != 'messages'}
    actual_parameters = {k:v for k,v in actual.items() if k != 'messages'}
    parameters_equal = canonical_digest(expected_parameters) == canonical_digest(actual_parameters)
    system_equal = expected['messages'][0] == actual['messages'][0]
    def projected(fields, value):
        return {key:value['view'][key] for key in sorted(fields) if key in value['view']}
    projections = {}
    for label, fields in [('sources', SOURCE_FIELDS), ('actions', ACTION_FIELDS)]:
        before = canonical_digest(projected(fields, expected_user))
        after = canonical_digest(projected(fields, actual_user))
        projections[label] = {'expected_sha256':before, 'actual_sha256':after,
                              'exact':before == after}
    receipt = {'recorded_call':ordinal, 'expected_phase':expected_phase, 'actual_phase':actual_phase,
        'phase_order_match':expected_phase == actual_phase == EXPECTED_PHASES[ordinal-1],
        'expected_request_sha256':canonical_digest(expected),
        'actual_request_sha256':canonical_digest(actual),
        'whole_request_exact':canonical_digest(expected) == canonical_digest(actual),
        'expected_schema_sha256':canonical_digest(expected_schema),
        'actual_schema_sha256':canonical_digest(actual_schema), 'schema_exact':schema_equal,
        'system_prompt_exact':system_equal, 'request_parameters_exact':parameters_equal,
        'protected_user_payload_exact':protected_equal,
        'protected_expected_sha256':canonical_digest(expected_comparison),
        'protected_actual_sha256':canonical_digest(actual_comparison),
        'allowed_comparison_only_paths':list(EXEMPT_PATHS),
        'different_user_paths':different_paths(expected_user, actual_user),
        'protected_different_paths':different_paths(expected_comparison, actual_comparison),
        'projection_checks':projections,
        'projection_exact':all(item['exact'] for item in projections.values()),
        'equivalence_comparable':protected_equal and system_equal and parameters_equal,
        'response_rewritten':False, 'external_model_calls':0}
    for condition, code in [
        (receipt['phase_order_match'], 'PHASE_ORDER_MISMATCH'),
        (schema_equal, 'WIRE_SCHEMA_MISMATCH')]:
        if not condition:
            raise ReplayBoundary(code, check=receipt)
    require(envelope.get('status_code') == 200 and envelope.get('body_json') == response
            and envelope.get('acceptance') == 'ACCEPTED'
            and envelope.get('stream_complete') is True
            and envelope.get('stream_receipt', {}).get('complete') is True,
            'recorded response is not a complete successful response')
    require(response.get('provider') == 'Parasail'
            and str(response.get('model', '')).startswith('qwen/qwen3.8-27b')
            and len(response.get('choices', [])) == 1
            and response['choices'][0].get('finish_reason') == 'stop',
            'recorded response model/provider/output contract changed')
    literal = response['choices'][0].get('message', {}).get('content')
    require(isinstance(literal, str), 'recorded response has no literal content')
    try:
        proposal = json.loads(literal)
        schema = actual_schema['json_schema']['schema']
        validator = validators.validator_for(schema)
        validator.check_schema(schema)
        validator(schema).validate(proposal)
    except Exception as exc:
        raise ReplayBoundary('RECORDED_RESPONSE_CURRENT_SCHEMA_INVALID',
                             error_type=type(exc).__name__, check=receipt) from exc
    receipt.update(response_valid_for_current_wire_schema=True,
                   response_content_sha256=canonical_digest(literal))
    return receipt


class RecordedTransport:
    def __init__(self, frozen, cell, arm):
        contract = frozen['replay_contract']
        require(frozen.get('offline_only') is True and frozen.get('prefix_only') is False
            and frozen.get('scripted_reconstruction') is True
            and frozen.get('external_model_calls_allowed') == 0, 'offline reconstruction contract changed')
        require(contract.get('expected_response_count') == 11
            and contract.get('expected_navigation_views') == 8
            and contract.get('schema_match') == 'exact'
            and contract.get('response_rewrite') is False, 'reconstruction checks not frozen')
        self.inventory_path = checked_file({'path':contract['inventory_path'],
                                           'sha256':contract['inventory_sha256']})
        inventory = read(self.inventory_path)
        require(inventory.get('schema_version') == 'exact-service-replay-inputs-v1', 'unknown input inventory')
        matches = [r for r in inventory['cells'] if r['case_id'] == cell['case_id'] and r['arm'] == cell['arm']]
        require(len(matches) == 1 and matches[0].get('source_completed') is True, 'source cell not complete')
        self.source = matches[0]
        require([r['call'] for r in self.source['calls']] == list(range(1, 12)), 'recorded call inventory changed')
        self.calls, self.visits, self.matches, self.failure = 0, 0, [], None
        self.arm, self.out, self.audit = arm, None, None
        for item in self.source['calls']:
            for key in ('request', 'response_receipt', 'response'):
                checked_file(item[key])
        self.outer_request = read(checked_file(self.source['outer_request']))
        self.policy = read(ROOT / frozen['code_root'] / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')
        self.proxy, self.failover_spec = self.policy, None

    def reply(self, payload):
        self.visits += 1
        require(self.visits == self.calls + 1 and self.calls < 11, 'extra, retried or out-of-order request')
        require(self.out is not None, 'reconstruction output not reserved')
        path = self.out / f'replay-request-{self.visits:03d}.json'
        with path.open('x', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        item = self.source['calls'][self.calls]
        expected = read(checked_file(item['request']))
        envelope = read(checked_file(item['response_receipt']))
        response = read(checked_file(item['response']))
        try:
            receipt = validate_exchange(expected, payload, envelope, response, self.visits)
            if 2 <= self.visits <= 9:
                require(self.audit is not None and self.audit.views == self.visits-1,
                        'navigation frame was not checked before response')
            self.matches.append(receipt)
            self.calls += 1
            # Return the original complete envelope, including historical usage;
            # runner receipts explicitly mark usage as inherited, never new cost.
            return deepcopy(envelope)
        except ReplayBoundary as exc:
            self.failure = {'code':exc.code, 'details':deepcopy(exc.details), 'visit':self.visits}
            if 'check' in exc.details:
                self.matches.append(deepcopy(exc.details['check']))
            raise

    def receipt(self):
        return {'schema_version':'scripted-service-reconstruction-v1', 'arm':self.arm,
            'inventory_path':str(self.inventory_path.relative_to(ROOT)), 'inventory_sha256':sha(self.inventory_path),
            'transport_visits':self.visits, 'recorded_responses_used':self.calls,
            'recorded_responses_available':11, 'external_model_calls':0, 'request_checks':self.matches,
            'failure':deepcopy(self.failure), 'response_rewritten':False, 'network_allowed':False,
            'request_identity_substitution':False, 'comparison_exempt_paths':list(EXEMPT_PATHS),
            'whole_request_exact_for_all_calls':len(self.matches) == 11 and all(r['whole_request_exact'] for r in self.matches),
            'full_wire_replay_verified':False, 'historical_usage_is_new_usage':False,
            'all_recorded_responses_consumed':self.calls == 11, 'prefix_only':False}


@contextmanager
def offline_network():
    originals = {n:getattr(socket.socket, n) for n in ('connect', 'connect_ex', 'sendto')}
    resolver = socket.getaddrinfo
    def forbidden(*args, **kwargs):
        raise ReplayBoundary('RECONSTRUCTION_NETWORK_FORBIDDEN', operation='getaddrinfo')
    def guarded(name):
        def call(sock, *args, **kwargs):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                raise ReplayBoundary('RECONSTRUCTION_NETWORK_FORBIDDEN', operation=name)
            return originals[name](sock, *args, **kwargs)
        return call
    for name in originals:
        setattr(socket.socket, name, guarded(name))
    socket.getaddrinfo = forbidden
    try:
        yield
    finally:
        for name, original in originals.items():
            setattr(socket.socket, name, original)
        socket.getaddrinfo = resolver


@contextmanager
def offline_credential(policy):
    import os
    key = policy['key_env']
    previous = os.environ.get(key)
    os.environ[key] = 'OFFLINE_RECONSTRUCTION_NO_NETWORK'
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous
