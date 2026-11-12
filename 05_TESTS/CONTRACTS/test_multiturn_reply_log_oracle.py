"""LOG=on: the .log of a follow-up that ended in a confirmation says why (user 2026-11-11).

The model calls were already there; the selection, the proposal and the refusal reason were not.
Actual service.py entry, Oracle-only records, scripted model whose reviewer refuses.
"""
import importlib.util
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('reply_log_base', ROOT/'05_TESTS/CONTRACTS/test_concurrent_chats_oracle.py')
_base = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_base)
native_oracle = _base.native_oracle  # noqa: F401  (fixture)
published = _base.published  # noqa: F401  (fixture)
structured_generation = _base.structured_generation  # noqa: F401  (fixture)


def test_a_confirmation_turn_logs_its_decision(native_oracle, tmp_path, monkeypatch):
    import test_unified_legal_agent as cases
    monkeypatch.setenv('LOG', 'on')
    send = cases.ScriptedTransport.send_once

    def refuse(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']
        if view.get('source_stage', view['phase']).startswith('memory-command-check'):
            return cases.wire({'valid': False, 'reason': '모의 거절', 'request_relation': 'NEW_TOPIC', 'requested_task': 'x'})
        return send(self, body=body, ticket=ticket)
    monkeypatch.setattr(cases.ScriptedTransport, 'send_once', refuse)
    ask, _, _ = _base.service(native_oracle, tmp_path, monkeypatch)
    out, _ = ask('s-reply-log', 'req-1', '그럼 제2조는?')
    assert out['status'] == 200 and '판단이 엇갈려' in str(out['body'])
    from semantic_runtime import request_report
    deadline = time.monotonic()+30
    while time.monotonic() < deadline and request_report._FINALIZER_QUEUE.unfinished_tasks:
        time.sleep(0.2)
    logs = list((tmp_path/'synthetic-nfs-logs').rglob('*.log'))
    assert len(logs) == 1, logs
    text = logs[0].read_text(encoding='utf-8')
    for label in ('MULTITURN 명령 제안', 'MULTITURN 명령 거절', 'MULTITURN 확인 질문'):
        assert '=== '+label+' ===' in text, label
    assert '모의 거절' in text and 'issue_codes' in text
