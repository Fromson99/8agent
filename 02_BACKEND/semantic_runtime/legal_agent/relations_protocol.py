"""Closed v3 model protocol, kept separate from the v2 replay contract."""
from copy import deepcopy
from . import tools_protocol as v2
from .protocol import obj, arr, enum, action, S, ID, CURSOR
from .errors import ProposalError
from jsonschema import Draft202012Validator, ValidationError

IDS = deepcopy(v2.IDS)
SPAN = obj({'evidence': ID, 'block_id': ID,
    'start_cp': {'type': 'integer', 'minimum': 0}, 'end_cp': {'type': 'integer', 'minimum': 1}})
FAMILIES = ('all', 'reference', 'definition', 'term', 'occurrence', 'structure', 'knowledge')
REGISTRY = deepcopy(v2.REGISTRY)
REGISTRY['follow_relations'] = {'target': ID, 'family': enum(*FAMILIES), 'cursor': CURSOR}
VIEW_SECTIONS = ('exact_evidence', 'relation_menu', 'relation_notices', 'last_action_results',
                 'relation_assessments', 'assessments', 'questions', 'coverage')
REGISTRY['view_page'] = {'section': enum(*VIEW_SECTIONS), 'cursor': S}
REGISTRY['inspect_relation'] = {'relation_id': ID}
REGISTRY['read']['target'] = {**ID, 'description':
    'Existing D/P/U location or E evidence handle. R is a corpus and F a folder: first locate or search within it, then read a returned target.'}
REGISTRY['inspect']['section'] = enum('history', 'evidence', 'candidates', 'questions', 'challenges',
                                     'budget', 'relations', 'assessments', 'actions', 'coverage')

def tool_schema(name, fields):
    base = action(name, fields)
    base['properties'].update(question_refs=IDS, expected_information=S)
    base['required'] += ['question_refs', 'expected_information']
    return base

TOOL = {'oneOf': [tool_schema(name, fields) for name, fields in REGISTRY.items()]}
ASSESSMENT = obj({'evidence': ID, 'summary': S, 'disposition': enum('ADOPT', 'REJECT', 'DEFER'),
    'role': enum('SUPPORT', 'CHALLENGE', 'CONTEXT'), 'reason': S, 'question_ref': ID,
    'basis_spans': arr(SPAN, 1, 24), 'related_relation_ids': IDS})
RELATION_ASSESSMENT = obj({'relation_id': ID, 'question_ref': ID,
    'decision': enum('RELEVANT', 'NOT_RELEVANT', 'DEFER'), 'reason': S,
    'source_evidence': IDS, 'target_evidence': IDS, 'basis_spans': arr(SPAN, 0, 32),
    'reason_basis': enum('SOURCE_ONLY', 'SOURCE_AND_TARGET', 'UNRESOLVED'),
    'scope_note': S, 'substitution_note': S, 'exception_note': S})
DEFINITIONS = deepcopy(v2.DEFINITIONS)
DEFINITIONS['ToolAction'] = TOOL
turn = DEFINITIONS['TurnDecision']['properties']
turn['actions'] = arr(TOOL, 0, 8)
turn['assessments'] = arr(ASSESSMENT)
turn['relation_assessments'] = arr(RELATION_ASSESSMENT)
DEFINITIONS['TurnDecision']['required'].append('relation_assessments')
p = DEFINITIONS['Draft']['properties']['paragraphs']['items']
p['properties']['relation_dependencies'] = IDS
p['required'].append('relation_dependencies')
c = DEFINITIONS['ReviewDecision']['properties']['checks']['items']
c['properties'].update(actions=arr(TOOL, 0, 8), relation_checks=IDS)
c['required'].append('relation_checks')
DEFINITIONS['AuditSummary'] = obj({
    'schema_version': enum('tool-exploration-v3'),
    'action_summary': arr({'type':'object'}), 'evidence_decisions': arr({'type':'object'}),
    'relation_checks': arr({'type':'object'}), 'outstanding_checks': arr({'type':'object'}),
    'assessment_history': arr({'type':'object'}), 'display_lines': arr(S),
    'totals': obj({k:{'type':'integer','minimum':0} for k in ('actions','evidence','relations','outstanding','assessment_versions')}),
    'truncated': {'type':'boolean'},
    'audit': obj({'run_id':ID,'revision':{'type':'integer','minimum':0},'hash':S,'complete':{'type':'boolean'}})})
SCHEMA = {'$schema': 'https://json-schema.org/draft/2020-12/schema',
    '$id': 'urn:8-agent:tool-exploration-v3', '$defs': DEFINITIONS}


def schema(name):
    return deepcopy(DEFINITIONS[name])


def validate(name, value):
    try:
        Draft202012Validator(DEFINITIONS[name]).validate(value)
    except ValidationError as exc:
        raise ProposalError(f'{name}: {exc.message}') from exc
    def nonblank(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if k in ('reason', 'summary', 'expected_information', 'scope_note', 'substitution_note', 'exception_note') and not x.strip():
                    raise ProposalError(k+' must not be blank')
                nonblank(x)
        elif isinstance(v, list):
            for x in v: nonblank(x)
    nonblank(value)
    return value
