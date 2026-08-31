from types import SimpleNamespace

from lawrag.api.routers import rag


class _View:
    name = "기존법"
    by_id = {1: {"id": 1}}

    def path(self, node):
        return "제1조"


class _Index:
    docs = {"floor": _View()}
    canonical_doc_ids = frozenset({"current-generation"})


def test_stored_question_and_floor_open_add_only_recovery(monkeypatch):
    branch = SimpleNamespace(
        doc_id="law29", node=244, doc="금융회사의 지배구조에 관한 법률",
        path="제29조(준법감시인 등의 겸직 제한)",
        origin="role-predicate-governing-hypothesis")
    captured = {}

    def fake_router(_idx, question, **kwargs):
        captured.update(question=question, **kwargs)
        return [branch], {
            "reason": "validated_role_predicate_bundle",
            "general_lexical_search_calls": 0,
            "forbidden_fields_used": [],
            "predicate_families": ["role_compatibility"],
            "caps": {"cards": 2, "additions": 4},
            "cards": [{
                "slug": "쟁점/겸직의-경계", "title": "겸직의 경계",
                "matched_triggers": ["준법감시인"],
                "actor_roles": ["준법감시인"],
                "predicate_families": ["role_compatibility"],
                "gate_open": True, "hypotheses": [],
                "text": "forbidden card body",
            }],
        }

    monkeypatch.setattr(rag.legal_coordinates, "article_root", lambda _v, n: n)
    monkeypatch.setattr(
        rag.companion_recovery, "role_predicate_governing_feedback", fake_router)

    result = rag._role_predicate_feedback_recovery(_Index(), {
        "질의": "준법감시인이 다른 업무를 수행할 수 있는가",
        "context": [{"doc_id": "floor", "node": 1}],
        "답": "기존 답은 바뀌지 않는다",
    })

    assert captured["answer_incorrect"] is True
    assert captured["exclude"] == [("floor", 1)]
    assert captured["preferred_document_ids"] == ["current-generation"]
    assert result["baseline_preserved"] is True
    assert result["added_count"] == 1
    assert result["selected"][0]["doc_id"] == "law29"
    assert result["audit"]["general_lexical_search_calls"] == 0
    assert result["audit"]["cards"][0]["gate_open"] is True
    assert "text" not in result["audit"]["cards"][0]


def _patch_feedback_side_effects(monkeypatch, *, switch=True):
    saved = []
    ask = {"질의": "준법감시인이 업무를 수행할 수 있는가", "context": []}
    monkeypatch.setattr(rag.tuples_mod, "find", lambda _qid: ask)
    monkeypatch.setattr(
        rag.tuples_mod, "log_feedback",
        lambda qid, verdict, expected, note: saved.append(
            (qid, verdict, expected, note)) or {"판정": verdict})
    monkeypatch.setattr(rag.logbook, "rag_event", lambda *_a, **_k: None)
    monkeypatch.setattr(rag.wikiledger, "feedback", lambda *_a, **_k: False)
    monkeypatch.setattr(rag.switches_mod, "is_on", lambda _key: switch)
    return saved


def test_wrong_feedback_without_location_returns_recovery(monkeypatch):
    saved = _patch_feedback_side_effects(monkeypatch)
    monkeypatch.setattr(
        rag, "_role_predicate_feedback_recovery",
        lambda _idx, _ask: {"enabled": True, "attempted": True,
                            "reason": "validated_role_predicate_bundle",
                            "selected": [{"doc_id": "law29", "node": 244}]})
    monkeypatch.setattr(rag.index_mod, "current", lambda: object())

    result = rag.rag_feedback(rag.Feedback(qid="q1", verdict="오답"))

    assert result["saved"] is True
    assert saved == [("q1", "오답", None, "")]
    assert result["recovery"]["selected"] == [{"doc_id": "law29", "node": 244}]


def test_switch_off_and_explicit_location_do_not_run_router(monkeypatch):
    _patch_feedback_side_effects(monkeypatch, switch=False)
    monkeypatch.setattr(
        rag, "_role_predicate_feedback_recovery",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must stay closed")))
    off = rag.rag_feedback(rag.Feedback(qid="q1", verdict="오답"))
    assert off["recovery"]["reason"] == "switch_off"

    _patch_feedback_side_effects(monkeypatch, switch=True)
    monkeypatch.setattr(rag.index_mod, "current", lambda: _Index())
    explicit = rag.rag_feedback(rag.Feedback(
        qid="q1", verdict="오답", expected={"doc_id": "floor", "node": 1}))
    assert explicit["recovery"]["reason"] == "explicit_expected_coordinate"


def test_recovery_error_fails_open_after_receipt(monkeypatch):
    saved = _patch_feedback_side_effects(monkeypatch)
    monkeypatch.setattr(rag.index_mod, "current", lambda: object())
    monkeypatch.setattr(
        rag, "_role_predicate_feedback_recovery",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))

    result = rag.rag_feedback(rag.Feedback(qid="q1", verdict="오답"))

    assert saved
    assert result["saved"] is True
    assert result["recovery"]["reason"] == "recovery_failed_open"
    assert result["recovery"]["error"] == "RuntimeError"
