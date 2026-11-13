"""Experiment-only provider fallback for Qwen3.8 (user 2026-11-12: "공급자의 문제처럼 답이 없다거나 하면 공급자
다르게해서 질문날리게해 … 4~5개 정도 선정해놔서 문제 생기면 교체").

The same request (same model, messages, schema, reasoning none, no output cap) goes to the next pre-checked provider
when the current one gives no usable answer: any non-200 HTTP status, a transport error, a stream error chunk, no
non-blank content within the first limit, only blank content (runaway newlines) for the stall limit, the attempt time
running out, a finish other than stop, an empty answer, reasoning output, or a provider/model echo that differs.
A complete answer is returned as is, even if its JSON does not fit the schema: that is model output and goes to the
product's own repair path, not to another provider.

Requests are streamed so a runaway can be seen: in ADR-1512 Reka and Parasail answered one stored request with
'{"choice": "FOLLOW", ...' and then only newlines for 180 s, which a non-streamed call shows as silence.
All attempts share the product's per-call deadline (ticket), every attempt is one physical call against the client's
call budget, and an abandoned attempt may still finish and be billed remotely (user accepted). Product code (GENOS,
local MAIN) keeps its own rule; this module is used only by experiment runners that load the fallback policy.
"""
import copy
import gzip
import hashlib
import json
import time
from pathlib import Path

import httpx

SCHEMA_VERSION = 'qwen38-provider-fallback-v1'
URL = 'https://openrouter.ai/api/v1/chat/completions'
SWITCH_KINDS = ('HTTP_STATUS', 'TRANSPORT', 'STREAM_ERROR', 'NO_NONBLANK', 'BLANK_STALL', 'ATTEMPT_DEADLINE',
                'FINISH_NOT_STOP', 'EMPTY_ANSWER', 'REASONING_OUTPUT', 'ECHO_MISMATCH')


def load_policy(path):
    raw = Path(path).read_bytes()
    cfg = json.loads(raw)
    providers = cfg.get('providers') or []
    ok = (cfg.get('schema_version') == SCHEMA_VERSION and cfg.get('model') == 'qwen/qwen3.8-27b'
          and 2 <= len(providers) <= 6
          and all(isinstance(p, dict) and set(p) == {'tag', 'name'} and p['tag'] and p['name'] for p in providers)
          and len({p['tag'] for p in providers}) == len(providers)
          and cfg.get('reasoning') == {'effort': 'none'} and cfg.get('model_fallback') is False
          and cfg.get('output_cap') is None and cfg.get('stream') is True
          and all(isinstance(cfg.get(k), (int, float)) and cfg[k] > 0 for k in
                  ('per_call_seconds', 'first_nonblank_seconds', 'nonblank_stall_seconds', 'min_attempt_seconds'))
          and (cfg.get('authorization') or {}).get('source') == 'user_message'
          and str((cfg.get('authorization') or {}).get('text', '')).strip())
    if not ok:
        raise ValueError('Invalid experiment provider fallback policy')
    return cfg, hashlib.sha256(raw).hexdigest()


def route(provider):
    tag = provider['tag']
    return {'only': [tag], 'order': [tag], **({'quantizations': [tag.rsplit('/', 1)[1]]} if '/' in tag else {}),
            'allow_fallbacks': False, 'require_parameters': True}


