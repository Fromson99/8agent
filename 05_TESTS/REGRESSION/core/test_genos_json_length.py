import hashlib
import json
import sqlite3
import pytest
from lawrag.pipeline import genos_build as build
from lawrag.pipeline.genos_authoring_runtime import parse_content
from .test_genos_build import Fake, setup


@pytest.mark.parametrize('content', ['{"ok":true}', '```json\n{"ok":true}\n```', '```\n{"ok":true}\n```', '  ```JSON\r\n{"ok":true}\r\n```  '])
def test_exact_json_envelope(content):
    assert parse_content(content) == {'ok': True}


@pytest.mark.parametrize('content', [None, '', ' ', '[]', '{', '```json\n{}', 'Here is JSON:\n{}',
    '```json\n{}\n```\nextra', '```json\n{}\n```\n```json\n{}\n```', '{"x":NaN}', '{"x":Infinity}', '{"x":1,"x":2}', '<think>hi</think>{}'])
def test_malformed_not_repaired(content):
    with pytest.raises((ValueError, TypeError)):
        parse_content(content)


def test_fenced_extraction_review_handoff_and_length_retry(setup):
    args, _, out = setup
    budgets = []
    class Wrapped(Fake):
        def request(self, kind, path, payload, role):
            budgets.append(payload['max_tokens'])
            raw, receipt = super().request(kind, path, payload, role)
            choice = raw['choices'][0]
            choice['message']['content'] = '```json\n' + choice['message']['content'] + '\n```'
            if len(budgets) == 1:
                # Even complete-looking JSON with length must not be accepted.
                choice['finish_reason'] = 'length'
            return raw, receipt
    result = build.execute(args, provider_factory=Wrapped, emit=lambda _: None)
    assert result['ok'] and budgets[:2] == [8192, 16384]
    with sqlite3.connect(out / 'queue/queue.sqlite') as db:
        rows = db.execute('SELECT response,response_hash,state FROM attempt ORDER BY id').fetchall()
        assert rows[0][2] == 'INVALID'
        for raw, fingerprint, _ in rows:
            assert hashlib.sha256(raw.encode()).hexdigest() == fingerprint
            assert json.loads(raw)['choices'][0]['message']['content'].startswith('```json')
    assert list((out / 'handoff').glob('*.bundle.json'))
    args.resume = True
    assert build.execute(args, provider_factory=Wrapped, emit=lambda _: None)['ok']


def test_length_cap_fails_no_load(setup):
    args, _, out = setup
    args.max_output_tokens = 16384
    budgets = []
    class AlwaysLength(Fake):
        def request(self, kind, path, payload, role):
            budgets.append(payload['max_tokens'])
            raw, receipt = super().request(kind, path, payload, role)
            raw['choices'][0]['finish_reason'] = 'length'
            return raw, receipt
    with pytest.raises(ValueError, match='authoring incomplete'):
        build.execute(args, provider_factory=AlwaysLength, emit=lambda _: None)
    assert budgets[:3] == [8192, 16384, 16384]
    assert not (out / 'generation').exists()
    with sqlite3.connect(out / 'queue/queue.sqlite') as db:
        assert db.execute("SELECT count(*) FROM attempt WHERE state='VALIDATED'").fetchone()[0] == 0


@pytest.mark.parametrize('mode', ['json_object', 'json_schema'])
def test_explicit_json_modes(setup, mode):
    args, _, _ = setup
    args.json_mode = mode
    class Mode(Fake):
        def request(self, kind, path, payload, role):
            assert payload['response_format']['type'] == mode
            if mode == 'json_schema':
                assert payload['response_format']['json_schema']['strict']
            return super().request(kind, path, {k:v for k,v in payload.items() if k != 'response_format'}, role)
    assert build.execute(args, provider_factory=Mode, emit=lambda _: None)['ok']


def test_smaller_segments_preserve_every_character_and_offset(setup):
    args, _, out = setup
    args.segment_chars = 40
    args.max_calls = 0
    with pytest.raises(ValueError, match='Positive --max-calls'):
        build.execute(args, provider_factory=Fake, emit=lambda _: None)
    with sqlite3.connect(out / 'authoring-source.sqlite') as db:
        original = dict(db.execute('SELECT block_id,text FROM source_block'))
    pieces = {}
    with sqlite3.connect(out / 'queue/queue.sqlite') as db:
        for (raw,) in db.execute('SELECT input_json FROM job'):
            blocks = json.loads(raw)['blocks']
            assert sum(len(b['text']) for b in blocks) <= 40
            for b in blocks:
                assert original[str(b['idx'])][b['source_start']:b['source_end']] == b['text']
                pieces.setdefault(str(b['idx']), []).append(b)
    for key, value in original.items():
        ordered = sorted(pieces[key], key=lambda b:b['source_start'])
        assert ''.join(b['text'] for b in ordered) == value
        assert all(a['source_end'] == b['source_start'] for a,b in zip(ordered,ordered[1:]))
