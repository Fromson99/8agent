"""Compact request-local demands. No legal rule database or extra model phase."""
from copy import deepcopy
from jsonschema import Draft202012Validator, ValidationError
from . import workflow_tiers_protocol as base
from .protocol import obj, arr, enum, ID
from .errors import ProposalError
SHORT = {'type': 'string', 'minLength': 4}
REFS = {**arr(ID, 1, 64), 'uniqueItems': True}
PLAN = obj({'demands': arr(obj({'question_refs': REFS, 'requirement': SHORT,
    'given_facts': arr(SHORT, 0, 6), 'missing_fact': {'anyOf': [SHORT, {'type': 'null'}]}}), 1, 8),
    'context_refs': {**arr(ID, 0, 64), 'uniqueItems': True}, 'change_reason': SHORT})
CHECK = obj({'obligation': ID, 'status': enum('ANSWERED', 'CONDITIONAL', 'MISSING_FACT', 'NEEDS_RESEARCH', 'NEEDS_REWRITE'),
    'claims': {**arr(ID, 0, 32), 'uniqueItems': True}, 'reason': SHORT, 'actions': arr(base.v3.TOOL, 0, 8)})
DEFINITIONS = deepcopy(base.DEFINITIONS)
DEFINITIONS['TurnDecision']['properties']['question_plan'] = {'anyOf': [PLAN, {'type': 'null'}]}
DEFINITIONS['TurnDecision']['required'].append('question_plan')
p = DEFINITIONS['Draft']['properties']['paragraphs']['items']
p['properties']['obligation_refs'] = {**arr(ID, 1, 8), 'uniqueItems': True}
p['required'].append('obligation_refs')
DEFINITIONS['ReviewDecision']['properties']['obligation_checks'] = arr(CHECK, 1, 8)
DEFINITIONS['ReviewDecision']['required'].append('obligation_checks')
SCHEMA = {'$schema': 'https://json-schema.org/draft/2020-12/schema', '$id': 'urn:8-agent:question-obligations-v1', '$defs': DEFINITIONS}
def schema(name): return deepcopy(DEFINITIONS[name])
def validate(name, value):
    try: Draft202012Validator(DEFINITIONS[name]).validate(value)
    except ValidationError as exc:
        raise ProposalError(f'{name} at /{"/".join(map(str, exc.absolute_path))}: {exc.message}') from exc
    meaningful(value)
    return value
def validate_wire(name, value):
    if name == 'TurnDecision':
        # Preserve parent's independent source/action validation and repair.
        envelope = schema(name)
        for key in ('actions', 'assessments', 'relation_assessments'): envelope['properties'][key]['items'] = {}
        envelope['properties']['source_selection'] = {'type': ['object', 'null']}
        try: Draft202012Validator(envelope).validate(value)
        except ValidationError as exc: raise ProposalError('TurnDecision: '+exc.message) from exc
        meaningful(value)
        # Reject this cross-field conflict inside the gateway's same-view
        # correction loop, before apply_turn or any source/tool mutation.
        # JSON alone can be valid while the requested execution is impossible.
        if value['intent'] != 'CONTINUE' and value['actions']:
            raise ProposalError(
                'observe action results before DRAFT/CLARIFY; use CONTINUE for actions. '
                'When actions is non-empty, set intent=CONTINUE and inspect their results '
                'in the next turn. To DRAFT or CLARIFY now, return actions=[] instead. '
                'Return the corrected complete object using the same question and view.')
        return value
    if name == 'SourceSelectionDecision':
        meaningful(value)
        return base.validate_wire(name, value)
    return validate(name, value)


def meaningful(value):
    """Provider regex dialects must not determine sentence length or whitespace rules."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ('requirement', 'reason', 'change_reason', 'expected_information', 'missing_fact') and item is not None:
                if not isinstance(item, str) or len(''.join(item.split())) < 4:
                    raise ProposalError(key + ': explain in at least four non-whitespace characters; a label is not a reason')
            if key == 'given_facts' and any(len(''.join(x.split())) < 2 for x in item):
                raise ProposalError('given_facts must describe facts, not one-character labels')
            meaningful(item)
    elif isinstance(value, list):
        for item in value: meaningful(item)

# A source-to-draft comparison is mandatory per reviewed source. These are
# model observations, never server-certified legal interpretations.
DIMENSIONS = ('concept', 'scope', 'conditions', 'exceptions', 'certainty', 'question_fit')
SOURCE_CHECK = obj({'source': ID, 'quote': {'type':'string','minLength':2},
    'draft_quote': {'type':'string','minLength':2},
    'dimensions': obj({key:enum('PRESERVED','NOT_APPLICABLE','CHANGED','UNCERTAIN') for key in DIMENSIONS}),
    'reason': SHORT})
review_check = DEFINITIONS['ReviewDecision']['properties']['checks']['items']
review_check['properties']['source_checks'] = arr(SOURCE_CHECK, 1, 32)
review_check['required'].append('source_checks')


def _sentence_bounds(node):
    if isinstance(node, dict):
        for key, child in node.get('properties', {}).items():
            if key in ('reason', 'requirement', 'change_reason', 'expected_information', 'relevance_reason') and child.get('type') == 'string':
                bounded = deepcopy(child)
                bounded['minLength'] = max(4, child.get('minLength', 0))
                bounded.pop('pattern', None)
                node['properties'][key] = bounded
        for child in node.values(): _sentence_bounds(child)
    elif isinstance(node, list):
        for child in node: _sentence_bounds(child)

# Detach newly inserted tool schemas as well as inherited shared leaf dictionaries.
DEFINITIONS = deepcopy(DEFINITIONS)
SCHEMA['$defs'] = DEFINITIONS
_sentence_bounds(DEFINITIONS)
paragraph = DEFINITIONS['Draft']['properties']['paragraphs']['items']['properties']
paragraph['text'] = {**paragraph['text'], 'minLength':4}
