"""Closed host policy over existing precondition owners. No I/O or retries."""
from dataclasses import asdict, dataclass
from types import MappingProxyType
from ..contracts import digest
from .errors import ContractError
from .tool_outcome import validate_outcome

VERSION = 'tool-policy-v1'
LEGACY = 'legacy-tool-adapters-v0'


@dataclass(frozen=True)
class ToolSpec:
    surface: str
    name: str
    precondition: str
    recovery_owner: str
    effect_class: str
    resume_rule: str
    allowed_recovery: tuple[str, ...]
    result_contract: str
    same_operation_automatic_retries: int = 0


def _specs():
    families = (
        ('navigation', 'READ_ARTICLES READ_PARENT READ_SCOPE VIEW_SAVED_SOURCE RESEARCH SEARCH_BODY SEARCH_STRUCTURE OPEN_STRUCTURE BROWSE_STRUCTURE NEXT_STRUCTURE NEXT_LAWS OPEN_LAW NEXT_ARTICLES NEXT_HITS FOLLOW_CONNECTION RETURN_TO',
         'tool_availability.navigation_reason','investigation','observation','verified_read_receipts',
         ('CONTINUE','REBUILD_MENU','OFFER_ALTERNATIVE','RESUME_REMAINDER','ASSESS_VERIFIED_ONLY','STOP')),
        ('reference','FOLLOW SKIP DEFER','unit_relations.validate','reference','observation','reference_checkpoint',
         ('CONTINUE','REBUILD_MENU','RESUME_REMAINDER','STOP')),
        ('ending','DECIDE FINISH PENDING','law_navigation.validate','investigation','terminal','accepted_decision',
         ('CONTINUE','ASSESS_VERIFIED_ONLY','STOP')),
        ('memory','CASE_START FACT_UPDATE STATE_RESTORE PURPOSE_REVISE RESEARCH_REPLAN RESEARCH_REENTER ANSWER_PRESENT HISTORY_EXPLAIN EXPERIENCE_CONFIRM EXPERIENCE_REUSE WIKI_RELINK NEED_TARGET',
         'memory_methods.offered','case','case_mutation','case_owner_current_revision',('CONTINUE','RESUME_REMAINDER','STOP')),
        ('entry','CASE_START NEED_TARGET','request_entry.accept','request_entry','terminal','request_entry_binding',('CONTINUE','STOP')),
        ('wiki_hint','history_ids','wiki_recall.selected_route','wiki_recall','hint','current_authority_hash',('CONTINUE','STOP')),
    )
    for surface,names,precondition,owner,effect,resume,recovery in families:
        for name in names.split():
            allowed = ('CONTINUE','STOP') if surface=='memory' and name in {'HISTORY_EXPLAIN','NEED_TARGET'} else recovery
            actual_effect=('terminal' if surface=='memory' and name=='NEED_TARGET' else
                           'observation' if surface=='memory' and name=='HISTORY_EXPLAIN' else effect)
            yield (surface,name), ToolSpec(surface,name,precondition,owner,actual_effect,resume,allowed,precondition)


REGISTRY = MappingProxyType(dict(_specs()))
POLICY_HASH = digest([asdict(spec) for spec in REGISTRY.values()])


@dataclass(frozen=True)
class Availability:
    offered: bool
    reason_code: str | None
    current_binding_hash: str
    predicted_cost: tuple[int, int] = (0, 0)
    policy_version: str = VERSION


def assess_availability(surface, name, *, binding, reason=None, predicted_cost=(0,0)):
    """The named adapter supplies its existing authoritative precondition result."""
    if (surface,name) not in REGISTRY: reason = 'UNREGISTERED_ACTION'
    return Availability(reason is None, reason, digest({'binding':binding,'policy':POLICY_HASH}),predicted_cost)


def require_registered(surface, name):
    spec = REGISTRY.get((surface,name))
    if spec is None: raise ContractError('unregistered tool policy: '+surface+'.'+str(name))
    return spec


def bind_checkpoint(state, binding, *, legacy=False):
    expected = {'version':VERSION,'policy_hash':POLICY_HASH,'binding':binding}
    prior = state.get('tool_policy')
    if prior is None and legacy:
        # Explicit compatible reader: existing adapters still validate all
        # targets and budgets. Do not rewrite accepted historic model views.
        expected['version'] = LEGACY
    elif prior is not None:
        if prior.get('version') == LEGACY: expected['version'] = LEGACY
        if prior != expected: raise ContractError('tool policy checkpoint binding changed')
    state['tool_policy'] = expected
    return expected


@dataclass(frozen=True)
class RecoveryState:
    same_binding: bool = True
    stop_requested: bool = False
    distinct_alternative: bool = False
    verified_remainder: bool = False
    pre_execution_rejection: bool = False
    verified_originals: bool = False


@dataclass(frozen=True)
class RecoveryBudget:
    deadline_expired: bool = False
    investigation_available: bool = True
    finalization_available: bool = False


@dataclass(frozen=True)
class RecoveryDecision:
    action: str
    reason_code: str
    owner: str
    policy_version: str = VERSION


def choose_recovery(spec, outcome, current, budget):
    validate_outcome(outcome)
    def answer(action, reason):
        return RecoveryDecision(action if action in spec.allowed_recovery else 'STOP',reason,spec.recovery_owner)
    if not current.same_binding: return answer('STOP','CURRENT_BINDING_REQUIRED')
    if outcome.failure_kind in {'AUTH','INTEGRITY','STATE','UNKNOWN','INTERNAL'}:
        return answer('STOP',outcome.cause_code)
    if outcome.execution=='UNKNOWN' or outcome.effects=='UNKNOWN': return answer('STOP','RECEIPT_RECONCILIATION_REQUIRED')
    if current.stop_requested or budget.deadline_expired or outcome.failure_kind=='DEADLINE':
        return answer('STOP','STOP_OR_DEADLINE')
    if outcome.failure_kind=='BUDGET':
        return answer('ASSESS_VERIFIED_ONLY' if current.verified_originals and budget.finalization_available else 'STOP','BUDGET')
    if outcome.status in {'SUCCESS','EMPTY'}: return answer('CONTINUE','VERIFIED_RESULT')
    if outcome.status=='PARTIAL' and current.verified_remainder and budget.investigation_available:
        return answer('RESUME_REMAINDER','VERIFIED_REMAINDER')
    if outcome.failure_kind=='TRANSIENT' and current.distinct_alternative and budget.investigation_available:
        return answer('OFFER_ALTERNATIVE','SOURCE_TEMPORARILY_UNAVAILABLE')
    if outcome.failure_kind=='PROPOSAL' and current.pre_execution_rejection and budget.investigation_available:
        return answer('REBUILD_MENU','ACTION_REJECTED')
    return answer('STOP','NO_ALLOWED_RECOVERY')
