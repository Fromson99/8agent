"""GENOS single physical transmission, with an actual total HTTP deadline."""
import asyncio
import hashlib
import json
import logging
import re
import time
import httpx
from .. import observability as obs
from ..genos import RETRY_STATUS, from_env
from .errors import ContractError, TransportError

log = obs.get_logger('legal_agent.model_http')
_ERROR_HINTS = (
    'json_schema', 'response_format', 'max_tokens', 'chat_template_kwargs',
    'enable_thinking', 'context length', 'token limit', 'rate limit',
    'authentication', 'permission', 'payload too large',
)


def _error_details(data):
    """Project diagnostic fields without printing an upstream body or source text."""
    if not isinstance(data, dict):
        return {}
    error = data.get('error')
    details = {}
    if isinstance(error, dict):
        for key in ('type', 'code', 'param'):
            value = error.get(key)
            if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,80}', value):
                details['upstream_error_' + key] = value
    validation = data.get('detail')
    if isinstance(validation, list):
        locations = []
        types = []
        for item in validation[:8]:
            if not isinstance(item, dict):
                continue
            location = item.get('loc')
            if isinstance(location, (list, tuple)) and location and all(
                isinstance(part, (str, int)) and re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', str(part))
                for part in location[:8]
            ):
                locations.append('.'.join(str(part) for part in location[:8]))
            error_type = item.get('type')
            if isinstance(error_type, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', error_type):
                types.append(error_type)
        if locations:
            details['validation_locations'] = locations
        if types:
            details['validation_error_types'] = types
    message = (error.get('message') if isinstance(error, dict) else None)
    if not isinstance(message, str):
        message = next((value for value in (data.get('message'), validation, error)
                        if isinstance(value, str)), None)
    if isinstance(message, str):
        details['upstream_message_chars'] = len(message)
        details['upstream_message_sha256'] = hashlib.sha256(message.encode()).hexdigest()
        lowered = message.casefold()
        details['upstream_error_hints'] = [hint for hint in _ERROR_HINTS if hint in lowered]
    return details


class GenosTransport:
    def __init__(self, target, binding):
        self.target, self.binding = target, dict(binding)
        if binding['provider'] != 'genos' or binding['trust_zone'] != 'internal':
            raise ContractError('GENOS transport requires explicit internal binding')
        if binding['adapter_version'] != 'genos-single-send-v1':
            raise ContractError('unsupported transport version')
        if binding['endpoint_identity'] != hashlib.sha256(target.root.encode()).hexdigest():
            raise ContractError('configured endpoint does not match the model binding')

    @classmethod
    def from_environment(cls, binding):
        target, model = from_env('llm')
        # A missing MODEL env value uses the ID pinned during profile creation.
        # validate_model still verifies it against this endpoint before inference.
        if model and model != binding['model']:
            raise ContractError('environment model does not match execution profile')
        return cls(target, binding)

    async def _request(self, method, path, body, seconds, *, attempt_id=None):
        started = time.perf_counter()
        fields = {'method': method, 'operation': path, 'attempt_id': attempt_id,
                  'endpoint_identity': self.binding['endpoint_identity'],
                  'model': self.binding['model'], 'timeout_ms': int(seconds * 1000)}
        obs.event(log, 'model_http.started', **fields)
        try:
            async with asyncio.timeout(seconds):
                async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
                                             timeout=httpx.Timeout(seconds, connect=min(self.target.connect_timeout, seconds))) as client:
                    response = await client.request(method, self.target.url(path), headers=self.target.headers, json=body)
                    try:
                        data = response.json()
                    except (ValueError, UnicodeError):
                        data = None
                    envelope = {'status_code': response.status_code, 'body_json': data,
                                'body_text': response.text if data is None else None,
                                'body_sha256': hashlib.sha256(response.content).hexdigest(),
                                'response_bytes': len(response.content)}
                    if response.status_code >= 400:
                        obs.event(log, 'model_http.failed', level=logging.ERROR, **fields,
                                  http_status=response.status_code,
                                  retryable=response.status_code in RETRY_STATUS,
                                  duration_ms=int((time.perf_counter() - started) * 1000),
                                  response_bytes=envelope['response_bytes'],
                                  response_sha256=envelope['body_sha256'],
                                  **_error_details(data))
                        raise TransportError('upstream HTTP error', retryable=response.status_code in RETRY_STATUS, response=envelope)
                    obs.event(log, 'model_http.finished', **fields,
                              http_status=response.status_code,
                              duration_ms=int((time.perf_counter() - started) * 1000),
                              response_bytes=envelope['response_bytes'])
                    return envelope
        except (TimeoutError, httpx.TimeoutException) as exc:
            obs.event(log, 'model_http.failed', level=logging.ERROR, **fields,
                      failure_kind='timeout', duration_ms=int((time.perf_counter() - started) * 1000))
            raise TransportError('model transmission timed out', retryable=True, unknown=True) from exc
        except httpx.TransportError as exc:
            obs.event(log, 'model_http.failed', level=logging.ERROR, **fields,
                      failure_kind='connection', error_type=type(exc).__name__,
                      duration_ms=int((time.perf_counter() - started) * 1000))
            raise TransportError('model connection failed', retryable=True, unknown=True) from exc

    def send_once(self, *, body, ticket):
        with asyncio.Runner() as runner:
            return runner.run(self._request('POST', '/chat/completions', body,
                                            ticket['remaining_seconds'], attempt_id=ticket.get('attempt_id')))

    async def _stream_request(self, body, ticket, on_content):
        """One HTTP send; reconstruct the canonical response and retain SSE events."""
        seconds = ticket['remaining_seconds']
        events, content, reasoning, arguments = [], [], [], []
        actual_model = None
        usage = None
        finish = None
        call_id = call_name = None
        completed = False
        pending_deltas = []
        digest = hashlib.sha256()
        size = 0
        fields = {'attempt_id': ticket.get('attempt_id'), 'model': self.binding['model'],
                  'operation': '/chat/completions', 'stream_requested': True}
        started = time.perf_counter()
        obs.event(log, 'model_http.started', **fields)
        def partial():
            return {'status_code': None, 'body_json': None, 'stream_events': events,
                    'body_sha256': digest.hexdigest(), 'response_bytes': size,
                    'stream_complete': False}
        try:
            async with asyncio.timeout(seconds):
                async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
                        timeout=httpx.Timeout(seconds, connect=min(self.target.connect_timeout, seconds))) as client:
                    async with client.stream('POST', self.target.url('/chat/completions'),
                                             headers=self.target.headers, json=body) as response:
                        if response.status_code >= 400:
                            raw = await response.aread()
                            try: data = json.loads(raw)
                            except ValueError: data = None
                            envelope = {'status_code': response.status_code, 'body_json': data,
                                        'body_sha256': hashlib.sha256(raw).hexdigest(), 'response_bytes': len(raw)}
                            raise TransportError('upstream HTTP error', retryable=response.status_code in RETRY_STATUS, response=envelope)
                        # A gateway may buffer even when stream=true. Consume that same
                        # response without retransmitting or claiming incremental delivery.
                        if 'application/json' in response.headers.get('content-type', ''):
                            raw = await response.aread()
                            data = json.loads(raw)
                            return {'status_code': response.status_code, 'body_json': data,
                                    'body_sha256': hashlib.sha256(raw).hexdigest(), 'response_bytes': len(raw)}
                        frame = []
                        async for line in response.aiter_lines():
                            size += len(line.encode()) + 1
                            digest.update((line+'\n').encode())
                            if size > 16 * 1024 * 1024:
                                raise TransportError('model stream exceeds response limit', unknown=True)
                            if line.startswith('data:'):
                                frame.append(line[5:].lstrip())
                                continue
                            if line or not frame:
                                continue
                            raw_event = '\n'.join(frame); frame = []
                            if raw_event == '[DONE]':
                                completed = True
                                break
                            event = json.loads(raw_event)
                            if not isinstance(event, dict) or event.get('error'):
                                raise TransportError('model stream returned an error', unknown=True)
                            events.append(event)
                            if event.get('model'):
                                actual_model = event['model']
                                if actual_model != self.binding['model']:
                                    raise ContractError('actual response model differs from pinned model')
                                for text in pending_deltas:
                                    on_content(text)
                                pending_deltas.clear()
                            if event.get('usage') is not None:
                                usage = event['usage']
                            for choice in event.get('choices', []):
                                if choice.get('index', 0) != 0:
                                    raise TransportError('expected one streamed choice', unknown=True)
                                delta = choice.get('delta') or {}
                                if isinstance(delta.get('reasoning_content'), str):
                                    reasoning.append(delta['reasoning_content'])
                                text = delta.get('content')
                                if isinstance(text, str):
                                    if arguments:
                                        raise TransportError('mixed model output channels', unknown=True)
                                    content.append(text)
                                    if actual_model: on_content(text)
                                    else: pending_deltas.append(text)
                                for call in delta.get('tool_calls') or []:
                                    if call.get('index', 0) != 0 or content:
                                        raise TransportError('expected one structured output channel', unknown=True)
                                    function = call.get('function') or {}
                                    call_id = call.get('id') or call_id
                                    call_name = function.get('name') or call_name
                                    text = function.get('arguments')
                                    if isinstance(text, str):
                                        arguments.append(text)
                                        if actual_model: on_content(text)
                                        else: pending_deltas.append(text)
                                if choice.get('finish_reason') is not None:
                                    finish = choice['finish_reason']
                        if not completed or finish is None:
                            raise TransportError('model stream ended before completion', unknown=True)
                        message = {'role': 'assistant', 'content': ''.join(content)}
                        if reasoning:
                            message['reasoning_content'] = ''.join(reasoning)
                        if arguments:
                            message['tool_calls'] = [{'id': call_id, 'type': 'function',
                                'function': {'name': call_name, 'arguments': ''.join(arguments)}}]
                        data = {'model': actual_model, 'usage': usage,
                                'choices': [{'index': 0, 'message': message, 'finish_reason': finish}]}
                        obs.event(log, 'model_http.finished', **fields,
                                  duration_ms=int((time.perf_counter()-started)*1000), response_bytes=size)
                        return {'status_code': response.status_code, 'body_json': data,
                                'body_sha256': digest.hexdigest(), 'response_bytes': size,
                                'stream_events': events}
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise TransportError('model transmission timed out', retryable=True, unknown=True, response=partial()) from exc
        except httpx.TransportError as exc:
            raise TransportError('model connection failed', retryable=True, unknown=True, response=partial()) from exc
        except TransportError as exc:
            if exc.response is None:
                exc.response = partial()
            raise
        except (ValueError, KeyError, TypeError) as exc:
            raise TransportError('invalid model stream', unknown=True, response=partial()) from exc

    def send_stream_once(self, *, body, ticket, on_content):
        with asyncio.Runner() as runner:
            return runner.run(self._stream_request(body, ticket, on_content))

    def validate_model(self):
        # Startup diagnostic only. Never discover or switch models during a query.
        with asyncio.Runner() as runner:
            response = runner.run(self._request('GET', '/models', None, self.target.read_timeout))
        ids = {r['id'] for r in (response['body_json'] or {}).get('data', []) if isinstance(r, dict) and 'id' in r}
        if self.binding['model'] not in ids:
            raise ContractError('configured model was not advertised by the selected endpoint')
        return {'model': self.binding['model'], 'endpoint_identity': self.binding['endpoint_identity'], 'verified': True}
