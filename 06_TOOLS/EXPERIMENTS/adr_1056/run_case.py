"""One immutable MVP matrix cell through frozen service.py -> /v1/rag/ask.

No cell is retried. Native semantic/budget termination is a completed observation;
provider, transport, integrity, resource and unexpected failures stop the matrix.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys
import time
import traceback

from common import ROOT, ADR, ART, read, save, sha, RESPONSE_RECEPTION, WHITESPACE_LIMIT

MAX_CALLS = 40
MAX_TOOLS = 1024
WALL_SECONDS = 1800
MEMORY_LIMIT = 6 * 1024**3
MIN_AVAILABLE = 4 * 1024**3
STOP = ART / 'matrix-stop.json'
MATRIX = ART / 'matrix'
TRACE = ROOT / '06_TOOLS/EXPERIMENTS/adr_1037/trace.py'
NATIVE_CODES = {'MODEL_PROPOSAL_INVALID', 'BUDGET_EXHAUSTED',
                'DEADLINE_EXCEEDED', 'SOURCE_INVESTIGATION_INCOMPLETE'}


class IntegrityFailure(RuntimeError):
    pass


class ResourceFailure(IntegrityFailure):
    pass


def require(condition, message):
    if not condition:
        raise IntegrityFailure(message)


def rooted(value):
    path = (ROOT / value).resolve()
    require(path.is_relative_to(ROOT.resolve()), 'path outside experiment workspace')
    return path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def durable(path, value, *, exclusive=False):
    """Small local receipts; never replace a completed result or first stop."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    if exclusive:
        with path.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    else:
        temporary = path.with_name(path.name + '.tmp-' + str(os.getpid()))
        with temporary.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def append(path, value):
    with Path(path).open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
        stream.flush(); os.fsync(stream.fileno())


def stop(reason, **details):
    try:
        durable(STOP, {'reason': reason, 'time': time.time(), **details}, exclusive=True)
    except FileExistsError:
        pass


def available_memory():
    return next(int(line.split()[1]) * 1024 for line in
        Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))


@contextmanager
def process_lock(name):
    ART.mkdir(parents=True, exist_ok=True)
    with (ART / name).open('a+') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise IntegrityFailure('another experiment process owns ' + name) from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def cell_directory(cell):
    require(type(cell['ordinal']) is int and cell['ordinal'] > 0, 'invalid ordinal')
    require(cell['arm'] in {'A0', 'A1', 'A2'}, 'invalid arm')
    require(all(c.isalnum() or c in '-_' for c in cell['case_id']), 'unsafe case id')
    return MATRIX / f"{cell['ordinal']:03d}-{cell['case_id']}-{cell['arm']}"


def checked(path, expected):
    require(path.is_file() and sha(path) == expected, 'file hash mismatch: ' + str(path))


def check_source_integrity(frozen):
    checked(rooted(frozen['source_integrity_path']), frozen['source_integrity_sha256'])
    receipt = read(rooted(frozen['source_integrity_path']))
    source = rooted(frozen['data_path']) / 'store.sqlite'
    require(rooted(receipt['store_path']) == source, 'source integrity receipt path differs')
    require(receipt['store_sha256'] == frozen['store_sha256'], 'source integrity digest differs')
    stat = source.stat()
    require(all(getattr(stat, 'st_' + key) == receipt[key] for key in ('size', 'mtime_ns', 'ctime_ns')),
        'source store changed after streamed integrity verification')


def authorization_receipt(frozen, authorization, cell, expected_question, expected_public,
                          query, native_request, manifest, *, public_question, original_grant_sha256):
    """Pure policy check; source publication and question export are separate."""
    question = native_request.get('question', query.get('question'))
    require(question == expected_question and text_sha(question)
        == authorization['case_question_sha256'][cell['case_id']], 'unapproved question bytes')
    corpus = read(rooted(frozen['corpus_path']))
    scope = set(query['scope']['document_version_ids'])
    require(native_request['use_llm'] is True and scope
        and scope <= set(corpus['document_ids']), 'experiment source scope denied')
    require(manifest['generation_id'] == frozen['source_generation_id']
        and manifest['store_sha256'] == frozen['store_sha256']
        and manifest['export_allowed'] is False, 'experiment generation denied')
    require(public_question is expected_public, 'question publicity assertion changed')
    return {'kind': 'USER_AUTHORIZED_MVP_EXPERIMENT',
        'authorization_sha256': frozen['authorization_sha256'],
        'optimization_authorization_sha256': frozen['optimization_authorization_sha256'],
        'corpus_sha256': frozen['corpus_sha256'], 'grant_sha256': original_grant_sha256,
        'policy_sha256': frozen['policy_sha256'], 'source_manifest_sha256': frozen['data_manifest_sha256'],
        'case_id': cell['case_id'], 'question_sha256': text_sha(question),
        'root_question_sha256': text_sha(question),
        'public_question_asserted': expected_public, 'scope_document_ids': sorted(scope)}