def stream_attempt(payload, *, key, provider, model, seconds, first_nonblank, stall, transport=None):
    """One physical streamed request. Returns (envelope or None, failure kind or None, diagnostics, raw lines)."""
    begin = time.monotonic()
    lines = []
    parts = []
    first = first_text = last_text = None
    finish = usage = echo_provider = echo_model = None
    reasoning = 0
    status = None
    kind = None
    detail = None
    try:
        timeout = httpx.Timeout(connect=min(20, seconds), read=min(30, seconds), write=60, pool=20)
        with httpx.Client(timeout=timeout, transport=transport) as client:
            with client.stream('POST', URL, json=payload,
                               headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}) as r:
                status = r.status_code
                if status != 200:
                    body = r.read()
                    detail = body.decode('utf-8', 'replace')[:500]
                    kind = 'HTTP_STATUS'
                else:
                    for line in r.iter_lines():
                        now = time.monotonic() - begin
                        lines.append([round(now, 3), line])
                        if now > seconds:
                            kind = 'ATTEMPT_DEADLINE'
                            break
                        if first_text is None and now > first_nonblank:
                            kind = 'NO_NONBLANK'
                            break
                        if first_text is not None and now - last_text > stall:
                            kind = 'BLANK_STALL'
                            break
                        if not line.startswith('data:'):
                            continue
                        data = line[5:].strip()
                        if data == '[DONE]':
                            break
                        try:
                            obj = json.loads(data)
                        except ValueError:
                            continue
                        if 'error' in obj:
                            kind = 'STREAM_ERROR'
                            detail = json.dumps(obj['error'], ensure_ascii=False)[:500]
                            break
                        echo_provider = obj.get('provider', echo_provider)
                        echo_model = obj.get('model', echo_model)
                        if obj.get('usage'):
                            usage = obj['usage']
                        for choice in obj.get('choices') or []:
                            delta = choice.get('delta') or {}
                            if delta.get('reasoning'):
                                reasoning += 1
                            text = delta.get('content') or ''
                            if text:
                                parts.append(text)
                                if first is None:
                                    first = round(now, 3)
                                if text.strip():
                                    if first_text is None:
                                        first_text = round(now, 3)
                                    last_text = now
                            if choice.get('finish_reason'):
                                finish = choice['finish_reason']
    except httpx.HTTPError as exc:
        kind = kind or 'TRANSPORT'
        detail = type(exc).__name__ + ': ' + str(exc)[:300]
    seconds_used = round(time.monotonic() - begin, 3)
    text = ''.join(parts)
    if kind is None:
        if reasoning or ((usage or {}).get('completion_tokens_details') or {}).get('reasoning_tokens'):
            kind = 'REASONING_OUTPUT'
        elif echo_provider != provider['name'] or not str(echo_model or '').startswith(model):
            kind = 'ECHO_MISMATCH'
            detail = f'{echo_provider} / {echo_model}'
        elif finish != 'stop':
            kind = 'FINISH_NOT_STOP'
            detail = str(finish)
        elif not text.strip():
            kind = 'EMPTY_ANSWER'
    diagnostics = {'provider': provider['name'], 'tag': provider['tag'], 'http_status': status, 'seconds': seconds_used,
                   'first_content_s': first, 'first_nonblank_s': first_text,
                   'last_nonblank_s': round(last_text, 3) if last_text is not None else None,
                   'content_chars': len(text), 'blank_chars': len(text) - len(text.strip()), 'finish_reason': finish,
                   'usage': usage, 'reasoning_chunks': reasoning, 'failure': kind, 'detail': detail}
    raw = '\n'.join(line for _, line in lines).encode('utf-8')
    if kind is not None:
        return None, kind, diagnostics, lines
    body = {'id': 'stream-' + hashlib.sha256(raw).hexdigest()[:16], 'object': 'chat.completion',
            'provider': echo_provider, 'model': echo_model, 'usage': usage,
            'choices': [{'index': 0, 'finish_reason': finish, 'message': {'role': 'assistant', 'content': text}}]}
    envelope = {'status_code': 200, 'retry_after': None, 'body_json': body, 'body_text': None,
                'body_sha256': hashlib.sha256(raw).hexdigest(), 'stream_reconstructed': True}
    return envelope, None, diagnostics, lines


def send_with_fallback(client, *, body, ticket, phase, error_module, request_encoder, policy, policy_sha256,
                       recorder=None, now=time.monotonic):
    """Experiment replacement of send_reserved: one logical product call, providers in policy order."""
    payload_base = request_encoder(body)
    deadline = min(float(ticket['deadline']), now() + min(float(policy['per_call_seconds']),
                                                          float(ticket['remaining_seconds'])))
    attempts = []
    for index, provider in enumerate(policy['providers']):
        remaining = deadline - now()
        if remaining < policy['min_attempt_seconds']:
            break
        if client.calls >= client.max_calls:
            raise error_module.BudgetExhausted('experiment client physical call limit')
        payload = copy.deepcopy(payload_base)
        payload.pop('max_tokens', None)
        payload['model'] = client.model
        payload['provider'] = route(provider)
        payload['reasoning'] = {'effort': 'none'}
        payload['usage'] = {'include': True}
        payload['stream'] = True
        client.calls += 1
        out = Path(client.output) / f'call-{client.calls:03d}-{phase}'
        out.mkdir(parents=True, exist_ok=False)
        (out / 'request.json').write_text(json.dumps(payload, ensure_ascii=False))
        row = {'physical_call': client.calls, 'phase': phase, 'provider_index': index, 'provider': provider['name'],
               'tag': provider['tag'], 'policy_sha256': policy_sha256, 'attempt_seconds': round(remaining, 3)}
        if recorder:
            recorder('started', row, payload)
        envelope, kind, diag, lines = stream_attempt(
            payload, key=client._key, provider=provider, model=client.model, seconds=remaining,
            first_nonblank=policy['first_nonblank_seconds'], stall=policy['nonblank_stall_seconds'],
            transport=getattr(client, 'transport', None))
        row.update(diag)
        (out / 'stream.jsonl.gz').write_bytes(gzip.compress(json.dumps(lines, ensure_ascii=False).encode()))
        (out / 'attempt.json').write_text(json.dumps(row, ensure_ascii=False, indent=1))
        if envelope is not None:
            (out / 'response.json').write_text(json.dumps(envelope['body_json'], ensure_ascii=False))
        attempts.append(row)
        Path(client.output, 'fallback-attempts.jsonl').open('a').write(json.dumps(row, ensure_ascii=False) + '\n')
        if recorder:
            recorder('finished', row, envelope)
        if envelope is not None:
            envelope['fallback_attempts'] = attempts
            return envelope
    error = error_module.TransportError('no provider gave a usable answer', retryable=False, unknown=True,
                                        response={'fallback_attempts': attempts})
    error.code = 'MODEL_PROVIDERS_EXHAUSTED'
    error.http_status = 504
    raise error
