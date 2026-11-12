"""ADR-1504 cm-014: after the answer read rounds were used up the answer still proposed reads; the
ANSWER_READ_REENTRY_UNAVAILABLE event carried the capacity function itself, the journal could not
store it as JSON and the request ended with HTTP 500 after 11 model calls. The test harness event
sink never serialized payloads, so the earlier round-limit test passed."""
import json

from test_guided_answer_single_write import READ


def test_round_limit_event_is_stored_as_json(monkeypatch):
    reply = {'proposed_reads': [READ]}
    stored = []
    # The executor of the stage harness; record events the way the journal does (JSON text).
    def event(kind, payload):
        stored.append((kind, json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))))
    import test_guided_answer_single_write as h
    real_execution = h.execution
    def execution(*a, **k):
        e, sent = real_execution(*a, **k)
        e.s.work.event = event
        return e, sent
    monkeypatch.setattr(h, 'execution', execution)
    go, modes = h.stage(monkeypatch, [reply], count=6)
    assert go()['guided_reply'] is reply
    unavailable = [p for k, p in stored if k == 'ANSWER_READ_REENTRY_UNAVAILABLE']
    assert unavailable and unavailable[0]['capacity'] is True and unavailable[0]['round'] == 6