def load_frozen():
    """Pure-file checks only: no runtime imports, source DB, credentials or model."""
    freeze_path = ART / 'design-freeze.json'
    frozen = read(freeze_path)
    code = rooted(frozen['code_root'])
    require('grouped-query-r1/revisions/rev-001/snapshot' in code.as_posix(), 'unexpected code revision')
    for relative, expected in frozen['files'].items():
        checked(code / relative, expected)
    for relative, expected in frozen['runner_hashes'].items():
        checked(rooted(relative), expected)
    for runner in (Path(__file__), Path(__file__).with_name('run_matrix.py'), TRACE):
        require(str(runner.relative_to(ROOT)) in frozen['runner_hashes'], 'runner is not frozen')
    client_path = code / '02_BACKEND/lawrag/research/experiment_client.py'
    require(rooted(frozen['client_path']) == client_path, 'product client is not the frozen candidate')
    checked(client_path, frozen['client_sha256'])
    require(frozen['files']['02_BACKEND/lawrag/research/experiment_client.py'] == frozen['client_sha256'],
        'product client is outside the frozen file map')
    require(frozen['response_reception']['product'] == RESPONSE_RECEPTION
        and frozen['response_reception']['whitespace_limit'] == WHITESPACE_LIMIT
        and frozen['response_reception']['judge'] == 'unchanged-nonstreaming'
        and frozen['response_reception']['partial_publication'] is False,
        'response reception contract drift')
    checked(rooted(frozen['judge_client_path']), frozen['judge_client_sha256'])
    for relative, expected in frozen['semantic_contract_files'].items():
        require(frozen['files'].get(relative) == expected, 'semantic contract changed: ' + relative)
        checked(code / relative, expected)
    checked(ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json', frozen['baseline_policy_sha256'])
    checked(code / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json', frozen['policy_sha256'])
    policy = read(code / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')
    require(policy['max_output_tokens'] is None and policy['http_retries'] == 0
        and policy['fallback_allowed'] is False, 'experiment policy drift')
    checked(rooted(frozen['provider_authorization_path']), frozen['provider_authorization_sha256'])
    require(frozen['runner_hashes'].get(frozen['provider_authorization_path']) == frozen['provider_authorization_sha256'], 'provider authorization not pinned')
    require(policy.get('provider_failover', {}).get('scope') == frozen['experiment_id'], 'provider failover scope drift')
    for key in ('product_cases', 'corpus', 'authorization', 'evaluator_cases', 'evaluation_contract',
                'optimization_authorization'):
        checked(rooted(frozen[key + '_path']), frozen[key + '_sha256'])
    require(frozen['runner_hashes'].get(frozen['optimization_authorization_path'])
        == frozen['optimization_authorization_sha256'], 'optimization authorization is not pinned')
    checked(rooted(frozen['data_path']) / 'manifest.json', frozen['data_manifest_sha256'])
    check_source_integrity(frozen)
    checked(rooted(frozen['snapshot_path']), frozen['snapshot_file_sha256'])
    snapshot = read(rooted(frozen['snapshot_path']))
    require(digest(snapshot) == frozen['snapshot_digest'], 'ontology snapshot digest mismatch')
    product = read(rooted(frozen['product_cases_path']))
    require(set(product) == {'schema_version', 'cases'}, 'product case envelope contains extra data')
    cases = product['cases']
    require(len(cases) == 37 and all(set(c) == {'case_id', 'question'} for c in cases),
        'product cases must contain only 37 IDs/questions')
    by_id = {c['case_id']: c for c in cases}
    require(len(by_id) == 37, 'duplicate product case')
    authorization = read(rooted(frozen['authorization_path']))
    require(authorization['kind'] == 'USER_AUTHORIZED_MVP_EXPERIMENT'
        and authorization['authorized_by'] == 'user' and authorization['approved_for_run'] is True,
        'experiment authorization missing')
    require(authorization['case_question_sha256'] == {k: text_sha(v['question']) for k, v in by_id.items()},
        'authorized question bytes differ')
    receipts = authorization['export_receipts']
    require({r['path'] for r in receipts} >= {
        '01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json',
        '01_DATA/GOLDEN/risk_cm/EXPORT_AUTHORIZATION_20261024.json'}, 'question export receipts missing')
    for receipt in receipts:
        checked(rooted(receipt['path']), receipt['sha256'])
    corpus = read(rooted(frozen['corpus_path']))
    ids = corpus['document_ids']
    require(isinstance(ids, list) and len(ids) == len(set(ids)) == 1536
        and all(isinstance(x, str) for x in ids), 'common public corpus changed')
    require(corpus['approved_for_run'] is True and corpus['all_arms_same_scope'] is True
        and corpus['generation_id'] == frozen['source_generation_id']
        and corpus['store_sha256'] == frozen['store_sha256']
        and corpus['manifest_sha256'] == frozen['data_manifest_sha256']
        and corpus['generation_manifest_export_allowed'] is False
        and corpus['authorization_receipt']['sha256'] == frozen['authorization_sha256'], 'corpus authorization drift')
    manifest = read(rooted(frozen['data_path']) / 'manifest.json')
    require(manifest['generation_id'] == frozen['source_generation_id']
        and manifest['store_sha256'] == frozen['store_sha256']
        and manifest['export_allowed'] is False, 'source generation binding changed')
    order = frozen['execution_order']
    require(len(order) == 3 and [x['ordinal'] for x in order] == [1,2,3], 'probe order invalid')
    require({(x['case_id'], x['arm']) for x in order} == {(cid, 'A0') for cid in ('fsc-hard-005','cm-023','fsc-hard-008')},
        'probe must contain each frozen case exactly once in A0')
    for cell in order:
        cell_directory(cell)
    return frozen, code, by_id, corpus, authorization, snapshot


def request_for(frozen, cell, question, document_ids):
    ident = f"adr1056-{cell['ordinal']:03d}-{cell['case_id']}-{cell['arm']}"
    public = cell['case_id'].startswith('fsc-hard-') or cell['case_id'] == 'ADR-1037'
    body = {'question': question, 'use_llm': True, 'document_ids': list(document_ids)}
    if public:
        body['public_question'] = True
    # Transport correlation only; adding session_id would select another API path.
    return {'API_TYPE': 'RAG_ASK', 'request_id': ident, 'json': body}, public


def native_failure(diagnostic):
    # A handled input limit publishes exact originals or a deterministic rendering
    # through the native finalization path. An escaping typed limit (e.g. after
    # partial streaming) is not a successful/bounded-complete observation.
    if diagnostic.get('error_code') == 'MODEL_INPUT_BUDGET_EXHAUSTED':
        return False
    if diagnostic.get('error_code') not in NATIVE_CODES:
        return False
    if diagnostic['error_code'] not in {'BUDGET_EXHAUSTED', 'DEADLINE_EXCEEDED'} and (
            diagnostic.get('output_contract') or {}).get('category') in {
                'STATE_OR_BINDING_INVALID', 'IMPLEMENTATION_FAILURE'}:
        return False
    tool = diagnostic.get('tool_outcome') or {}
    return tool.get('failure_kind') not in {'AUTH', 'INTEGRITY', 'STATE', 'UNKNOWN', 'INTERNAL'}


def usage_fields(envelope):
    raw = (envelope or {}).get('body_json') or {}
    usage = raw.get('usage') or {}
    return {'provider': raw.get('provider'), 'model': raw.get('model'), 'raw_usage': raw.get('usage'),
        'input_tokens': usage.get('prompt_tokens'), 'output_tokens': usage.get('completion_tokens'),
        'reasoning_tokens': (usage.get('completion_tokens_details') or {}).get('reasoning_tokens'),
        'total_tokens': usage.get('total_tokens'), 'cost_usd': usage.get('cost')}


def reception_failure(exc):
    """Keep a failed physical response out of JSON/schema repair and success.

    No partial model text is inferred to be accepted. Binding errors remain
    integrity failures; all other uncompleted streams retain unknown acceptance.
    """
    code = getattr(exc, 'error_code', None) or getattr(exc, 'code', None) or 'STREAM_FAILURE'
    envelope = getattr(exc, 'response', None)
    receipt = (envelope or {}).get('stream_receipt') or {}
    integrity_codes = {'MODEL_BINDING_MISMATCH', 'PROVIDER_BINDING_MISMATCH', 'REASONING_NOT_DISABLED'}
    return {'failure_code':code, 'stream_receipt':deepcopy(receipt),
        'stop_reason':'OUTPUT_WHITESPACE_STALL' if code == 'OUTPUT_WHITESPACE_STALL' else 'STREAM_FAILURE',
        'product_error':'OUTPUT_RECEPTION' if code == 'OUTPUT_WHITESPACE_STALL' else
            'INTEGRITY' if code in integrity_codes else 'TRANSPORT',
        'acceptance':'UNKNOWN', 'usage':usage_fields(envelope)}


def authorized_transport(base_class, frozen, corpus, authorization, cell, expected_question, expected_public, *, audit_path=None):
    """Expose the exact same source grant for public and export-authorized questions."""
    from semantic_runtime.legal_agent.errors import ContractError
    class Authorized(base_class):
        @property
        def public_scope(self):
            # A private, export-authorized question never asserts publicity.
            # authorize below enforces the same frozen public source ACL.
            return tuple(corpus['document_ids']) if expected_public else None

        def authorize(self, query, native_request, manifest, *, public_question=False):
            try:
                checked(self.grant_path, frozen['files']['00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'])
                checked(self.policy_path, frozen['policy_sha256'])
                checked(rooted(frozen['corpus_path']), frozen['corpus_sha256'])
                checked(rooted(frozen['authorization_path']), frozen['authorization_sha256'])
                checked(rooted(frozen['optimization_authorization_path']), frozen['optimization_authorization_sha256'])
                checked(rooted(frozen['data_path']) / 'manifest.json', frozen['data_manifest_sha256'])
                check_source_integrity(frozen)
                for receipt in authorization['export_receipts']:
                    checked(rooted(receipt['path']), receipt['sha256'])
                return authorization_receipt(frozen, authorization, cell, expected_question,
                    expected_public, query, native_request, manifest,
                    public_question=public_question, original_grant_sha256=self.grant_hash)
            except Exception as exc:
                stop('AUTHORIZATION_INTEGRITY_FAILURE', cell=cell, error_type=type(exc).__name__)
                raise ContractError(str(exc)) from exc

        def validate_authorization(self, context):
            try:
                identity = {'run_id': context.run_id, 'binding_sha256': digest(context.binding),
                    'query_id': context.query.get('id'), 'scope': deepcopy(context.query['scope'])}
                previous = getattr(self, '_mvp_native_identity', None)
                if previous is None:
                    require(context.request.get('question') == expected_question,
                        'first native context is not the approved root question')
                else:
                    require(identity == previous, 'native run, binding or scope changed')
                    require(context.deadline <= self._mvp_initial_deadline,
                        'native request deadline was extended')
                require(context.request.get('use_llm') is True, 'native model request changed')
                # UnifiedRag preserves this native run/binding while replacing
                # only its effective investigation question. Revalidate the
                # original user grant, never re-label the derived text as gold
                # or as another externally approved user question.
                expected = self.authorize(context.query, {**context.request, 'question': expected_question}, {
                    'generation_id': context.binding['generation_id'],
                    'store_sha256': context.binding['store_sha256'],
                    'export_allowed': context.binding['export_allowed']}, public_question=expected_public)
                require(context.binding.get('external_authorization') == expected
                    and context.binding['model'] == self.binding, 'native authorization receipt changed')
                if previous is None:
                    self._mvp_native_identity = identity
                    self._mvp_initial_deadline = context.deadline
                if audit_path is not None:
                    append(audit_path, {'run_id': context.run_id,
                        'root_question_sha256': text_sha(expected_question),
                        'current_question_sha256': text_sha(context.request['question']),
                        'derived_question': context.request['question'] != expected_question,
                        'binding_sha256': identity['binding_sha256'],
                        'scope_document_ids_sha256': digest(expected['scope_document_ids']),
                        'scope_document_ids_count': len(expected['scope_document_ids']),
                        'authorization_sha256': frozen['authorization_sha256']})
            except Exception as exc:
                stop('AUTHORIZATION_INTEGRITY_FAILURE', cell=cell, error_type=type(exc).__name__)
                raise ContractError(str(exc)) from exc

        def authorize_fresh_session_export(self, context, body, principal):
            # The runtime separately proves that its whole case store is fresh.
            # This host hook can grant only this exact approved question/scope.
            self.validate_authorization(context)
            receipt = context.binding.get('external_authorization') or {}
            if (expected_public or body.get('public_question') is True or
                    body.get('question') != expected_question or
                    set(principal['document_ids']) != set(receipt.get('scope_document_ids', []))):
                raise ContractError('fresh private session differs from approved experiment request')
            return deepcopy(receipt)

    return Authorized


def run(cell, loaded):
    frozen, code, cases, corpus, authorization, snapshot = loaded
    require(not STOP.exists(), 'matrix has a sticky stop')
    require(available_memory() >= MIN_AVAILABLE, 'available RAM is below 4 GiB')
    out = cell_directory(cell)
    # Exclusive cell creation is the irreversible execution reservation. An
    # incomplete reservation needs explicit review; never recreate its budget.
    out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    request, public_question = request_for(frozen, cell, cases[cell['case_id']]['question'], corpus['document_ids'])
    durable(out / 'request.json', request, exclusive=True)
    durable(out / 'reservation.json', {'cell': cell, 'request_id': request['request_id'],
        'design_freeze_sha256': sha(ART / 'design-freeze.json'), 'reserved_at': time.time(),
        'deadline_seconds': WALL_SECONDS, 'max_calls': MAX_CALLS, 'max_tools': MAX_TOOLS,
        'reuse_policy': 'NEVER_RERUN_EXISTING_CELL'}, exclusive=True)
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
    os.environ.update(GENOS_RUNTIME_DIR=str(out / 'runtime'), AD_WORKER_ENABLED='0',
        GENOS_AUTO_WARMUP='0', GENOS_RESIDENT_DATA='off', MALLOC_ARENA_MAX='1',
        LAWRAG_WORKSPACE_ROOT=str(ROOT), TOOL_WORKSPACE_ROOT=str(ROOT))
    for key in ('TEAM_ID', 'AD_WORKSPACE', 'DP', 'GENOS_SHARED_LOG_DIR',
                'GENOS_STATE_DIR', 'GENOS_GENERATION', 'GENOS_DATA_ROOT', 'GENOS_MEMORY_JOURNAL_MODE'):
        os.environ.pop(key, None)
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(code / '02_BACKEND'), str(ROOT / '02_BACKEND')]
    result = {'cell': cell, 'request_id': request['request_id'], 'completed': False,
        'code_root': str(code.relative_to(ROOT)), 'known_in_sample': True,
        'model_calls': 0, 'usage': [], 'error': None}
    app = client = None
    observations = []
    events = []
    try:
        import lawrag
        lawrag.__path__.append(str(ROOT / '02_BACKEND/lawrag'))
        from lawrag.research.experiment_client import (ExperimentClient, ExperimentProviderError,
            ExperimentFormatError, ExperimentTransportError, ExperimentStreamError)
        from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
        from semantic_runtime.legal_agent.errors import TransportError, ProposalError, BudgetExhausted, ContractError
        from semantic_runtime.legal_agent.workflow_tiers_policy import profile as normalize_profile
        from semantic_runtime.legal_agent.investigation_diagnostics import exception_diagnostics
        import semantic_runtime.app as app_module

        product_client = Path(importlib.util.find_spec('lawrag.research.experiment_client').origin).resolve()
        require(product_client == rooted(frozen['client_path']), 'product imported an unfrozen model client')
        checked(product_client, frozen['client_sha256'])
        client = ExperimentClient(ROOT, out / 'model', max_calls=MAX_CALLS, policy_root=code,
            response_reception=RESPONSE_RECEPTION)
        original_error = app_module.legal_error_payload
        def observe_error(exc, *args, **kwargs):
            diagnostic = exception_diagnostics(exc)
            observations.append(diagnostic)
            append(out / 'native-failures.jsonl', diagnostic)
            return original_error(exc, *args, **kwargs)
        app_module.legal_error_payload = observe_error

        from lawrag.research.provider_failover import ProviderFailover
        routing = ProviderFailover(client.policy, digest({'cell':cell,'freeze':sha(ART/'design-freeze.json')}))
        durable(out/'provider-routing-state.json', routing.snapshot(), exclusive=True)

        class Audited(authorized_transport(LocalGemmaTransport, frozen, corpus, authorization, cell,
                cases[cell['case_id']]['question'], public_question,
                audit_path=out / 'authorization-trace.jsonl')):
            def preview_request(self, body):
                payload = super().preview_request(body)
                payload['provider'] = deepcopy(client.proxy['provider_routing'])
                return payload

            def send_once(self, *, body, ticket):
                if STOP.exists():
                    raise TransportError('experiment has a sticky stop', retryable=False, unknown=False)
                if client.calls >= MAX_CALLS:
                    raise BudgetExhausted('physical call budget exhausted')
                if time.monotonic() - start >= WALL_SECONDS:
                    raise BudgetExhausted('case wall budget exhausted')
                if available_memory() < MIN_AVAILABLE:
                    stop('RESOURCE_FAILURE', cell=cell, cause='SYSTEM_AVAILABLE_MEMORY_LIMIT')
                    raise ResourceFailure('available RAM is below 4 GiB before call')
                payload = self.preview_request(body)
                require(payload.get('stream') is True
                    and payload.get('stream_options', {}).get('include_usage') is True,
                    'product preview omitted buffered stream/usage request')
                require(not {'max_tokens', 'max_completion_tokens', 'max_output_tokens'} & set(payload),
                    'uncapped experiment constructed an output cap')
                view = json.loads(next(x['content'] for x in body['messages'] if x['role'] == 'user')).get('view', {})
                event = {'call': client.calls + 1, 'phase': view.get('source_stage', view.get('phase')),
                    'started_at': time.time(), 'status': 'STARTED', 'acceptance': 'UNKNOWN',
                    'requested_provider_tag':routing.selected[0], 'requested_provider_name':routing.selected[1],
                    'usage': usage_fields(None)}
                append(out / 'physical-calls.jsonl', {**event, 'event': 'START'})
                durable(out / 'call-state.json', {'reserved_calls': event['call'], 'max_calls': MAX_CALLS,
                    'remaining_calls': MAX_CALLS - event['call'], 'last_call': event, 'replay_allowed': False})
                begin = time.monotonic()
                print('CALL_START', event['call'], event['phase'], flush=True)
                envelope = None
                try:
                    envelope = client.chat_completions(payload, phase='service',
                        timeout_seconds=min(ticket['remaining_seconds'], max(.001, WALL_SECONDS - (time.monotonic() - start))))
                    event.update(status='RETURNED', acceptance='ACCEPTED')
                    return envelope
                except ExperimentTransportError as exc:
                    envelope = getattr(exc, 'response', None)
                    stream = (envelope or {}).get('stream_receipt')
                    failure_kind = 'STREAM_FAILURE' if stream else 'TRANSPORT_FAILURE'
                    event.update(status=failure_kind, acceptance='UNKNOWN' if exc.unknown else 'NOT_ACCEPTED')
                    if envelope and envelope.get('stream_receipt'):
                        event['stream_receipt'] = deepcopy(envelope['stream_receipt'])
                        event['failure_code'] = stream.get('client_stop_reason') or 'STREAM_NETWORK_ERROR'
                    stop(failure_kind, cell=cell, calls=client.calls, acceptance=event['acceptance'],
                        failure_code=event.get('failure_code'), stream_receipt=stream)
                    raise TransportError(str(exc), retryable=False, unknown=exc.unknown, response=envelope) from exc
                except ExperimentProviderError as exc:
                    envelope = exc.response
                    transition = routing.advance(envelope, physical_calls=client.calls,
                        max_calls=MAX_CALLS, remaining_seconds=min(ticket['remaining_seconds'],
                        WALL_SECONDS-(time.monotonic()-start)))
                    known = (envelope or {}).get('acceptance') == 'KNOWN_REJECTED'
                    event.update(status='PROVIDER_FAILURE', acceptance='KNOWN_REJECTED' if known else 'UNKNOWN',
                        provider_transition=transition)
                    if transition is not None:
                        durable(out/'provider-routing-state.json', routing.snapshot())
                        client.select_failover_provider(routing.selected[0])
                        append(out/'provider-transitions.jsonl', transition)
                        raise TransportError(str(exc), retryable=True, unknown=False, response=envelope) from exc
                    stop('PROVIDER_FAILURE', cell=cell, calls=client.calls,
                        status_code=(envelope or {}).get('status_code'), provider_tag=routing.selected[0])
                    raise TransportError(str(exc), retryable=False, unknown=not known, response=envelope) from exc
                except ExperimentStreamError as exc:
                    envelope = exc.response
                    failure = reception_failure(exc)
                    event.update(status=failure['stop_reason'], acceptance=failure['acceptance'],
                        failure_code=failure['failure_code'], stream_receipt=failure['stream_receipt'])
                    stop(failure['stop_reason'], cell=cell, calls=client.calls,
                        failure_code=failure['failure_code'], stream_receipt=failure['stream_receipt'])
                    if failure['product_error'] == 'OUTPUT_RECEPTION':
                        from semantic_runtime.legal_agent.output_contract import OutputReceptionError
                        raise OutputReceptionError(failure['failure_code'], response=envelope) from exc
                    if failure['product_error'] == 'INTEGRITY':
                        error = ContractError('Buffered response binding failed: ' + failure['failure_code'])
                        error.response = envelope
                        raise error from exc
                    raise TransportError('Buffered response failed: ' + failure['failure_code'],
                        retryable=False, unknown=True, response=envelope) from exc
                except ExperimentFormatError as exc:
                    envelope = exc.response
                    event.update(status='FORMAT_FAILURE', acceptance='ACCEPTED')
                    raw = (exc.response or {}).get('body_json', {})
                    if (raw.get('choices') or [{}])[0].get('finish_reason') in ('length', 'content_filter', 'refusal'):
                        from semantic_runtime.legal_agent.model_contract import structured_content
                        from semantic_runtime.legal_agent.output_contract import OutputContractError
                        try:
                            structured_content(raw, allow_length_repair=False)
                        except OutputContractError as error:
                            error.response = exc.response
                            raise error from exc
                    error = ProposalError(str(exc)); error.response = exc.response
                    raise error from exc
                finally:
                    if envelope and envelope.get('stream_receipt'):
                        event['stream_receipt'] = deepcopy(envelope['stream_receipt'])
                    event.update(seconds=time.monotonic() - begin, usage=usage_fields(envelope))
                    events.append(event)
                    append(out / 'physical-calls.jsonl', {**event, 'event': 'END'})
                    durable(out / 'call-state.json', {'reserved_calls': event['call'], 'physical_calls': client.calls,
                        'max_calls': MAX_CALLS, 'remaining_calls': MAX_CALLS - event['call'],
                        'last_call': event, 'replay_allowed': False})
                    print('CALL_END', event['call'], event['status'], round(event['seconds'], 3), flush=True)

        trace_spec = importlib.util.spec_from_file_location('adr1049_scope_trace', TRACE)
        trace = importlib.util.module_from_spec(trace_spec); trace_spec.loader.exec_module(trace)
        trace.install(out)
        transport = Audited(code, ROOT, response_reception=RESPONSE_RECEPTION)
        base = read(code / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
        require(base['max_model_attempts'] == MAX_CALLS and base['max_tool_actions'] == MAX_TOOLS
            and base['wall_seconds'] == WALL_SECONDS and base['max_output_tokens'] is None, 'base profile budgets changed')
        config = {'mode': cell['arm']}
        if cell['arm'] != 'A0':
            config.update(snapshot=deepcopy(snapshot), snapshot_sha256=frozen['snapshot_digest'])
        profile = normalize_profile({**base, 'model_binding': transport.binding,
            'max_transport_retries': 4, 'candidate_navigation': {**base['candidate_navigation'],
                'ontology_context': config}}, require_model=True)
        durable(out / 'effective-profile.json', profile, exclusive=True)
        app = app_module.create_app(ROOT, rooted(frozen['data_path']), contracts_root=code,
            workspace_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
            runtime_root=out / 'runtime', legal_agent_profile=profile, legal_agent_transport=transport,
            release={'mode': 'local-experiment', 'release_id': 'ontology-mvp-adr1056-r10'})
        spec = importlib.util.spec_from_file_location('adr1049_qualification_service', code / 'service.py')
        service = importlib.util.module_from_spec(spec); spec.loader.exec_module(service)
        service._APP = app; service._BINDING = {'mode': 'local-experiment', 'code_root': str(code)}
        modules = {name: importlib.util.find_spec(name).origin for name in (
            'semantic_runtime.app', 'semantic_runtime.legal_agent.request_entry',
            'semantic_runtime.legal_agent.law_navigation', 'semantic_runtime.legal_agent.ontology_context',
            'lawrag.research.experiment_client', 'semantic_runtime.legal_agent.buffered_json_stream')}
        require(all(Path(path).is_relative_to(code) for path in modules.values()), 'runtime imported outside frozen candidate')
        from semantic_runtime.legal_agent.shortcut_store import selected_store
        from semantic_runtime.state_sqlite import journal_policy
        state_path = selected_store(out / 'runtime')
        require(state_path.is_relative_to(out.resolve()), 'case state escaped isolated runtime')
        durable(out / 'execution-binding.json', {'code_root': str(code), 'imports': modules,
            'data_path': frozen['data_path'], 'data_manifest_sha256': frozen['data_manifest_sha256'],
            'authorization_sha256': frozen['authorization_sha256'], 'corpus_sha256': frozen['corpus_sha256'],
            'source_document_count': len(corpus['document_ids']), 'request_sha256': sha(out / 'request.json'),
            'profile_sha256': digest(profile), 'snapshot_digest': frozen['snapshot_digest'] if cell['arm'] != 'A0' else None,
            'public_question_asserted': public_question,
            'authorization_mode': 'USER_AUTHORIZED_MVP_EXPERIMENT',
            'private_question_gate': 'Omitted publicity assertion; exact approved question and unchanged public source ACL enforced by experiment transport.',
            'runtime_root': str(out / 'runtime'), 'inherited_state_paths_removed': True,
            'selected_case_store': str(state_path), 'case_store_inside_cell': True,
            'memory_journal_mode': journal_policy(state_path), 'memory_journal_override': None,
            'http_retries': 0, 'transport_retries': 4, 'output_token_cap': None,
            'provider_failover':client.failover_spec, 'provider_retry_owner':'gateway',
            'response_reception':RESPONSE_RECEPTION, 'whitespace_limit':WHITESPACE_LIMIT,
            'product_client_path':frozen['client_path'], 'product_client_sha256':frozen['client_sha256'],
            'unverified_partial_tokens_public':False,
            'entrypoint': 'frozen service.service -> POST /v1/rag/ask'}, exclusive=True)
        response = asyncio.run(service.service({}, request))
        durable(out / 'response.json', response, exclusive=True)
        result['service_status'] = response.get('status')
        result['native_failures'] = observations
        if STOP.exists():
            result['outcome'] = 'FATAL_STOP'
        elif observations and all(native_failure(d) for d in observations):
            result.update(outcome='NATIVE_BOUNDED_FAILURE', completed=True)
        elif observations or response.get('status') != 200:
            stop('UNEXPECTED_OR_INTEGRITY_FAILURE', cell=cell, service_status=response.get('status'),
                 error_codes=[d.get('error_code') for d in observations])
            result['outcome'] = 'FATAL_STOP'
        else:
            result.update(outcome='SERVICE_COMPLETED', completed=True)
    except BaseException as exc:
        result.update(outcome='FATAL_STOP', error={'type': type(exc).__name__,
            'message': str(exc), 'traceback': traceback.format_exc()})
        stop('RESOURCE_FAILURE' if isinstance(exc, (MemoryError, ResourceFailure)) else 'RUNNER_OR_INTEGRITY_FAILURE',
             cell=cell, error_type=type(exc).__name__)
    finally:
        result.update(seconds=time.monotonic() - start, model_calls=client.calls if client else 0,
            usage=[{'call': event['call'], **event['usage']} for event in events],
            usage_complete=bool(client is not None and len(events) == client.calls
                and all(e['usage']['raw_usage'] is not None for e in events)),
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            remaining_call_budget=MAX_CALLS - (client.calls if client else 0), replay_allowed=False)
        if app is not None:
            try:
                app.state.pipeline.store.close()
            except Exception as exc:
                result.update(completed=False, outcome='FATAL_STOP', close_error=type(exc).__name__)
                stop('STORE_CLOSE_FAILURE', cell=cell)
        durable(out / 'result.json', result, exclusive=True)
    print(json.dumps({k: result[k] for k in ('cell', 'outcome', 'completed', 'model_calls', 'seconds')}, ensure_ascii=False), flush=True)
    return 0 if result['completed'] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ordinal', type=int, required=True)
    parser.add_argument('--inspect-only', '--dry-run', action='store_true')
    args = parser.parse_args()
    loaded = load_frozen()
    matches = [cell for cell in loaded[0]['execution_order'] if cell['ordinal'] == args.ordinal]
    require(len(matches) == 1, 'unknown cell ordinal')
    cell = matches[0]
    if args.inspect_only:
        print(json.dumps({'cell': cell, 'out': str(cell_directory(cell)), 'frozen_inputs_verified': True,
            'live_model_calls': 0, 'runtime_loaded': False}, ensure_ascii=False))
        return 0
    with process_lock('.matrix-case.lock'):
        for earlier in loaded[0]['execution_order'][:args.ordinal - 1]:
            path = cell_directory(earlier) / 'result.json'
            require(path.is_file() and read(path).get('completed') is True, 'previous cell incomplete; no automatic replay')
        return run(cell, loaded)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except IntegrityFailure as exc:
        # Inspection is read-only, including on failure.
        if '--inspect-only' not in sys.argv and '--dry-run' not in sys.argv:
            stop('RUNNER_OR_INTEGRITY_FAILURE', error=str(exc))
        print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        raise SystemExit(2)
