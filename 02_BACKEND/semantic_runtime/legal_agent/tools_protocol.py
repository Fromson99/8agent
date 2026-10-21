"""Product v2 protocol. Tool schemas and dispatch names share this registry."""
from copy import deepcopy
from jsonschema import Draft202012Validator, ValidationError
from .protocol import obj, arr, enum, action, S, ID, CURSOR, DEFINITIONS as V1
from .errors import ProposalError

REGISTRY = {
    'browse': {'target': ID, 'relation': enum('self', 'parent', 'document', 'root'),
               'view': enum('children', 'outline', 'tree', 'neighbors'),
               'depth': {'type': 'integer', 'minimum': 1, 'maximum': 4}, 'cursor': CURSOR},
    'search': {'query': S, 'target': ID, 'mode': enum('fulltext', 'literal', 'title'), 'cursor': CURSOR},
    'match_terms': {'text': S, 'target': ID, 'strategy': enum('auto', 'direct', 'bridge'), 'cursor': CURSOR},
    'term_occurrences': {'terms': {**arr(ID, 1, 16), 'uniqueItems': True}, 'target': ID,
                         'match': enum('any', 'all'), 'cursor': CURSOR},
    'locate': {'locator': S, 'target': ID, 'branch': enum('body', 'addendum', 'annex', 'any'), 'cursor': CURSOR},
    'lookup_definition': {'query': S, 'target': ID, 'cursor': CURSOR},
    'follow_reference': {'evidence': ID, 'direction': enum('outgoing', 'incoming', 'both'), 'cursor': CURSOR},
    'read': {'target': ID, 'extent': enum('exact', 'subtree', 'article'), 'cursor': CURSOR},
    'inspect': {'section': enum('history', 'evidence', 'candidates', 'questions', 'challenges', 'budget'), 'cursor': CURSOR},
}
TOOL = {'oneOf': [action(name, fields) for name, fields in REGISTRY.items()]}
IDS = {**arr(ID), 'uniqueItems': True}
DEFINITIONS = {
    'ToolAction': TOOL,
    'TurnDecision': obj({
        'actions': arr(TOOL, 0, 8),
        'assessments': arr(obj({'evidence': ID, 'summary': S, 'disposition': enum('ADOPT', 'REJECT', 'DEFER'),
                               'role': enum('SUPPORT', 'CHALLENGE', 'CONTEXT'), 'reason': S, 'question_refs': IDS})),
        'candidate_decisions': arr(obj({'candidate': ID, 'decision': enum('PARK', 'REOPEN'), 'reason': S})),
        'route_decisions': arr(obj({'route': ID, 'decision': enum('REJECT', 'RESTORE', 'DEFER'), 'reason': S})),
        'question_updates': arr(obj({'question_refs': {**IDS, 'minItems': 1}, 'interpretation': S,
                                    'missing_fact': {'type': ['string', 'null']}, 'reason': S})),
        'intent': enum('CONTINUE', 'DRAFT', 'CLARIFY', 'STOP_PARTIAL'), 'reason': S}),
    'Draft': obj({'paragraphs': arr(obj({'text': S, 'evidence': {**IDS, 'minItems': 1},
                                        'question_refs': {**IDS, 'minItems': 1}, 'fact_dependencies': arr(S)}), 0, 32),
                  'limitations': arr(S)}),
    'ReviewDecision': obj({'checks': arr(obj({'claim': ID,
        'verdict': enum('SUPPORTED', 'NEEDS_RESEARCH', 'NEEDS_REWRITE', 'UNCERTAIN'),
        'evidence': IDS, 'issue': S, 'reason': S, 'actions': arr(TOOL, 0, 8)})),
        'question': obj({'status': enum('RESOLVED', 'PARTIAL', 'MISSING_FACT', 'UNRESOLVED'),
                         'question_refs': IDS, 'reason': S})}),
    'Rebuttal': obj({'claim': ID, 'evidence': {**IDS, 'minItems': 1}, 'reason': S,
                     'requested_resolution': enum('REVIEW_AGAIN', 'WITHDRAW_CLAIM')}),
    'Control': deepcopy(V1['Control']),
}
DEFINITIONS['Control']['properties']['decision'] = enum('FINAL', 'RESEARCH', 'RECOMPOSE', 'REVIEW')
SCHEMA = {'$schema': 'https://json-schema.org/draft/2020-12/schema',
          '$id': 'urn:8-agent:tool-exploration-v2', '$defs': DEFINITIONS}


def schema(name):
    return deepcopy(DEFINITIONS[name])


def validate(name, value):
    try:
        Draft202012Validator(DEFINITIONS[name]).validate(value)
    except ValidationError as exc:
        raise ProposalError(f'{name}: {exc.message}') from exc
    return value
