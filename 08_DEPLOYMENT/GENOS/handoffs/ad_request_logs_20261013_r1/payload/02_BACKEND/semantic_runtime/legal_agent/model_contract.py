"""Shared structured model wire contract for legal reasoning and AD commands.

Only provider-incompatible grammar keywords are omitted on the wire. Callers
retain their original schemas and validate the decoded value before using it.
"""
from copy import deepcopy
import json
from .errors import ProposalError

REVISION = 'genos-structured-contract-20261013-r1'


def genos_wire_schema(value):
    if not isinstance(value, dict):
        return deepcopy(value)
    result = {}
    maps = {'properties', 'patternProperties', '$defs', 'definitions', 'dependentSchemas'}
    single = {'items', 'additionalItems', 'contains', 'additionalProperties',
              'unevaluatedProperties', 'unevaluatedItems', 'propertyNames', 'not', 'if', 'then', 'else'}
    for key, child in value.items():
        if key == 'uniqueItems':
            continue
        if key in maps and isinstance(child, dict):
            result[key] = {name: genos_wire_schema(schema) for name, schema in child.items()}
        elif key in single:
            result[key] = ([genos_wire_schema(schema) for schema in child]
                           if isinstance(child, list) else genos_wire_schema(child))
        elif key in {'anyOf', 'oneOf', 'allOf', 'prefixItems'} and isinstance(child, list):
            result[key] = [genos_wire_schema(schema) for schema in child]
        else:
            result[key] = deepcopy(child)
    return result


def structured_request(*, model, max_tokens, messages, schema_name, schema):
    return {'model': model, 'max_tokens': max_tokens, 'temperature': 0,
            'stream': False, 'chat_template_kwargs': {'enable_thinking': False},
            'messages': messages,
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': schema_name, 'strict': True, 'schema': genos_wire_schema(schema)}}}


def structured_content(body, *, require_complete=True):
    if (not isinstance(body, dict) or not isinstance(body.get('choices'), list)
            or len(body['choices']) != 1 or not isinstance(body['choices'][0], dict)):
        raise ProposalError('expected one structured choice')
    choice = body['choices'][0]
    if require_complete and choice.get('finish_reason') in ('length', 'content_filter'):
        raise ProposalError('model response did not complete normally')
    message = choice.get('message')
    if not isinstance(message, dict):
        raise ProposalError('expected a structured message')
    content = message.get('content')
    calls = message.get('tool_calls')
    if not content and isinstance(calls, list) and len(calls) == 1:
        function = calls[0].get('function') if isinstance(calls[0], dict) else None
        content = function.get('arguments') if isinstance(function, dict) else None
    return content


def structured_value(body, *, require_complete=True):
    content = structured_content(body, require_complete=require_complete)
    return json.loads(content) if isinstance(content, str) else content
