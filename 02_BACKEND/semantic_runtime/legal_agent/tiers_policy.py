"""Opt-in source selection; numerical limits are policy bounds, not quality claims."""
from . import relations_policy as v3
from .errors import ContractError
IMPLEMENTATION = 'legal-agent-tools-v4'
PROFILE_ID = 'legal-agent-rag-v4'
DEFAULT_PROFILE = {**v3.DEFAULT_PROFILE, 'schema_version':'system-harness-profile-v4',
    'profile_id':'tiered-sources-v4', 'max_core_sources':5, 'max_supplemental_sources':5,
    'max_source_excerpt_chars':1600, 'source_page_size':4, 'source_selection_attempts':2,
    'selection_time_reserve_seconds':30}
DOMAIN = {**v3.DOMAIN, 'schema_version':'legal-domain-v4', 'domain_id':'model-selected-source-tiers',
    'completion':'source_selection_independent_of_legal_claim_review'}
def profile(value, *, require_model=False):
    if set(value)-set(DEFAULT_PROFILE): raise ContractError('unknown v4 profile field')
    p={**DEFAULT_PROFILE, **value}
    if p['schema_version']!=DEFAULT_PROFILE['schema_version']: raise ContractError('v4 profile required')
    v3.profile({**{k:p[k] for k in v3.DEFAULT_PROFILE}, 'schema_version':v3.DEFAULT_PROFILE['schema_version']},require_model=require_model)
    for k in set(DEFAULT_PROFILE)-set(v3.DEFAULT_PROFILE):
        if type(p[k]) is not int or p[k]<1: raise ContractError('invalid v4 bound: '+k)
    if p['source_selection_attempts']>=p['finalization_reserve']: raise ContractError('reserve must cover source selection and composition')
    if p['max_core_sources']+p['max_supplemental_sources']>20: raise ContractError('source bundle schema permits at most 20 cards')
    return p
def domain(value):
    if value!=DOMAIN: raise ContractError('unsupported v4 domain')
    return dict(value)
SYSTEM = v3.SYSTEM + (' Source selection is relevance to the whole original question, not proof of a legal conclusion. '
    'Select exact presented span IDs as CORE or SUPPLEMENTAL with a short relevance reason. '
    'Exceptions that may change the answer can be CORE alongside the principle. Document class never fixes tier. '
    'Do not reject necessary text merely because its interpretation is uncertain. '
    'No selection is preferable to irrelevant sources. Menus and concept hints are not source evidence. '
    'Optional legal assessments and claims still require independent joint review.')
PROMPTS = {**v3.PROMPTS, 'investigate':
    'Explore using offered handles and continuations. After reading, select relevant spans or give pending/rejected reasons. '
    'source_selection may be null before any evidence. Selection does not require legal assessments; those arrays may be empty. '
    'Consider directly connected definitions and exceptions. Choose DRAFT when ready or bounded; do not repeat identical actions.',
    'select_sources':'Final short selection of already presented source spans only. No tools. Keep existing valid selections unless explicitly rejecting or replacing them. '
    'Select principle and exception together when relevant, even if interpretation is UNCERTAIN. Return pending/rejected reasons when unable to select.'}
