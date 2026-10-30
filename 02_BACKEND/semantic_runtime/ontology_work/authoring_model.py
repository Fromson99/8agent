"""Single-attempt GENOS authoring transport with the shared absolute deadline."""
import json
import time
from ..legal_agent.errors import ContractError


class AuthoringFailure(ContractError):
    def __init__(self, status, receipt):
        self.status, self.receipt = status, receipt
        super().__init__(status + ': see persisted provider receipt')


def generate(store, prompt, context, schema):
    from ..genos import from_env, advertised_model
    from ..provider import _structured_genos_value
    from lawrag.core.request_deadline import post_json
    target, configured = from_env('llm'); model = advertised_model(target, configured)
    seconds = context['call_budget']['absolute_deadline'] - time.time()
    request = {'model': model, 'messages': [{'role': 'system', 'content': prompt},
               {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}],
               'temperature': 0, 'stream': False, 'chat_template_kwargs': {'enable_thinking': False},
               'response_format': {'type': 'json_schema', 'json_schema': {'name': 'domain_profile', 'strict': True, 'schema': schema}}}
    from ..legal_agent.wire_schema import project_request
    request, projection = project_request(request)
    key = store.put({'request': request, 'schema_projection': projection, 'status': 'SENT_ONCE'})
    response = post_json(target.url('/chat/completions'), headers=target.headers, json_body=request,
                         deadline=time.monotonic() + min(180, seconds))
    # HTTP refusal is known; a broken connection before a response remains UNKNOWN.
    if response.status_code >= 400:
        saved = store.put({'request_hash': key, 'http_status': response.status_code,
                           'response_text': response.text, 'status': 'HTTP_REJECTED'})
        raise AuthoringFailure('HTTP_REJECTED', {'store_hash': saved, 'physical_calls': 1})
    try:
        raw = response.json()
    except ValueError:
        saved = store.put({'request_hash': key, 'response_text': response.text, 'status': 'INVALID_RESPONSE'})
        raise AuthoringFailure('INVALID_RESPONSE', {'store_hash': saved, 'physical_calls': 1})
    saved = store.put({'request_hash': key, 'response': raw, 'status': 'RESPONSE_RECEIVED'})
    receipt = {'store_hash': saved, 'requested_model': model, 'physical_calls': 1,
               'schema_projection': projection,
               'usage': raw.get('usage') if isinstance(raw, dict) else None}
    if isinstance(raw, dict) and raw.get('error'):
        raise AuthoringFailure('INCOMPLETE_RESPONSE', receipt)
    choices = raw.get('choices') if isinstance(raw, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise AuthoringFailure('INVALID_RESPONSE', receipt)
    choice = choices[0]
    # A provider can report an error inside HTTP200, even with JSON-looking text.
    # Preserve the response and stop before the workflow's semantic repair path.
    receipt['finish_reason'] = choice.get('finish_reason')
    if choice.get('error') or choice.get('finish_reason') not in (None, 'stop'):
        raise AuthoringFailure('INCOMPLETE_RESPONSE', receipt)
    message = choice.get('message') or {}
    if not isinstance(message, dict):
        raise AuthoringFailure('INVALID_RESPONSE', receipt)
    if message.get('refusal'):
        raise AuthoringFailure('INCOMPLETE_RESPONSE', receipt)
    if isinstance(message.get('content'), str) and message['content'].strip():
        try:
            return json.loads(message['content']), receipt
        except json.JSONDecodeError:
            # Schema validation owns the single repair. Retain the exact original.
            return {'invalid_json_text': message['content']}, receipt
    try:
        return _structured_genos_value(raw), receipt
    except Exception as exc:
        raise AuthoringFailure('INVALID_RESPONSE', receipt) from exc
