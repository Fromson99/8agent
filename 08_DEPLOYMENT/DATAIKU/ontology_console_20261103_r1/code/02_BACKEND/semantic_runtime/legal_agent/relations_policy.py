"""V3 relation discovery policies. All numbers are bounds, not quality claims."""
from . import tools_policy as v2
from .errors import ContractError

IMPLEMENTATION = 'legal-agent-tools-v3'
PROFILE_ID = 'legal-agent-rag-v3'
# relation_scan_seconds is retained for serialized profile compatibility only.
# Relation discovery uses the request deadline; this legacy value is not enforced.
DEFAULT_PROFILE = {**v2.DEFAULT_PROFILE, 'schema_version': 'system-harness-profile-v3',
    'profile_id': 'tool-exploration-v3', 'preview_chars': 360, 'max_preview_chars': 3600,
    'relation_page_size': 12, 'max_relation_chars': 14000, 'relation_scan_seconds': 5,
    'auto_reference_read_depth': 1, 'max_auto_reference_reads_per_request': 3,
    'max_auto_reference_chars_per_request': 12000, 'tool_finalization_reserve': 4,
    'max_summary_items': 60}
DOMAIN = {**v2.DOMAIN, 'schema_version': 'legal-domain-v3',
    'domain_id': 'audited-relation-aware-source-judgments',
    'relations': 'reference_definition_term_occurrence_structure_and_source_knowledge',
    'completion': 'question_scoped_assessments_and_joint_relation_review'}


def profile(value, *, require_model=False):
    if set(value) - set(DEFAULT_PROFILE):
        raise ContractError('unknown v3 execution profile fields')
    result = {**DEFAULT_PROFILE, **value}
    if result['schema_version'] != DEFAULT_PROFILE['schema_version']:
        raise ContractError('v3 profile version required')
    v2.profile({**{k: result[k] for k in v2.DEFAULT_PROFILE},
                'schema_version': v2.DEFAULT_PROFILE['schema_version']}, require_model=require_model)
    for key in set(DEFAULT_PROFILE)-set(v2.DEFAULT_PROFILE):
        if type(result[key]) is not int or result[key] < 1:
            raise ContractError('invalid v3 limit: '+key)
    if result['auto_reference_read_depth'] != 1 or result['relation_page_size'] > 100:
        raise ContractError('v3 automatic depth must be one; relation page <=100')
    if result['tool_finalization_reserve'] >= result['max_tool_actions']:
        raise ContractError('tool reserve leaves no exploration budget')
    if result['preview_chars'] > result['max_preview_chars']:
        raise ContractError('preview span exceeds preview budget')
    return result


def domain(value):
    if value != DOMAIN:
        raise ContractError('unsupported v3 domain policy')
    return dict(value)


SYSTEM = v2.SYSTEM + (' Record short verifiable purposes, not hidden reasoning. Distinguish MODEL, REVIEWER and '
    'SYSTEM_POLICY actions. Previews and relation hints are navigation data, never citation evidence. '
    'Discovery, storage, successful presentation, assessment and legal applicability are separate. '
    'Never treat unknown/omitted/denied relations as absence. Preserve original relation direction and predicate. '
    'R is the corpus and F is a folder: neither can be READ. When only corpus_root is available, '
    'locate a named article or search within corpus_root, then READ the returned D/P/U target. '
    'Use cursor=null for a new operation; reuse a cursor only with its original tool and arguments. '
    'Input is paged. Request a supplied continuations/view_page action when more is needed. '
    'When relation_menu is present, select useful relation IDs with inspect_relation; menu cards are not '
    'full notices or evidence and cannot be assessed. Then READ selected target handles as needed. '
    'Never assume omitted items were reviewed. READ next_cursor continues the original source extent.')
PROMPTS = {**v2.PROMPTS,
    'investigate': v2.PROMPTS['investigate'] + ' Every action needs question_refs and expected_information. '
        'Assess E separately for each question_ref with exact basis_spans. Assess relevant relation_notices '
        'using source/target evidence and scope, substitution, exception notes. NOT_RELEVANT needs source evidence; '
        'a target-content reason also needs target evidence. DEFER when unresolved. Follow relations or inspect '
        'omitted pages; automatic prefetch does not imply adoption. Clear targets may be read immediately.',
    'compose': v2.PROMPTS['compose'] + ' Declare relation_dependencies for relationships used in each claim. '
        'Every outgoing citation/delegation/annex/mutatis-mutandis relation on adopted evidence needs an '
        'explicit relevance decision. Use only jointly presented source and target extents for dependencies. '
        'Defer blocked claims while retaining independent supported claims.',
    'review': v2.PROMPTS['review'] + ' List relation_checks for every relevant or excluded reference attached '
        'to this claim. Compare source, target, scope, substitutions, exceptions and exclusion reasons in '
        'the same view. A relation predicate is a hint and may be mistaken; never endorse unsupported interpretation.'}

GUIDANCE = {
    'VERIFY_SOURCE_TARGET_SCOPE': '이 원문에 연결 단서가 있습니다. 관계를 근거로 사용할 때 출발·대상 원문과 적용 범위·치환·예외를 함께 확인하십시오. 관계 표시는 사례 적용 확정이 아닙니다.',
    'WITNESS_NOT_VERIFIED': '색인 연결의 출발 문언을 아직 검증하지 못했습니다. 원문 위치를 확인하십시오.',
    'VERIFY_DEFINITION_SCOPE': '같은 표제어의 정의 후보입니다. 이 문서와 질문에 적용되는 정의 범위를 확인하십시오.',
    'TERM_NAVIGATION_HINT': '용어 관계의 원래 유형과 방향을 보존한 탐색 단서입니다. 관련 규정의 적용을 뜻하지 않습니다.',
    'OCCURRENCE_NOT_APPLICABILITY': '같은 용어가 출현하는 원문입니다. 적용 가능성은 원문을 읽고 별도로 판단하십시오.',
    'STRUCTURAL_CONTEXT_NOT_LEGAL_EFFECT': '현재 읽은 부분의 구조상 주변 문맥입니다. 상하위 구조를 법적 우선순위로 해석하지 마십시오.',
    'SHARED_LABEL_NOT_SAME_MEANING': '표기가 연결된 개념 후보입니다. 의미 동일성이나 법적 적용이 승인된 상태가 아닙니다.',
    'LEXICAL_OBSERVATION_NOT_APPROVED': '정의에 근거한 용어 의미 검토 관측입니다. 정본 병합이나 현재 사례 적용 승인이 아닙니다.',
    'SOURCE_KNOWLEDGE_UNAPPROVED': '원천 자료에 기록된 관계입니다. 출처·방향·검토 상태를 확인하십시오.',
    'SOURCE_DEFINITION_NOT_LOCAL_APPLICABILITY': '원천 정의 자료입니다. 해당 문서의 정의 또는 현재 사례에 자동 적용하지 마십시오.'}
