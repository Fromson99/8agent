from lawrag.core.rag import proof_boundary_feedback as boundary
from lawrag.core.rag import termexplore
from lawrag.core.rag.index import Index


def _index():
    return Index.from_docs([("d", {"name": "시험법", "kind": "law"}, {
        "nodes": [
            {"id": node, "parent": None, "level": 1,
             "surface": f"제{node}조", "title": title,
             "span": [node - 1, node]}
            for node, title in (
                (1, "일반"), (2, "채무조정"), (3, "준법감시인"))
        ],
        "blocks": [
            {"idx": 0, "text": "일반 규정이다.", "kind": "text"},
            {"idx": 1, "text": "채무조정 업무를\n전담한다.", "kind": "text"},
            {"idx": 2, "text": "준법감시인은 다른 업무를 겸직할 수 없다.",
             "kind": "text"},
        ],
    })])


def _branch(index, node, origin="initial", terms=()):
    return termexplore._branch(index, "d", node, tuple(terms), origin=origin)


class _LLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def structured(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.pop(0)


def _gate(state, *, evidence=(), kind="stop", from_id="",
          query="", keywords=(), missing=""):
    return {
        "state": state,
        "answer_claim": "질문의 핵심 법적 결론",
        "missing_claim": missing,
        "evidence": list(evidence),
        "action": {
            "kind": kind, "from_id": from_id, "query": query,
            "keywords": list(keywords), "reason": "단일 간극을 확인한다",
        },
    }


def _verify(status, *, evidence=(), gap=""):
    return {
        "status": status,
        "conclusion": "근거가 확인됐다" if status == "closed" else "",
        "evidence": list(evidence), "remaining_gap": gap,
    }


def test_existing_grounded_support_stops_after_gate():
    index = _index()
    initial = [_branch(index, 2, terms=("채무조정",))]
    llm = _LLM([_gate(
        "supported",
        evidence=[{"candidate_id": "C1",
                   "quote": "채무조정 업무를 전담한다."}])])

    selected, meta = boundary.run(
        index, "채무조정 업무를 전담하는가", llm,
        initial, initial, ("채무조정",), {})

    assert [row.node for row in selected] == [2]
    assert meta["status"] == "complete"
    assert meta["reason"] == "existing_grounded_support"
    assert len(llm.calls) == 1
    assert meta["raw_candidate_count"] == 0


def test_whitespace_equivalent_quote_is_source_grounded():
    index = _index()
    row = _branch(index, 2)

    accepted, errors = boundary._validate_evidence(
        index,
        [{"candidate_id": "C1", "quote": "채무조정 업무를 전담한다."}],
        {"C1": row})

    assert errors == []
    assert len(accepted) == 1
    assert "\n" in accepted[0]["quote"]


def test_seen_inspection_can_close_without_expanding_pool():
    index = _index()
    initial = [_branch(index, 1)]
    deferred = _branch(index, 2, terms=("채무조정",))
    llm = _LLM([
        _gate(
            "present_but_unread", kind="inspect_seen", from_id="C2",
            missing="채무조정 업무의 전담 여부"),
        _verify("closed", evidence=[{
            "candidate_id": "V1",
            "quote": "채무조정 업무를 전담한다.",
            "role": "support",
        }]),
    ])

    selected, meta = boundary.run(
        index, "채무조정 업무를 전담하는가", llm,
        initial, [initial[0], deferred], ("채무조정",), {})

    assert [row.node for row in selected] == [1]
    assert meta["status"] == "complete"
    assert meta["raw_candidate_count"] == 1
    assert meta["admitted"] == []
    assert len(meta["evidence_pool"]) == 2
    assert len(llm.calls) == 2


def test_search_admits_and_promotes_only_verified_fresh_candidate(monkeypatch):
    index = _index()
    initial = [_branch(index, 1)]
    fresh = _branch(
        index, 3, origin="boundary-keyword", terms=("준법감시인",))
    llm = _LLM([
        _gate(
            "missing_rule", kind="keyword_search",
            query="준법감시인 겸직 제한", keywords=("준법감시인", "겸직"),
            missing="준법감시인의 겸직 제한"),
        _verify("closed", evidence=[{
            "candidate_id": "V1",
            "quote": "준법감시인은 다른 업무를 겸직할 수 없다.",
            "role": "support",
        }]),
    ])
    monkeypatch.setattr(
        boundary, "_execute",
        lambda *args, **kwargs: ([fresh], {"tool": "keyword_search"}))

    selected, meta = boundary.run(
        index, "담당자가 다른 업무를 겸직할 수 있는가", llm,
        initial, initial, ("담당자",), {}, cap=2)

    assert [row.node for row in selected] == [1, 3]
    assert [row["node"] for row in meta["admitted"]] == [3]
    assert [row["node"] for row in meta["promoted"]] == [3]
    assert meta["actions"][0]["admitted_count"] == 1


def test_unverified_raw_results_never_enter_evidence_pool(monkeypatch):
    index = _index()
    initial = [_branch(index, 1)]
    fresh = _branch(index, 3, origin="boundary-keyword")
    llm = _LLM([
        _gate(
            "missing_rule", kind="keyword_search",
            query="준법감시인 겸직 제한", keywords=("준법감시인",),
            missing="준법감시인의 겸직 제한"),
        _verify("unresolved", evidence=(), gap="직접 근거 없음"),
    ])
    monkeypatch.setattr(
        boundary, "_execute",
        lambda *args, **kwargs: ([fresh], {"tool": "keyword_search"}))

    selected, meta = boundary.run(
        index, "담당자가 겸직할 수 있는가", llm,
        initial, initial, ("담당자",), {}, cap=2)

    assert [row.node for row in selected] == [1]
    assert [row["node"] for row in meta["evidence_pool"]] == [1]
    assert meta["admitted"] == []
    assert meta["raw_candidate_count"] == 1


def test_novelty_veto_blocks_query_inside_initial_trace():
    index = _index()
    initial = [_branch(index, 1)]
    llm = _LLM([_gate(
        "missing_rule", kind="keyword_search",
        query="채무조정", keywords=("채무조정",),
        missing="채무조정 규정")])

    selected, meta = boundary.run(
        index, "채무조정은 가능한가", llm,
        initial, initial, ("채무조정",), {})

    assert [row.node for row in selected] == [1]
    assert meta["reason"] == "novelty_veto"
    assert meta["actions"][0]["skipped"] == "query_inside_initial_trace"
    assert len(llm.calls) == 1
