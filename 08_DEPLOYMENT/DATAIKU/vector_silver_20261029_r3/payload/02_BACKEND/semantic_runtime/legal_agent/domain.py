"""Separate, hash-bound domain policy and execution profile; no dynamic imports."""
import json
from pathlib import Path
from ..contracts import digest, sha
from .errors import ContractError

DOMAIN = {
    'schema_version': 'legal-domain-v1', 'domain_id': 'source-first-revisable-issues',
    'question_coverage': 'original_question_and_answer_direct_review',
    'evidence_policy': {'require_exact_spans': True, 'require_presented_before_adoption': True,
                        'scope_expansion': 'forbidden', 'unknown_effective_date': 'no_current_applicability_assertion'},
    'issue_policy': {'initial_issues_optional': True, 'hypotheses_may_restrict_source_access': False,
                     'changes_invalidate_dependents': True},
    'checks': ['CITATION_MEMBERSHIP', 'CURRENT_DEPENDENCIES', 'QUALIFIER_PRESERVATION',
               'REFERENCE_COMPLETION', 'CONFLICT_RESOLUTION', 'FACT_DEPENDENCY', 'DIRECT_QUESTION_COVERAGE'],
}
DEFAULT_PROFILE = {
    'schema_version': 'legal-agent-profile-v1', 'profile_id': 'initial-wiring',
    'model_binding': None, 'max_model_attempts': 14, 'finalization_reserve': 3,
    'max_tool_actions': 56, 'wall_seconds': 1800, 'max_cycles': 3, 'max_no_progress': 2,
    'max_schema_repairs': 1, 'max_transport_retries': 1, 'max_context_chars': 60000,
    'max_output_tokens': 80000, 'max_read_chars': 12000, 'page_size': 40,
    'max_concurrent_requests_per_process': 4,
}


def load_bound(root, binding):
    root = Path(root).resolve()
    path = (root/binding['path']).resolve()
    path.relative_to(root)
    if sha(path) != binding['sha256']:
        raise ContractError('legal-agent configuration hash mismatch')
    return json.loads(path.read_text())


def profile(value, *, require_model=False):
    if set(value)-set(DEFAULT_PROFILE):
        raise ContractError('unknown execution profile fields')
    result = {**DEFAULT_PROFILE, **value}
    if result['schema_version'] != 'legal-agent-profile-v1':
        raise ContractError('unsupported execution profile')
    for key in set(DEFAULT_PROFILE)-{'schema_version', 'profile_id', 'model_binding'}:
        v = result[key]
        # None delegates output length to the selected model server. Other
        # numerical budgets (including attempts and deadline) remain required.
        if key == 'max_output_tokens' and v is None:
            continue
        minimum = 0 if key in ('max_schema_repairs', 'max_transport_retries',
                              'max_concurrent_requests_per_process') else 1
        if type(v) is not int or v < minimum:
            raise ContractError('invalid execution limit: '+key)
    if result['max_model_attempts'] < result['finalization_reserve'] or result['finalization_reserve'] < 2:
        raise ContractError('compose and review attempt reserve required')
    if result['page_size'] > 500 or result['max_read_chars'] > result['max_context_chars']//2:
        raise ContractError('source page exceeds bounded context')
    if require_model:
        binding = result['model_binding']
        required = {'provider', 'model', 'adapter_version', 'endpoint_identity', 'trust_zone'}
        # Old pinned byte fields remain inert metadata; new bindings omit them.
        if not isinstance(binding, dict) or not required <= set(binding) or set(binding)-required-{'max_input_bytes'}:
            raise ContractError('explicit deployment model binding required')
        for key in required:
            if not isinstance(binding[key], str) or not binding[key] or 'REQUIRED' in binding[key]:
                raise ContractError('unresolved model binding')
    return result


def domain(value):
    # v1 has a single audited evaluator set. Changing policies needs new code/schema.
    if value != DOMAIN:
        raise ContractError('unsupported DomainSpec; no checks may be silently disabled')
    return json.loads(json.dumps(value))
