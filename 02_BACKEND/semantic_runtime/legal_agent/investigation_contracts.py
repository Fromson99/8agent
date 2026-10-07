"""Internal issue/assessment extensions; external claim source_ids stay stable."""
from copy import deepcopy
from .corrected_memory import object_schema, array
from .errors import ContractError

GAP_KINDS = ['MISSING_SCOPE', 'UNREAD_SAVED', 'MISSING_SOURCE', 'UNRESOLVED_REFERENCE',
             'WRONG_SUBJECT', 'MISSING_FACT', 'VERSION_AMBIGUOUS']
ISSUE = object_schema({'id': {'type': 'string', 'pattern': '^Q[1-9][0-9]*$'},
    'question': {'type': 'string', 'minLength': 1},
    'subject': {'type': 'string'}, 'kind': {'type': 'string', 'enum':
        ['ACTOR','TIMING','CLASSIFICATION','STRUCTURE','FORMULA','AUTHORITY','DEFINITION','OTHER']}})


def intent_schema(base):
    out = deepcopy(base)
    out['properties']['issues'] = {**array(ISSUE), 'minItems': 1, 'maxItems': 8}
    out['required'].append('issues')
    return out


def assess_schema(base, issues, sources, *, final=False):
    out = deepcopy(base)
    ids = [i['id'] for i in issues]
    out['properties'].update(
        disposition={'type':'string','enum':['ANSWER','LIMITED_ANSWER','NEEDS_INVESTIGATION']},
        issue_assessments=array(object_schema({'issue_id':{'type':'string','enum':ids},
            'status':{'type':'string','enum':['COVERED','PARTIAL','INSUFFICIENT']},
            'reason':{'type':'string','minLength':1}})),
        gaps=array(object_schema({'issue_id':{'type':'string','enum':ids},
            'kind':{'type':'string','enum':GAP_KINDS}, 'reason':{'type':'string','minLength':1},
            'material_id':{'anyOf':[{'type':'string','enum':list(sources)},{'type':'null'}]} if sources else {'type':'null'},
            'suggested_action':{'type':'string','enum':['VIEW_SAVED_SOURCE','READ_SCOPE','FOLLOW_CONNECTION','RETURN_TO','RESEARCH','REQUEST_FACT','CHOOSE_VERSION']}})))
    out['required'] += ['disposition','issue_assessments','gaps']
    if not final:
        out['properties']['claims']['minItems'] = 0
    return out


def validate_assessment(value, issues, materials):
    expected = {i['id'] for i in issues}
    actual = [i['issue_id'] for i in value['issue_assessments']]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ContractError('assessment must cover each offered issue exactly once')
    for gap in value['gaps']:
        if gap['material_id'] is not None and gap['material_id'] not in materials:
            raise ContractError('assessment references an unknown saved original')
        if gap['kind'] == 'MISSING_FACT' and gap['suggested_action'] != 'REQUEST_FACT':
            raise ContractError('missing user facts cannot be invented by source search')
    if value['disposition'] == 'ANSWER' and (value['gaps'] or any(
            i['status'] != 'COVERED' for i in value['issue_assessments'])):
        raise ContractError('full answer requires all issues covered without outstanding gaps')
    if value['disposition'] == 'NEEDS_INVESTIGATION' and not value['gaps']:
        raise ContractError('reentry requires an explicit issue gap')
    if value['disposition'] != 'NEEDS_INVESTIGATION' and not value['claims']:
        raise ContractError('final answer still requires supported legal claims')


def claim_evidence(claim):
    return [{'source_id':claim['source_id'],'quote':claim['quote']}, *claim.get('evidence',[])]


def coverage(value):
    statuses = {r['status'] for r in value.get('issue_assessments',[])}
    return ('COVERED' if statuses == {'COVERED'} else 'INSUFFICIENT'
            if statuses == {'INSUFFICIENT'} else 'PARTIAL')
