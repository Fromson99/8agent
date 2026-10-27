"""Replay saved text through synthetic SSE boundaries; never contact a model."""
from pathlib import Path
import hashlib
import json
import sys

from common import ART, ROOT, RESPONSE_RECEPTION, WHITESPACE_LIMIT, save, sha


def main():
    code = Path(sys.argv[1]).resolve()
    sys.path[:0] = [str(code/'02_BACKEND'), str(code)]
    from semantic_runtime.legal_agent import buffered_json_stream as stream
    source = ROOT/'04_EXPERIMENTS/ADR/ADR-1043-ontology-mvp-input-budget/artifacts/matrix/002-fsc-hard-002-A1/model/call-002-service/response.json'
    body = json.loads(source.read_text())
    content = body['choices'][0]['message']['content']
    rows = []
    for width in (1, 97, 1024):
        receiver = stream.BufferedJSONStream(body['model'], whitespace_limit=WHITESPACE_LIMIT)
        received = ''
        caught = None
        for at in range(0, len(content), width):
            delta = content[at:at+width]
            frame = {'model': body['model'], 'provider': body['provider'], 'choices': [
                {'index': 0, 'delta': {'content': delta}, 'finish_reason': None}]}
            wire = ('data: '+json.dumps(frame, ensure_ascii=False)+'\n\n').encode()
            received += delta
            try:
                receiver.feed(wire)
            except stream.BufferedStreamError as exc:
                caught = exc
                break
        assert caught is not None and caught.kind == 'OUTPUT_WHITESPACE_STALL'
        snapshot = receiver.snapshot()
        assert snapshot['choices'][0]['message']['content'] == received
        receipt = receiver.receipt()
        assert not receipt['complete'] and not receipt['done']
        assert receipt['outside_whitespace_run'] == WHITESPACE_LIMIT
        assert not snapshot.get('usage'), 'historical total must not be invented as early usage'
        assert content.startswith(received) and len(received) < len(content)
        rows.append({'synthetic_content_delta_characters': width,
            'received_content_characters': len(received),
            'received_content_sha256': hashlib.sha256(received.encode()).hexdigest(),
            'receipt': receipt})
    assert len({r['receipt']['stall_offset'] for r in rows}) == 1
    save(ART/'historical-stall-fixture-validation.json', {
        'passed': len(rows), 'failed': 0, 'model_calls': 0,
        'response_reception': RESPONSE_RECEPTION, 'whitespace_limit': WHITESPACE_LIMIT,
        'source_path': str(source.relative_to(ROOT)), 'source_sha256': sha(source),
        'source_content_characters': len(content),
        'implementation_path': str(Path(stream.__file__).relative_to(ROOT)),
        'implementation_sha256': sha(stream.__file__),
        'script_path': str(Path(__file__).relative_to(ROOT)), 'script_sha256': sha(__file__),
        'method': 'Saved original response text, synthetic SSE chunks. Original provider chunk timing and cancellation/billing effects are unknown.',
        'raw_original_unchanged': sha(source), 'rows': rows})
    print('Historical text fixture:', len(rows), 'passed; model calls 0')


if __name__ == '__main__':
    main()
