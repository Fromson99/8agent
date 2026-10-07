"""GENOS grammar compatibility without weakening local proposal validation."""
import json

from jsonschema import Draft202012Validator

from semantic_runtime.legal_agent import obligation_protocol
from semantic_runtime.legal_agent.bounded_source_session import _Gateway, _Protocol
from semantic_runtime.legal_agent.gateway import ModelGateway


class _Context:
    binding = {'export_allowed': False}


class _Transport:
    binding = {'provider': 'genos', 'trust_zone': 'internal', 'model': 'synthetic'}


def _gateway(cls=ModelGateway, *, numbered=False, schema=None):
    profile = {'model_binding': _Transport.binding, 'max_output_tokens': 6400,
               'numbered_references_enabled': numbered}
    return cls(None, _Context(), profile, {}, _Transport(),
               message_protocol=_Protocol(schema) if schema is not None else obligation_protocol,
               system='synthetic system', prompts={'investigate': 'synthetic prompt'})


def test_turn_decision_wire_schema_omits_unique_items_with_and_without_numbers():
    assert 'uniqueItems' in json.dumps(obligation_protocol.schema('TurnDecision'))
    for numbered in (False, True):
        request = _gateway(numbered=numbered).request(
            'investigate', {'question_pieces': [{'id': 'Q1'}]}, 'TurnDecision')
        assert 'uniqueItems' not in json.dumps(request)
        assert request['response_format']['json_schema']['name'] == 'TurnDecision'
    assert not Draft202012Validator(obligation_protocol.REFS).is_valid(['Q1', 'Q1'])


def test_bounded_question_plan_wire_schema_omits_unique_items():
    schema = obligation_protocol.schema('TurnDecision')['properties']['question_plan']['anyOf'][0]
    request = _gateway(_Gateway, schema=schema).request('investigate', {}, 'BoundedSourceDecision')
    assert 'uniqueItems' not in json.dumps(request)
    assert 'uniqueItems' in json.dumps(schema)


def _search_modes(schema):
    found = []
    def visit(node):
        if isinstance(node, list):
            for child in node: visit(child)
        elif isinstance(node, dict):
            properties = node.get('properties') or {}
            if properties.get('tool', {}).get('const') == 'search':
                found.append(properties['args']['properties']['mode']['enum'])
            for child in node.values(): visit(child)
    visit(schema)
    return found


def test_wire_schema_excludes_unavailable_fulltext_search_without_changing_protocol():
    for numbered in (False, True):
        gateway = _gateway(numbered=numbered)
        view = {'question_pieces': [{'id': 'Q1'}], 'corpus_root': 'R1',
                'tool_capabilities': {'search': True, 'fulltext': False}}
        request = gateway.request('investigate', view, 'TurnDecision')
        modes = _search_modes(request['response_format']['json_schema']['schema'])
        assert modes and all(mode == ['literal', 'title'] for mode in modes)
        view['tool_capabilities']['fulltext'] = True
        request = gateway.request('investigate', view, 'TurnDecision')
        assert all('fulltext' in mode for mode in _search_modes(request['response_format']['json_schema']['schema']))
    assert all('fulltext' in mode for mode in _search_modes(obligation_protocol.schema('TurnDecision')))
