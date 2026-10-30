"""Opt-in source selection; numerical limits are policy bounds, not quality claims."""
from . import relations_policy as v3
from .errors import ContractError
IMPLEMENTATION = 'legal-agent-tools-v5'
PROFILE_ID = 'legal-agent-rag-v5'
DEFAULT_PROFILE = {**v3.DEFAULT_PROFILE, 'schema_version':'system-harness-profile-v5',
    'profile_id':'hardened-obligations-v5', 'max_output_tokens':None, 'question_obligations_enabled':True, 'numbered_references_enabled':True, 'max_core_sources':5, 'max_supplemental_sources':5,
    'max_source_excerpt_chars':1600, 'source_page_size':4, 'source_selection_attempts':2,
    'selection_time_reserve_seconds':30, 'max_auto_reference_reads_per_request':12,
    'bounded_source_selection_enabled':False, 'final_review_enabled':False,
    'candidate_navigation': {'mode': 'legacy'}, 'request_entry_policy':'legacy', 'answer_presentation':'structured'}
DOMAIN = {**v3.DOMAIN, 'schema_version':'legal-domain-v5', 'domain_id':'model-selected-source-tiers',
    'completion':'source_selection_independent_of_legal_claim_review'}
def profile(value, *, require_model=False):
    if set(value)-set(DEFAULT_PROFILE): raise ContractError('unknown v4 profile field')
    p={**DEFAULT_PROFILE, **value}
    if p['schema_version']!=DEFAULT_PROFILE['schema_version']: raise ContractError('v4 profile required')
    v3.profile({**{k:p[k] for k in v3.DEFAULT_PROFILE}, 'schema_version':v3.DEFAULT_PROFILE['schema_version']},require_model=require_model)
    if not p['question_obligations_enabled'] or not p['numbered_references_enabled']:
        raise ContractError('v5 requires question obligations and numbered references')
    if type(p['question_obligations_enabled']) is not bool: raise ContractError('question_obligations_enabled must be bool')
    if type(p['numbered_references_enabled']) is not bool: raise ContractError('numbered_references_enabled must be bool')
    if type(p['bounded_source_selection_enabled']) is not bool: raise ContractError('bounded_source_selection_enabled must be bool')
    if type(p['final_review_enabled']) is not bool: raise ContractError('final_review_enabled must be bool')
    if p['request_entry_policy'] not in ('legacy','fused-v1','fused-title-v1'):raise ContractError('unknown request entry policy')
    if p['answer_presentation'] not in ('structured','grounded-narrative-v1','accepted-content-v1'):raise ContractError('unknown answer presentation')
    from .law_candidates import validate_policy
    p['candidate_navigation']=validate_policy(p['candidate_navigation'])
    for k in set(DEFAULT_PROFILE)-set(v3.DEFAULT_PROFILE)-{'question_obligations_enabled', 'numbered_references_enabled', 'bounded_source_selection_enabled', 'final_review_enabled', 'candidate_navigation', 'request_entry_policy', 'answer_presentation'}:
        if type(p[k]) is not int or p[k]<1: raise ContractError('invalid v4 bound: '+k)
    if p['source_selection_attempts']>=p['finalization_reserve']: raise ContractError('reserve must cover source selection and composition')
    if not p['bounded_source_selection_enabled'] and p['max_core_sources']+p['max_supplemental_sources']>20:
        raise ContractError('legacy source selection permits at most 20 cards')
    return p
def domain(value):
    if value!=DOMAIN: raise ContractError('unsupported v4 domain')
    return dict(value)
SYSTEM = v3.SYSTEM + (' Select relevant whole delivered sources using source choices. This is relevance, not proof. '
    'Source cards bind source ID and exact text together. Never return block offsets, span IDs or REVIEWED. '
    'KEEP_CORE for governing rules and decisive exceptions, KEEP_SUPPLEMENTAL for useful context. '
    'No selection is not absence. Empty search is only that query result. '
    'On errors correct rejected operations; successful choices remain stored. '
    'For READ use candidate read_action; corpus R is only for discovery. '
    'Optional assessments and relation_assessments should be empty: claim composition and review happen after selection.')
PROMPTS = {**v3.PROMPTS, 'investigate':
    'Discover documents, READ promising candidate read_action, then select exact_evidence.source using choices. '
    'Do not stop just because search found candidates: read relevant candidates first. '
    'Follow direct references to necessary exceptions or subordinate rules when relevant. '
    'After actions observe their results on the next turn. Choose DRAFT when selected sources are sufficient or clearly bounded. '
    'source_selection can be null before reading. Return empty assessments and relation_assessments.',
    'select_sources':'Choose from exact_evidence.source with decision and reason only. Preserve relevant full delivered sources. '
    'Keep existing selections unless explicitly replacing/rejecting. Uncertain interpretation does not preclude relevant selection.'}

PROMPTS['compose']='Draft only claims supported by the selected delivered evidence pack. Selection is not legal proof. Cite evidence IDs and question refs; declare any relation_dependencies actually relied on. Check exceptions, actor, scope and missing facts. Do not infer absent text. Return limitations for unresolved parts.'
PROMPTS['review']='Independently compare every current claim with exact evidence and the entire original question. Selection and drafting are not approval. Check governing rule, relevant exceptions, missing subordinate rules, actor and scope; missing decisive text requires NEEDS_RESEARCH or UNCERTAIN, never SUPPORTED. Verify declared relation dependencies. Return one check per claim and overall question status.'

PROMPTS['review']+=' Each claims card has claim (the ID, such as C1) and text. Copy only that claim ID into checks[].claim, never the text. The output enum lists exactly the valid IDs.'

SYSTEM += ' For each explicit READ the server reads all small direct reference sets, including incoming links. Automatic target reads do not expand recursively. Check relation_delivery: if selection is required, choose target read_actions or continue the relation scan; do not treat unscanned or unresolved links as absent. Auto-read text still needs relevance selection and review.'
