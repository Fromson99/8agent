"""Experiment provider fallback (user 2026-11-12): a provider that gives no usable answer is replaced by the next
pre-checked provider for the same request; a complete answer is returned as is (repair stays with the product)."""
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '02_BACKEND'))

from lawrag.research import provider_fallback as pf  # noqa: E402

MODEL = 'qwen/qwen3.8-27b'


class Errors:
    class TransportError(Exception):
        def __init__(self, message, *, retryable=False, unknown=False, response=None):
            super().__init__(message)
            self.retryable, self.unknown, self.response = retryable, unknown, response

    class BudgetExhausted(Exception):
        pass


def policy(**over):
    cfg = {'schema_version': pf.SCHEMA_VERSION, 'model': MODEL,
           'providers': [{'tag': 'one/fp8', 'name': 'One'}, {'tag': 'two/fp8', 'name': 'Two'},
                         {'tag': 'three/fp8', 'name': 'Three'}],
           'stream': True, 'per_call_seconds': 30, 'first_nonblank_seconds': 0.4, 'nonblank_stall_seconds': 0.4,
           'min_attempt_seconds': 0.2, 'reasoning': {'effort': 'none'}, 'model_fallback': False, 'output_cap': None,
           'authorization': {'source': 'user_message', 'text': 'test'}}
    cfg.update(over)
    return cfg


def sse(provider, chunks, finish='stop', delay=0.0, usage=True):
    def gen():
        for text in chunks:
            if delay:
                time.sleep(delay)
            yield ('data: ' + json.dumps({'provider': provider, 'model': MODEL,
                   'choices': [{'index': 0, 'delta': {'content': text}}]}) + '\n\n').encode()
        last = {'provider': provider, 'model': MODEL, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]}
        if usage:
            last['usage'] = {'prompt_tokens': 10, 'completion_tokens': 5, 'cost': 0.0001}
        yield ('data: ' + json.dumps(last) + '\n\n').encode()
        yield b'data: [DONE]\n\n'
    return gen()


def runaway(provider):
    def gen():
        yield ('data: ' + json.dumps({'provider': provider, 'model': MODEL,
               'choices': [{'index': 0, 'delta': {'content': '{"choice": "FOLLOW"'}}]}) + '\n\n').encode()
        for _ in range(200):
            time.sleep(0.02)
            yield ('data: ' + json.dumps({'provider': provider, 'model': MODEL,
                   'choices': [{'index': 0, 'delta': {'content': '\n\n'}}]}) + '\n\n').encode()
    return gen()


def keepalive_only():
    def gen():
        for _ in range(200):
            time.sleep(0.02)
            yield b': OPENROUTER PROCESSING\n\n'
    return gen()


def run(tmp_path, behaviours, cfg=None, max_calls=10, remaining=30):
    seen = []

    def handler(request):
        body = json.loads(request.content)
        name = {'one/fp8': 'One', 'two/fp8': 'Two', 'three/fp8': 'Three'}[body['provider']['only'][0]]
        seen.append((name, body))
        behaviour = behaviours[name]
        if isinstance(behaviour, Exception):
            raise behaviour
        if isinstance(behaviour, int):
            return httpx.Response(behaviour, json={'error': {'message': 'nope'}})
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=behaviour(name))

    client = SimpleNamespace(calls=0, max_calls=max_calls, model=MODEL, _key='k', output=str(tmp_path),
                             transport=httpx.MockTransport(handler))
    cfg = cfg or policy()
    ticket = {'deadline': time.monotonic() + remaining, 'remaining_seconds': remaining, 'attempt_id': 'A1'}
    events = []
    body = {'model': MODEL, 'messages': [{'role': 'user', 'content': 'q'}], 'reasoning': {'effort': 'none'},
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'o', 'strict': True, 'schema': {}}}}
    result = pf.send_with_fallback(client, body=body, ticket=ticket, phase='p', error_module=Errors,
                                   request_encoder=lambda b: dict(b), policy=cfg, policy_sha256='h',
                                   recorder=lambda event, row, _: events.append((event, row.get('provider'), row.get('failure'))))
    return result, seen, client, events


def ok(chunks):
    return lambda name: sse(name, chunks)


def test_runaway_newlines_switch_to_next_provider(tmp_path):
    result, seen, client, events = run(tmp_path, {'One': runaway, 'Two': ok(['{"a": ', '1}']), 'Three': ok(['{}'])})
    assert [name for name, _ in seen] == ['One', 'Two']
    assert result['body_json']['provider'] == 'Two'
    assert result['body_json']['choices'][0]['message']['content'] == '{"a": 1}'
    assert [a['failure'] for a in result['fallback_attempts']] == ['BLANK_STALL', None]
    assert client.calls == 2
    # Same request each time; only provider routing (and the stream flag) is set by the sender.
    assert seen[0][1]['messages'] == seen[1][1]['messages'] and seen[1][1]['stream'] is True
    assert seen[1][1]['provider'] == {'only': ['two/fp8'], 'order': ['two/fp8'], 'quantizations': ['fp8'],
                                      'allow_fallbacks': False, 'require_parameters': True}


