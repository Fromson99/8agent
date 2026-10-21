"""Closed model message schemas. Cross-state checks live in WorkRepository."""
from copy import deepcopy
from jsonschema import Draft202012Validator, ValidationError
from .errors import ProposalError

URI = 'urn:8-agent:legal-agent-v1'


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def arr(items, minimum=0, maximum=64):
    return {'type': 'array', 'items': items, 'minItems': minimum, 'maxItems': maximum}


def enum(*items):
    return {'type': 'string', 'enum': list(items)}


S = {'type': 'string', 'minLength': 1}
ID = {'type': 'string', 'minLength': 1}
IDS = {**arr(ID), 'uniqueItems': True}
POS = {'type': 'integer', 'minimum': 1}
ISSUE = obj({'text': S, 'question_piece_ids': {**IDS, 'minItems': 1},
             'required': {'type': 'boolean'}, 'origin': enum('question', 'source_trigger'), 'evidence_ids': IDS})


def op(name, fields):
    return obj({'op': {'const': name}, **fields})


def action(name, fields):
    return obj({'tool': {'const': name}, 'args': obj(fields), 'reason': S})


CURSOR = {'type': ['string', 'null']}
TOOLS = [
    action('list_documents', {'query': {'type': 'string'}, 'cursor': CURSOR}),
    action('list_structure', {'document': ID, 'cursor': CURSOR}),
    action('read_node', {'node': ID, 'cursor': CURSOR}),
    action('search_text', {'query': S, 'document': {'type': ['string', 'null']}, 'cursor': CURSOR}),
    action('search_subtree', {'query': S, 'node': ID, 'cursor': CURSOR}),
    action('locate_provision', {'document': ID, 'coordinate': S, 'cursor': CURSOR}),
    action('lookup_definition', {'query': S, 'cursor': CURSOR}),
    action('follow_reference', {'evidence_id': ID, 'direction': enum('outgoing', 'incoming'), 'cursor': CURSOR}),
    action('inspect_work', {}),
]
TOOL = {'oneOf': TOOLS}
TARGET = {'issue_id': ID, 'expected_version': POS}
UPDATES = [
    op('create_issue', {'temp_id': ID, 'issue': ISSUE}),
    op('revise_issue', {**TARGET, 'issue': ISSUE, 'reason': S}),
    op('split_issue', {**TARGET, 'replacements': arr(obj({'temp_id': ID, 'issue': ISSUE}), 2, 8), 'reason': S}),
    op('merge_issue', {'targets': arr(obj(TARGET), 2, 8), 'temp_id': ID, 'issue': ISSUE, 'reason': S}),
    op('supersede_issue', {**TARGET, 'temp_id': ID, 'issue': ISSUE, 'reason': S}),
    op('assess', {'temp_id': ID, 'issue_id': ID, 'evidence_ids': {**IDS, 'minItems': 1},
                  'relation': enum('supports', 'qualifies', 'contradicts', 'irrelevant'), 'reason': S}),
    op('retract_assessment', {'assessment_id': ID, 'expected_version': POS, 'reason': S}),
    op('propose_finding', {'temp_id': ID, 'issue_id': ID, 'assessment_ids': {**IDS, 'minItems': 1},
                         'fact_ids': IDS, 'text': S, 'applicability': enum('source_only', 'conditional', 'current')}),
    op('attach_fact', {'temp_id': ID, 'issue_id': ID, 'name': S, 'status': enum('stated', 'unknown'),
                      'question_piece_ids': IDS}),
    op('mark_unresolved', {**TARGET, 'observation_ids': {**IDS, 'minItems': 1}, 'reason': S}),
    op('mark_not_applicable', {**TARGET, 'finding_ids': {**IDS, 'minItems': 1}, 'reason': S}),
]
DEFINITIONS = {
    'ToolAction': TOOL,
    'InvestigateDecision': obj({'updates': arr({'oneOf': UPDATES}), 'reads': arr(TOOL, 0, 8),
                               'intent': enum('CONTINUE', 'DRAFT'), 'reason': S}),
    'Draft': obj({'paragraphs': arr(obj({'text': S, 'finding_ids': {**IDS, 'minItems': 1},
                                       'evidence_ids': {**IDS, 'minItems': 1}})), 'limitations': arr(S)}),
    'Review': obj({
        'claims': arr(obj({'claim_id': ID, 'claim_version': POS,
                          'verdict': enum('SUPPORTED', 'NEEDS_RESEARCH', 'NEEDS_REWRITE', 'UNCERTAIN'),
                          'reason': S, 'evidence_ids': IDS, 'follow_up_reads': arr(TOOL, 0, 8)})),
        'question_checks': arr(obj({'question_piece_id': ID, 'claim_ids': IDS,
                                   'status': enum('RESOLVED', 'UNRESOLVED', 'MISSING'), 'reason': S,
                                   'follow_up_reads': arr(TOOL, 0, 8)}), 1),
        'whole_question': obj({'status': enum('RESOLVED', 'UNRESOLVED', 'MISSING'), 'reason': S,
                              'follow_up_reads': arr(TOOL, 0, 8)}),
    }),
    'Control': obj({'decision': enum('FINAL', 'RESEARCH', 'RECOMPOSE'),
                    'gate': enum('READY', 'BOUNDED', 'CLARIFY'), 'reason': S,
                    'state_revision': {'type': 'integer', 'minimum': 0},
                    'evidence_revision': {'type': 'integer', 'minimum': 0}}),
}
SCHEMA = {'$schema': 'https://json-schema.org/draft/2020-12/schema', '$id': URI, '$defs': DEFINITIONS}


def schema(name):
    return deepcopy(DEFINITIONS[name])


def validate(name, value):
    try:
        Draft202012Validator(DEFINITIONS[name]).validate(value)
    except ValidationError as exc:
        raise ProposalError(f'{name}: {exc.message}') from exc
    return value
