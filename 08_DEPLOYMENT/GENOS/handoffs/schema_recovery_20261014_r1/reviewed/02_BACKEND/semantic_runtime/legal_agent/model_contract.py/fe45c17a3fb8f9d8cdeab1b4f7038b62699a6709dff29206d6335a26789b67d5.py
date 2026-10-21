"""Shared structured model wire contract for legal reasoning and AD commands.

Only provider-incompatible grammar keywords are omitted on the wire. Callers
retain their original schemas and validate the decoded value before using it.
"""
from copy import deepcopy
import json
from .errors import ProposalError
from .output_contract import strict_json, OutputContractError, issue

REVISION = 'genos-structured-contract-20261013-r1'
INPUT_METRICS_REVISION = 'model-input-metrics-20261014-r1'


def request_metrics(request):
    """Measure the exact message strings and canonical JSON, never estimate tokens.

    The provider's chat template/tokenizer and context limit are not available
    here. Canonical JSON bytes are a reproducible payload measure, not HTTP wire
    bytes or the model's tokenized prompt (which may also include the schema).
    """
    request = request if isinstance(request, dict) else {}
    messages = request.get('messages')
    messages = messages if isinstance(messages, list) else []
    contents = [(row.get('role'), row.get('content')) for row in messages if isinstance(row, dict)]
    strings = [value for _, value in contents if isinstance(value, str)]
    encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False)
    schema = encode(request.get('response_format', {}))
    return {'input_metrics_revision': INPUT_METRICS_REVISION,
        'request_size_basis': 'canonical_json',
        'request_bytes': len(encode(request).encode('utf-8')),
        'input_message_count': len(messages),
        'input_content_chars': sum(map(len, strings)),
        'input_content_utf8_bytes': sum(len(s.encode('utf-8')) for s in strings),
        'input_system_chars': sum(len(s) for role, s in contents if role == 'system' and isinstance(s, str)),
        'input_user_chars': sum(len(s) for role, s in contents if role == 'user' and isinstance(s, str)),
        'input_nontext_messages': sum(not isinstance(s, str) for _, s in contents),
        'input_messages_json_bytes': len(encode(messages).encode('utf-8')),
        'response_format_chars': len(schema),
        'response_format_utf8_bytes': len(schema.encode('utf-8')),
        'context_limit_known': False}


def response_length_metrics(request, body):
    """Observe output-cap contact without claiming an unknown context overflow."""
    request = request if isinstance(request, dict) else {}
    body = body if isinstance(body, dict) else {}
    usage = body.get('usage')
    usage = usage if isinstance(usage, dict) else {}
    count = lambda value: value if type(value) is int and value >= 0 else None
    maximum = count(request.get('max_tokens'))
    prompt, completion = count(usage.get('prompt_tokens')), count(usage.get('completion_tokens'))
    choices = body.get('choices')
    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    finish = choice.get('finish_reason')
    reached = completion >= maximum if completion is not None and maximum else None
    diagnosis = ('output_cap_reached' if reached else 'length_stop_cause_unknown') if finish == 'length' else (
        'content_filter' if finish == 'content_filter' else 'no_length_stop' if finish in ('stop', 'tool_calls', 'function_call') else 'unknown')
    return {'max_tokens': maximum, 'prompt_tokens': prompt, 'completion_tokens': completion,
        'total_tokens': count(usage.get('total_tokens')),
        'prompt_plus_max_tokens': prompt + maximum if prompt is not None and maximum is not None else None,
        'output_cap_reached': reached, 'length_diagnosis': diagnosis,
        'context_limit_known': False}


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
    if require_complete and choice.get('finish_reason') in ('length', 'content_filter', 'refusal'):
        reason = choice['finish_reason']
        can_repair = reason == 'length'
        raise OutputContractError('model response did not complete normally: '+reason,
            [issue('OUTPUT_'+reason.upper(), repairable=can_repair)],
            category='OUTPUT_INCOMPLETE' if can_repair else 'OUTPUT_REFUSED', repairable=can_repair)
    message = choice.get('message')
    if not isinstance(message, dict):
        raise ProposalError('expected a structured message')
    if message.get('refusal'):
        raise OutputContractError('model refused the response',
            [issue('OUTPUT_REFUSED', repairable=False)], category='OUTPUT_REFUSED', repairable=False)
    content = message.get('content')
    calls = message.get('tool_calls')
    if not content and isinstance(calls, list) and len(calls) == 1:
        function = calls[0].get('function') if isinstance(calls[0], dict) else None
        content = function.get('arguments') if isinstance(function, dict) else None
    return content


def structured_value(body, *, require_complete=True):
    content = structured_content(body, require_complete=require_complete)
    return strict_json(content)