@pytest.mark.parametrize('first', [429, 502, 400])
def test_http_failures_switch(tmp_path, first):
    result, seen, _, _ = run(tmp_path, {'One': first, 'Two': ok(['{}']), 'Three': ok(['{}'])})
    assert [n for n, _ in seen] == ['One', 'Two'] and result['body_json']['provider'] == 'Two'
    assert result['fallback_attempts'][0]['failure'] == 'HTTP_STATUS'


def test_no_content_and_transport_error_switch(tmp_path):
    result, seen, _, _ = run(tmp_path, {'One': lambda n: keepalive_only(), 'Two': httpx.ConnectError('down'),
                                        'Three': ok(['{"x": 2}'])})
    assert [n for n, _ in seen] == ['One', 'Two', 'Three']
    assert [a['failure'] for a in result['fallback_attempts']] == ['NO_NONBLANK', 'TRANSPORT', None]


def test_complete_answer_with_bad_json_is_returned_not_switched(tmp_path):
    result, seen, _, _ = run(tmp_path, {'One': ok(['not json at all']), 'Two': ok(['{}']), 'Three': ok(['{}'])})
    assert [n for n, _ in seen] == ['One']
    assert result['body_json']['choices'][0]['message']['content'] == 'not json at all'


def test_finish_length_reasoning_and_echo_mismatch_switch(tmp_path):
    def reasoning(name):
        def gen():
            yield ('data: ' + json.dumps({'provider': name, 'model': MODEL,
                   'choices': [{'index': 0, 'delta': {'reasoning': 'think', 'content': '{}'}}]}) + '\n\n').encode()
            yield ('data: ' + json.dumps({'provider': name, 'model': MODEL,
                   'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]}) + '\n\n').encode()
        return gen()
    with pytest.raises(Errors.TransportError) as caught:
        run(tmp_path, {'One': lambda n: sse(n, ['{"a"'], finish='length'), 'Two': reasoning,
                       'Three': lambda n: sse('Elsewhere', ['{}'])})
    kinds = [a['failure'] for a in caught.value.response['fallback_attempts']]
    assert kinds == ['FINISH_NOT_STOP', 'REASONING_OUTPUT', 'ECHO_MISMATCH']
    assert caught.value.unknown is True and caught.value.code == 'MODEL_PROVIDERS_EXHAUSTED'


def test_budget_and_shared_deadline(tmp_path):
    with pytest.raises(Errors.BudgetExhausted):
        run(tmp_path / 'a', {'One': 503, 'Two': 503, 'Three': ok(['{}'])}, max_calls=2)
    # The attempts share the product's per-call deadline: no new attempt once too little time is left.
    with pytest.raises(Errors.TransportError) as caught:
        run(tmp_path / 'b', {'One': runaway, 'Two': runaway, 'Three': ok(['{}'])},
            cfg=policy(min_attempt_seconds=0.5), remaining=1.0)
    assert len(caught.value.response['fallback_attempts']) == 2


def test_policy_file_is_valid_and_ordered(tmp_path):
    cfg, digest = pf.load_policy(ROOT / '00_SYSTEM/EXPERIMENT_PROVIDER_FALLBACK.json')
    assert [p['name'] for p in cfg['providers']] == ['Near AI', 'CoreWeave', 'Chutes', 'Reka', 'Parasail']
    assert cfg['first_nonblank_seconds'] == 60 and cfg['nonblank_stall_seconds'] == 60 and len(digest) == 64
    bad = tmp_path / 'bad.json'
    bad.write_text(json.dumps(dict(cfg, model_fallback=True)))
    with pytest.raises(ValueError):
        pf.load_policy(bad)


def test_experiment_client_generate_uses_fallback(tmp_path, monkeypatch):
    """Standalone experiment scripts: ExperimentClient(..., fallback_policy=...) sends the same request to the next
    provider when the first gives no usable answer; without the option nothing changes."""
    from lawrag.research.experiment_client import ExperimentClient
    monkeypatch.setenv('OPEN_ROUTER', 'test-key')
    seen = []

    def handler(request):
        body = json.loads(request.content)
        tag = body['provider']['only'][0]
        seen.append(tag)
        if tag == 'near-ai/fp8':
            return httpx.Response(503, json={'error': {'message': 'busy'}})
        name = {'coreweave/fp8': 'CoreWeave'}[tag]
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=sse(name, ['{"answer": ', '"ok"}']))

    client = ExperimentClient(ROOT, tmp_path / 'client', max_calls=4, transport=httpx.MockTransport(handler),
                              fallback_policy=ROOT / '00_SYSTEM/EXPERIMENT_PROVIDER_FALLBACK.json')
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['answer'],
              'properties': {'answer': {'type': 'string'}}}
    out = client.generate('Answer with JSON.', {'q': 'x'}, schema, phase='probe')
    assert out == {'answer': 'ok'} and seen == ['near-ai/fp8', 'coreweave/fp8'] and client.calls == 2
    assert client.usage[-1]['upstream_provider'] == 'CoreWeave' and client.usage[-1]['fallback_attempts'] == 2
