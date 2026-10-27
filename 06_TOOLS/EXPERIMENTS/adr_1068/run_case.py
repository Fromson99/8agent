"""One offline startup prefix through frozen service.py -> /v1/rag/ask.

Only B0/B1, original ordinal1/A0, one reservation each. No model client or
recorded response is invoked; every first request stops at the offline boundary.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager, ExitStack
from copy import deepcopy
import fcntl
from functools import wraps
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import sys
import time
import traceback

from common import ROOT, ADR, ART, read, save, sha, RESPONSE_RECEPTION, WHITESPACE_LIMIT
from replay_transport import RecordedTransport, ReplayBoundary, offline_network, offline_credential
import profile_capture

MAX_CALLS = 40
MAX_TOOLS = 1024
WALL_SECONDS = 1800
MEMORY_LIMIT = 4 * 1024**3
MIN_AVAILABLE = 3 * 1024**3
ADDRESS_SPACE_LIMIT = 6 * 1024**3  # separate hard backstop, never called an RSS measurement
MIN_DISK_FREE = 20 * 1024**3
MAX_SWAP_INCREASE = 512 * 1024**2
STOP = ART / 'replay-stop.json'
MATRIX = ART / 'replay'
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


def swap_used():
    fields = {line.split(':',1)[0]:int(line.split()[1])*1024
              for line in Path('/proc/meminfo').read_text().splitlines()
              if line.startswith(('SwapTotal:','SwapFree:'))}
    return fields['SwapTotal']-fields['SwapFree']


def process_rss(pid=None):
    try:
        return next((int(line.split()[1])*1024 for line in
            Path(f'/proc/{pid or os.getpid()}/status').read_text().splitlines()
            if line.startswith('VmRSS:')), 0)
    except FileNotFoundError:
        return 0


def resource_reading(*, baseline_swap, pid=None):
    return {'rss_bytes':process_rss(pid),'available_memory_bytes':available_memory(),
            'disk_free_bytes':shutil.disk_usage(ROOT).free,'swap_used_bytes':swap_used(),
            'baseline_swap_bytes':baseline_swap}


def resource_cause(reading):
    if reading['rss_bytes']>MEMORY_LIMIT:return 'PROCESS_MEMORY_LIMIT'
    if reading['available_memory_bytes']<MIN_AVAILABLE:return 'SYSTEM_AVAILABLE_MEMORY_LIMIT'
    if reading['disk_free_bytes']<MIN_DISK_FREE:return 'DISK_FREE_LIMIT'
    if reading['swap_used_bytes']-reading['baseline_swap_bytes']>MAX_SWAP_INCREASE:return 'SWAP_INCREASE_LIMIT'
    return None


def resource_baseline(frozen):
    path=ART/'matrix-resource-baseline.json'
    value={'schema_version':'mvp-resource-baseline-v1',
           'design_freeze_sha256':sha(ART/'design-freeze.json'),
           'swap_used_bytes':swap_used()}
    if not path.exists():
        try:durable(path,value,exclusive=True)
        except FileExistsError:pass
    saved=read(path)
    require(saved.get('schema_version')=='mvp-resource-baseline-v1'
        and saved.get('design_freeze_sha256')==value['design_freeze_sha256']
        and type(saved.get('swap_used_bytes')) is int, 'resource baseline binding changed')
    return saved['swap_used_bytes']


def resource_guard(cell, *, baseline_swap, phase):
    reading=resource_reading(baseline_swap=baseline_swap)
    cause=resource_cause(reading)
    if cause:
        stop('RESOURCE_FAILURE',cell=cell,cause=cause,phase=phase,resources=reading)
        raise ResourceFailure(cause)
    if STOP.exists():
        raise ResourceFailure('sticky matrix stop blocks new reservations')
    return reading


@contextmanager
def install_resource_guards(cell, *, baseline_swap, code_root):
    """Guard the real common repository API; restore it after this execution.

    The live runner and synthetic native-API checks call this same installer.
    V3-v6 projection checks run in their existing override before the exact
    WorkRepository reservation methods reached through super().
    """
    from semantic_runtime.legal_agent.repository import WorkRepository
    module = Path(sys.modules[WorkRepository.__module__].__file__).resolve()
    expected = Path(code_root)/'02_BACKEND/semantic_runtime/legal_agent/repository.py'
    require(module == expected.resolve(), 'resource guard repository is outside selected code')
    reserve_attempt = WorkRepository.reserve_attempt
    reserve_tool = WorkRepository.reserve_tool
    require(not getattr(reserve_attempt, '__adr_resource_guard__', False)
            and not getattr(reserve_tool, '__adr_resource_guard__', False),
            'resource admission guard already installed')
    counts = {'repository_class':'WorkRepository', 'repository_path':str(module),
              'model_guard_checks':0, 'model_reservations':0,
              'tool_guard_checks':0, 'tool_reservations':0}
    @wraps(reserve_attempt)
    def guarded_attempt(repo, view, request, logical_call_id, attempt_no, phase):
        counts['model_guard_checks'] += 1
        resource_guard(cell, baseline_swap=baseline_swap, phase='BEFORE_MODEL_RESERVATION')
        result = reserve_attempt(repo, view, request, logical_call_id, attempt_no, phase)
        counts['model_reservations'] += 1
        return result
    @wraps(reserve_tool)
    def guarded_tool(repo):
        counts['tool_guard_checks'] += 1
        resource_guard(cell, baseline_swap=baseline_swap, phase='BEFORE_TOOL_RESERVATION')
        result = reserve_tool(repo)
        counts['tool_reservations'] += 1
        return result
    guarded_attempt.__adr_resource_guard__ = True
    guarded_tool.__adr_resource_guard__ = True
    WorkRepository.reserve_attempt = guarded_attempt
    WorkRepository.reserve_tool = guarded_tool
    try:
        yield counts
    finally:
        WorkRepository.reserve_attempt = reserve_attempt
        WorkRepository.reserve_tool = reserve_tool


def before_physical_call(cell, *, baseline_swap):
    """A local resource refusal is known not sent, never unknown acceptance."""
    from semantic_runtime.legal_agent.errors import TransportError
    try:
        return resource_guard(cell, baseline_swap=baseline_swap, phase='BEFORE_PHYSICAL_CALL')
    except ResourceFailure as exc:
        raise TransportError(str(exc), retryable=False, unknown=False, response={
            'acceptance':'NOT_SENT', 'physical_request_sent':False,
            'failure_code':'EXPERIMENT_RESOURCE_STOP', 'phase':'BEFORE_PHYSICAL_CALL'}) from exc


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


def bound_code(frozen, arm, run_id):
    """Resolve an exact registered arm revision, never a mutable snapshot."""
    bindings = [r for r in frozen.get('arm_code_bindings', []) if r.get('arm_id') == arm]
    require(len(bindings) == 1, 'missing or duplicate frozen arm binding: ' + arm)
    binding = bindings[0]
    manifest_path = rooted(binding['manifest_path'])
    require(manifest_path.is_relative_to(ROOT/'02_BACKEND/lawrag/research/candidates/adr_1068')
        and binding.get('experiment_id') == frozen['experiment_id']
        and run_id in binding.get('run_ids', []), 'candidate experiment/run binding changed')
    checked(manifest_path, binding['manifest_sha256'])
    candidate = read(manifest_path)
    require(candidate.get('experiment_id') == frozen['experiment_id']
        and candidate.get('arm_id') == arm and run_id in candidate.get('run_ids', [])
        and candidate.get('production_loadable') is False, 'registered candidate identity changed')
    revisions = [r for r in candidate['revisions'] if r['revision_id'] == binding['revision_id']]
    require(len(revisions) == 1, 'candidate revision missing or duplicated')
    revision = revisions[0]
    require(revision['revision_sha256'] == binding['revision_sha256']
        and digest({k:v for k,v in revision.items() if k != 'revision_sha256'}) == binding['revision_sha256'],
        'candidate revision hash changed')
    code = (manifest_path.parent/'revisions'/binding['revision_id']/'snapshot').resolve()
    files = {}
    for row in revision['files']:
        path = rooted(row['frozen_path'])
        require(path.is_relative_to(code), 'revision file escaped frozen code')
        relative = str(path.relative_to(code))
        require(relative not in files, 'duplicate revision file')
        files[relative] = row['snapshot_sha256']
    require(bool(files), 'empty frozen file map')
    return code, files


def load_frozen(*, replay_arm=None):
    """Pure-file checks only: no runtime imports, source DB, credentials or model."""
    freeze_path = ART / 'design-freeze.json'
    frozen = read(freeze_path)
    require(frozen.get('enforce_input_character_limits') is False
        and frozen.get('minimal_action_choices') is True
        and frozen.get('mode_limits') == {key: None for key in
            ('entry','catalogue','review','repair','assess','compose','outer')},
        'action-choice or unenforced input contract changed')
    require(replay_arm in ('B0','B1'), 'offline replay arm is required; live execution forbidden')
    require(frozen.get('run_id') == 'run-001' and frozen.get('offline_only') is True
        and frozen.get('prefix_only') is True and frozen.get('external_model_calls_allowed') == 0,
        'offline-only run contract changed')
    require(frozen.get('resource_limits') == {'worker_rss_max_bytes':MEMORY_LIMIT,
        'available_memory_min_bytes':MIN_AVAILABLE, 'disk_free_min_bytes':MIN_DISK_FREE,
        'swap_increase_max_bytes':MAX_SWAP_INCREASE, 'address_space_backstop_bytes':ADDRESS_SPACE_LIMIT,
        'heavy_workers':1}, 'frozen resource limits differ from runner')
    require({r['arm_id'] for r in frozen['arm_code_bindings']} == {'B0','B1'}
        and len(frozen['arm_code_bindings']) == 2, 'offline arm inventory changed')
    source = frozen['source_experiment_freeze']
    checked(rooted(source['path']), source['sha256'])
    code, files = bound_code(frozen, replay_arm, 'run-001')
    frozen = deepcopy(frozen)
    frozen.update(code_root=str(code.relative_to(ROOT)), files=files,
        client_path=str((code/'02_BACKEND/lawrag/research/experiment_client.py').relative_to(ROOT)),
        client_sha256=files['02_BACKEND/lawrag/research/experiment_client.py'],
        policy_sha256=files['00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'])
    frozen['semantic_contract_files'] = {p:files[p] for p in frozen['semantic_contract_files']}
    for relative, expected in frozen['files'].items():
        checked(code / relative, expected)
    for relative, expected in frozen['runner_hashes'].items():
        checked(rooted(relative), expected)
    for runner in (Path(__file__), Path(__file__).with_name('run_matrix.py'), TRACE):
        require(str(runner.relative_to(ROOT)) in frozen['runner_hashes'], 'runner is not frozen')
    for name in ('common.py','replay_transport.py','profile_capture.py','extract_timing.py'):
        require(str(Path(__file__).with_name(name).relative_to(ROOT)) in frozen['runner_hashes'],
                'shared runner helper is not frozen: '+name)
    replay_contract=frozen.get('replay_contract',{})
    require(replay_contract.get('allow_prefix_diagnostic') is True, 'missing offline replay contract')
    checked(rooted(replay_contract['inventory_path']),replay_contract['inventory_sha256'])
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
    require(policy.get('provider_failover') is None and frozen.get('provider_failover') is None
        and policy.get('model') == 'qwen/qwen3.8-27b'
        and policy.get('allowed_upstream_providers') == ['Parasail']
        and policy.get('reasoning') == {'effort':'none'}
        and policy.get('provider_routing') == {'only':['parasail/fp8'], 'order':['parasail/fp8'],
            'quantizations':['fp8'], 'allow_fallbacks':False, 'require_parameters':True},
        'single-provider experiment policy changed')
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
    require(len(cases) == 3 and all(set(c) == {'case_id', 'question'} for c in cases),
        'product cases must contain only 3 IDs/questions')
    by_id = {c['case_id']: c for c in cases}
    require(len(by_id) == 3, 'duplicate product case')
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
    require(order == [{'ordinal':1,'case_id':'fsc-hard-005','arm':'A0'}],
            'only the original first A0 prefix is authorized')
    cell_directory(order[0])
    return frozen, code, by_id, corpus, authorization, snapshot


def request_for(frozen, cell, question, document_ids):
    ident = f"adr1068-{cell['ordinal']:03d}-{cell['case_id']}-{cell['arm']}"
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


def effective_profile(base, model_binding, ontology_config):
    """The exact production-run candidate profile, also consumed by native API tests."""
    from semantic_runtime.legal_agent.workflow_tiers_policy import profile as normalize_profile
    require(base['max_model_attempts'] == MAX_CALLS and base['max_tool_actions'] == MAX_TOOLS
        and base['wall_seconds'] == WALL_SECONDS and base['max_output_tokens'] is None,
        'base profile budgets changed')
    require(base['max_transport_retries'] == 1, 'single-provider transport retry budget changed')
    return normalize_profile({**deepcopy(base), 'model_binding': deepcopy(model_binding),
        'candidate_navigation': {**deepcopy(base['candidate_navigation']),
            'ontology_context': deepcopy(ontology_config), 'execution_review': True,
            'task_local_navigation': True, 'enforce_input_character_limits': False,
            'minimal_action_choices': True}}, require_model=True)


def expected_prefix_boundary(error, replay):
    """Recognize a boundary only when every grouped leaf is known and local.

    Cancellation alone is not a completed prefix. A wrapped unrelated error,
    even alongside a genuine boundary, must remain a fatal observation.
    """
    if replay is None or replay.calls != 0 or replay.visits != 1 or len(replay.matches) != 1:
        return None
    expected = replay.matches[0]
    leaves=[];pending=[(error,0)]
    while pending:
        leaf,depth=pending.pop()
        if depth>64 or len(leaves)+len(pending)>256:return None
        if isinstance(leaf,BaseExceptionGroup):
            pending.extend((child,depth+1) for child in leaf.exceptions)
        else:leaves.append(leaf)
    boundaries=[];cancelled=0
    for leaf in leaves:
        if isinstance(leaf,ReplayBoundary) and leaf.code=='REPLAY_PREFIX_DIAGNOSTIC':
            if (leaf.details.get('actual_sha256')!=expected.get('actual_sha256')
                    or leaf.details.get('expected_sha256')!=expected.get('expected_sha256')
                    or leaf.details.get('matched_responses')!=0):return None
            boundaries.append(leaf)
        elif isinstance(leaf,asyncio.CancelledError):cancelled+=1
        else:return None
    if not boundaries:return None
    return {'boundary_leaf_count':len(boundaries),'cancelled_leaf_count':cancelled,
        'grouped':isinstance(error,BaseExceptionGroup),'request_check':deepcopy(expected),
        'full_service_replay_verified':False,'recorded_responses_used':0,'external_model_calls':0}


def run(cell, loaded, *, replay=None):
    frozen, code, cases, corpus, authorization, snapshot = loaded
    require(replay is not None and replay.arm in ('B0','B1'), 'offline transport is mandatory')
    require(cell == {'ordinal':1,'case_id':'fsc-hard-005','arm':'A0'}, 'unauthorized prefix cell')
    require(not STOP.exists(), 'offline experiment has a sticky stop')
    baseline_swap=resource_baseline(frozen)
    initial_resources=resource_guard(cell,baseline_swap=baseline_swap,phase='BEFORE_CELL_RESERVATION')
    out = ART/'replay'/replay.arm/cell_directory(cell).name
    # Exclusive cell creation is the irreversible execution reservation. An
    # incomplete reservation needs explicit review; never recreate its budget.
    out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    request, public_question = request_for(frozen, cell, cases[cell['case_id']]['question'], corpus['document_ids'])
    if replay is not None:
        # Preserve the historical outer request exactly. Never transplant its
        # generated internal view IDs into the current server state.
        original = replay.outer_request
        require(original.get('API_TYPE') == 'RAG_ASK' and original.get('json') == request['json'],
                'replay outer request question/scope/publicity differs')
        request = deepcopy(original)
        replay.out = out
    durable(out / 'request.json', request, exclusive=True)
    durable(out / 'reservation.json', {'cell': cell, 'request_id': request['request_id'],
        'design_freeze_sha256': sha(ART / 'design-freeze.json'), 'reserved_at': time.time(),
        'deadline_seconds': WALL_SECONDS, 'max_calls': MAX_CALLS, 'max_tools': MAX_TOOLS,
        'resource_contract':{'worker_rss_max_bytes':MEMORY_LIMIT,'available_memory_min_bytes':MIN_AVAILABLE,
            'disk_free_min_bytes':MIN_DISK_FREE,'swap_increase_max_bytes':MAX_SWAP_INCREASE,
            'address_space_backstop_bytes':ADDRESS_SPACE_LIMIT,'initial':initial_resources},
        'replay_arm':replay.arm if replay else None,
        'reuse_policy': 'NEVER_RERUN_EXISTING_CELL'}, exclusive=True)
    os.environ.update(GENOS_RUNTIME_DIR=str(out / 'runtime'), AD_WORKER_ENABLED='0',
        GENOS_AUTO_WARMUP='0', GENOS_RESIDENT_DATA='off', MALLOC_ARENA_MAX='1',
        LAWRAG_WORKSPACE_ROOT=str(ROOT), TOOL_WORKSPACE_ROOT=str(ROOT),
        GENOS_FUNCTION_TIMING='1', GENOS_FUNCTION_TIMING_MODE='coarse')
    for key in ('TEAM_ID', 'AD_WORKSPACE', 'DP', 'GENOS_SHARED_LOG_DIR',
                'GENOS_STATE_DIR', 'GENOS_GENERATION', 'GENOS_DATA_ROOT', 'GENOS_MEMORY_JOURNAL_MODE'):
        os.environ.pop(key, None)
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(code), str(code / '02_BACKEND'), str(ROOT / '02_BACKEND')]
    result = {'cell': cell, 'request_id': request['request_id'], 'completed': False,
        'code_root': str(code.relative_to(ROOT)), 'known_in_sample': True,
        'model_calls': 0, 'usage': [], 'error': None}
    app = client = None
    observations = []
    events = []
    guard_contexts = ExitStack()
    resource_admission = None
    profile_events = guard_contexts.enter_context(profile_capture.capture())
    service_seconds = None
    try:
        if replay is not None:
            guard_contexts.enter_context(offline_network())
            guard_contexts.enter_context(offline_credential(replay.policy))
        try:
            resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_SPACE_LIMIT, ADDRESS_SPACE_LIMIT))
        except (ValueError, OSError) as exc:
            result['resource_limit_error'] = {'type':type(exc).__name__, 'message':str(exc),
                'requested_address_space_bytes':ADDRESS_SPACE_LIMIT}
            raise ResourceFailure('ADDRESS_SPACE_BACKSTOP_UNAVAILABLE') from exc
        import lawrag
        lawrag.__path__.append(str(ROOT / '02_BACKEND/lawrag'))
        from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
        from semantic_runtime.legal_agent.errors import TransportError, ProposalError, BudgetExhausted, ContractError
        from semantic_runtime.legal_agent.investigation_diagnostics import exception_diagnostics
        import semantic_runtime.app as app_module
        resource_admission = guard_contexts.enter_context(install_resource_guards(
            cell, baseline_swap=baseline_swap, code_root=code))

        product_client = Path(importlib.util.find_spec('lawrag.research.experiment_client').origin).resolve()
        require(product_client == rooted(frozen['client_path']), 'product imported an unfrozen model client')
        checked(product_client, frozen['client_sha256'])
        client = replay
        original_error = app_module.legal_error_payload
        def observe_error(exc, *args, **kwargs):
            diagnostic = exception_diagnostics(exc)
            observations.append(diagnostic)
            append(out / 'native-failures.jsonl', diagnostic)
            return original_error(exc, *args, **kwargs)
        app_module.legal_error_payload = observe_error

        require(client.failover_spec is None, 'provider failover must be disabled')

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
                before_physical_call(cell,baseline_swap=baseline_swap)
                payload = self.preview_request(body)
                require(payload.get('stream') is True
                    and payload.get('stream_options', {}).get('include_usage') is True,
                    'product preview omitted buffered stream/usage request')
                require(not {'max_tokens', 'max_completion_tokens', 'max_output_tokens'} & set(payload),
                    'uncapped experiment constructed an output cap')
                if replay is not None:
                    return replay.reply(payload)

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
        profile = effective_profile(base, transport.binding, config)
        durable(out / 'effective-profile.json', profile, exclusive=True)
        app = app_module.create_app(ROOT, rooted(frozen['data_path']), contracts_root=code,
            workspace_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
            runtime_root=out / 'runtime', legal_agent_profile=profile, legal_agent_transport=transport,
            release={'mode': 'local-experiment', 'release_id': 'ontology-mvp-adr1068-r1'})
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
            'http_retries': 0, 'transport_retries': profile['max_transport_retries'], 'output_token_cap': None,
            'provider_failover':client.failover_spec, 'provider_retry_owner':'gateway',
            'response_reception':RESPONSE_RECEPTION, 'whitespace_limit':WHITESPACE_LIMIT,
            'product_client_path':frozen['client_path'], 'product_client_sha256':frozen['client_sha256'],
            'unverified_partial_tokens_public':False,
            'external_model_calls_enabled':False, 'replay_arm':replay.arm if replay else None,
            'entrypoint': 'frozen service.service -> POST /v1/rag/ask'}, exclusive=True)
        service_started = time.monotonic()
        try:
            response = asyncio.run(service.service({}, request))
        finally:
            service_seconds = time.monotonic() - service_started
        durable(out / 'response.json', response, exclusive=True)
        result['service_status'] = response.get('status')
        result['native_failures'] = observations
        raise IntegrityFailure('service returned before the mandatory offline prefix boundary')
    except BaseException as exc:
        boundary = expected_prefix_boundary(exc, replay)
        if boundary is not None and not STOP.exists():
            result.update(outcome='REPLAY_PREFIX_DIAGNOSTIC', completed=True,
                full_service_replay_verified=False, diagnostic_only=True,
                replay_details=boundary, external_model_calls=0, attempt_diagnostic_count=1)
        else:
            result.update(outcome='FATAL_STOP', completed=False,
                full_service_replay_verified=False, diagnostic_only=True,
                error={'type':type(exc).__name__, 'message':str(exc), 'traceback':traceback.format_exc()})
            stop('RESOURCE_FAILURE' if isinstance(exc,(MemoryError,ResourceFailure))
                else 'RUNNER_OR_INTEGRITY_FAILURE', cell=cell, error_type=type(exc).__name__)
    finally:
        guard_contexts.close()
        actual_calls = 0
        result.update(seconds=time.monotonic() - start, model_calls=actual_calls,
            usage=[{'call': event['call'], **event['usage']} for event in events],
            usage_complete=bool(replay is None and client is not None and len(events) == client.calls
                and all(e['usage']['raw_usage'] is not None for e in events)),
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            remaining_call_budget=MAX_CALLS - (client.calls if client else 0), replay_allowed=False,
            final_resources=resource_reading(baseline_swap=baseline_swap),
            resource_admission=deepcopy(resource_admission))
        if app is not None:
            try:
                app.state.pipeline.store.close()
            except Exception as exc:
                result.update(completed=False, outcome='FATAL_STOP', close_error=type(exc).__name__)
                stop('STORE_CLOSE_FAILURE', cell=cell)
        if replay is not None:
            durable(out/'replay-receipt.json', replay.receipt(), exclusive=True)
        profile = profile_capture.receipt(profile_events, freeze_hash=sha(ART/'design-freeze.json'),
            code_root=str(code.relative_to(ROOT)), replay=replay is not None, service_seconds=service_seconds)
        durable(out/'profile.json', profile, exclusive=True)
        result['profile_complete'] = profile['profile_complete']
        result['profile_sha256'] = sha(out/'profile.json')
        durable(out / 'result.json', result, exclusive=True)
    print(json.dumps({k: result[k] for k in ('cell', 'outcome', 'completed', 'model_calls', 'seconds')}, ensure_ascii=False), flush=True)
    return 0 if result['completed'] else 2


def main():
    global STOP
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ordinal', type=int, required=True)
    parser.add_argument('--inspect-only', '--dry-run', action='store_true')
    parser.add_argument('--replay-arm', choices=('B0','B1'), required=True)
    args = parser.parse_args()
    if args.replay_arm:
        STOP = ART/'replay-stop.json'
    loaded = load_frozen(replay_arm=args.replay_arm)
    matches = [cell for cell in loaded[0]['execution_order'] if cell['ordinal'] == args.ordinal]
    require(len(matches) == 1, 'unknown cell ordinal')
    cell = matches[0]
    if args.inspect_only:
        print(json.dumps({'cell': cell, 'out': str(cell_directory(cell)), 'frozen_inputs_verified': True,
            'live_model_calls': 0, 'runtime_loaded': False}, ensure_ascii=False))
        return 0
    replay = RecordedTransport(loaded[0], cell, args.replay_arm)
    with process_lock('.matrix-case.lock'):
        return run(cell, loaded, replay=replay)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except IntegrityFailure as exc:
        # Inspection is read-only, including on failure.
        if '--inspect-only' not in sys.argv and '--dry-run' not in sys.argv:
            stop('RUNNER_OR_INTEGRITY_FAILURE', error=str(exc))
        print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        raise SystemExit(2)
