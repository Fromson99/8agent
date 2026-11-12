"""ADR-1503/1504 대사 item review: a row cited the other side's original and every repair repeated it,
because the wire schema offered every citation ID to both rows and the error named nothing. Each row
now chooses only its own side's citation IDs, and the canonical error names the field, side and
original. The canonical rule itself is unchanged."""
from copy import deepcopy

import pytest
from jsonschema import ValidationError, validate

from workflow.adapters import projection
from workflow.risk_team_compare_workflow import task_board


CITATIONS = {'C1': {'evidence': 'EI', 'quote': '내규 원문'}, 'C2': {'evidence': 'EE', 'quote': '외규 원문'}}
SIDES = {'internal': ['EI'], 'external': ['EE']}


def row():
    choice = {'anyOf': [{'type': 'object', 'properties': {'citation_id': {'type': 'string', 'enum': ['C1', 'C2']}},
                         'required': ['citation_id'], 'additionalProperties': False},
                        {'type': 'string', 'enum': ['C1', 'C2']}]}
    return {'type': 'object', 'properties': {'text': {'type': 'string'}, 'citations': {'type': 'array', 'items': choice}},
            'required': ['text', 'citations'], 'additionalProperties': False}


def wire():
    item = {'type': 'object', 'properties': {'field': {'enum': ['definition']}, 'internal': row(), 'external': row()},
            'required': ['field', 'internal', 'external'], 'additionalProperties': False}
    flat = {'type': 'object', 'properties': {'field': {'enum': ['definition']}, 'side': {'enum': ['internal', 'external']},
            **deepcopy(row()['properties'])}, 'required': ['field', 'side', 'text', 'citations'], 'additionalProperties': False}
    return {'type': 'object', 'properties': {'items': {'type': 'array', 'items': {'anyOf': [flat, item]}}}, 'required': ['items']}


def test_each_side_offers_only_its_own_citations():
    schema = projection.side_citations(wire(), CITATIONS, SIDES)
    ok = {'items': [{'field': 'definition', 'internal': {'text': 'a', 'citations': ['C1']}, 'external': {'text': 'b', 'citations': [{'citation_id': 'C2'}]}},
                    {'field': 'definition', 'side': 'external', 'text': 'b', 'citations': ['C2']}]}
    validate(ok, schema)
    for bad in ({'field': 'definition', 'internal': {'text': 'a', 'citations': ['C2']}, 'external': {'text': 'b', 'citations': []}},
                {'field': 'definition', 'side': 'internal', 'text': 'a', 'citations': [{'citation_id': 'C2'}]}):
        with pytest.raises(ValidationError):
            validate({'items': [bad]}, schema)


def test_a_side_without_originals_offers_no_citation():
    schema = projection.side_citations(wire(), CITATIONS, {'internal': ['EI', 'EE'], 'external': []})
    validate({'items': [{'field': 'definition', 'internal': {'text': 'a', 'citations': ['C2']}, 'external': {'text': '미확보', 'citations': []}}]}, schema)
    with pytest.raises(ValidationError):
        validate({'items': [{'field': 'definition', 'internal': {'text': 'a', 'citations': []}, 'external': {'text': 'b', 'citations': ['C2']}}]}, schema)


def test_canonical_error_names_field_side_and_original():
    def original(ident, side, name):
        return {'evidence_id': ident, 'side': side, 'text': name + ' 본문', 'spans': [{'text': name + ' 본문'}],
                'metadata': {'document_name': 'x > ' + name, 'heading': '제1조'}}
    sources = [original('EI', 'internal', '위험관리기준시행세칙'), original('EE', 'external', '금융투자업규정시행세칙')]
    empty = {'status': 'MISSING', 'text': '', 'citations': [], 'dependencies': [], 'scope_sufficient': False, 'missing': ''}
    value = {'items': [{'field': 'definition', 'content_status': 'UNKNOWN', 'difference': '', 'next_tasks': [],
                        'internal': {**empty, 'status': 'CONFIRMED', 'text': 'a', 'citations': [{'evidence': 'EE', 'quote': '금융투자업규정시행세칙 본문'}]},
                        'external': dict(empty)}]}
    with pytest.raises(ValueError) as caught:
        task_board.checked(value, sources, ['definition'], {})
    message = str(caught.value)
    assert message.startswith('opposite-side clues cannot prove this side')
    assert 'field definition internal' in message and '금융투자업규정시행세칙 제1조' in message
