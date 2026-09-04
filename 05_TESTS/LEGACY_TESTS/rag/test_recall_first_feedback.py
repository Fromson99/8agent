from lawrag.core.rag import recall_first_feedback as recall
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
            {"idx": 1, "text": "채무조정 업무를 전담한다.", "kind": "text"},
            {"idx": 2, "text": "준법감시인은 다른 업무를 겸직할 수 없다.",
             "kind": "text"},
        ],
    })])


def _branch(index, node, *, origin="initial", mandatory=False):
    row = termexplore._branch(index, "d", node, (), origin=origin)
    if mandatory:
        from dataclasses import replace
        row = replace(row, mandatory=True)
    return row


class _LLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def structured(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.pop(0)


def _planner():
    return {
        "issue": "채무조정 업무와 겸직 제한",
        "operation_terms": ["채무조정", "겸직 제한"],
        "relation_seed_ids": ["C1"],
        "exact_query": "채무조정 전담",
        "keywords": ["채무조정", "준법감시인"],
        "assertion_query": "준법감시인은 채무조정 업무를 겸직할 수 있는가",
        "vector_query": "담당자가 다른 업무를 함께 수행하는 사실관계",
    }


def _selector(evidence=()):
    return {"issue": "채무조정 업무와 겸직 제한",
            "evidence": list(evidence), "uncovered": []}


def test_all_grounded_route_results_are_retained_without_selector_acceptance(
        monkeypatch):
    index = _index()
    initial = [_branch(index, 1)]
    fresh = _branch(index, 2, origin="recall-exact")
    receipts = [{"kind": kind, "fingerprint": kind, "query": kind,
                 "keywords": [], "seed_ids": [], "raw_count": int(pos == 0),
                 "tool_meta": {}, "skipped": ""}
                for pos, kind in enumerate(recall.ROUTE_KINDS)]
    monkeypatch.setattr(
        recall, "_execute_union", lambda *args, **kwargs: ([fresh], receipts))
    llm = _LLM([_planner(), _selector()])

    selected, meta = recall.run(
        index, "채무조정 담당자는 누구인가", llm,
        initial, initial, (), {}, cap=2)

    assert [row.node for row in selected] == [1]
    assert [row["node"] for row in meta["retained"]] == [2]
    assert [row["node"] for row in meta["evidence_pool"]] == [1, 2]
    assert meta["promoted"] == []
    assert meta["coverage_ledger"]["visited_routes"] == list(recall.ROUTE_KINDS)
    assert len(llm.calls) == 2


def test_partial_exact_quote_can_promote_without_complete_judgment(monkeypatch):
    index = _index()
    initial = [_branch(index, 1)]
    fresh = _branch(index, 3, origin="recall-relation")
    receipts = [{"kind": kind, "fingerprint": kind, "query": kind,
                 "keywords": [], "seed_ids": [], "raw_count": int(pos == 0),
                 "tool_meta": {}, "skipped": ""}
                for pos, kind in enumerate(recall.ROUTE_KINDS)]
    monkeypatch.setattr(
        recall, "_execute_union", lambda *args, **kwargs: ([fresh], receipts))
    llm = _LLM([_planner(), _selector([{
        "candidate_id": "N1",
        "quote": "준법감시인은 다른 업무를 겸직할 수 없다.",
        "role": "partial",
    }])])

    selected, meta = recall.run(
        index, "채무조정 업무 겸직이 가능한가", llm,
        initial, initial, (), {}, cap=2)

    assert [row.node for row in selected] == [1, 3]
    assert [row["node"] for row in meta["promoted"]] == [3]
    assert meta["selector_errors"] == []


def test_invalid_quote_does_not_promote_but_coordinate_remains(monkeypatch):
    index = _index()
    initial = [_branch(index, 1)]
    fresh = _branch(index, 2, origin="recall-exact")
    receipts = [{"kind": kind, "fingerprint": kind, "query": kind,
                 "keywords": [], "seed_ids": [], "raw_count": int(pos == 0),
                 "tool_meta": {}, "skipped": ""}
                for pos, kind in enumerate(recall.ROUTE_KINDS)]
    monkeypatch.setattr(
        recall, "_execute_union", lambda *args, **kwargs: ([fresh], receipts))
    llm = _LLM([_planner(), _selector([{
        "candidate_id": "N1", "quote": "존재하지 않는 요약문",
        "role": "governing",
    }])])

    selected, meta = recall.run(
        index, "채무조정 담당자는 누구인가", llm,
        initial, initial, (), {}, cap=2)

    assert [row.node for row in selected] == [1]
    assert [row["node"] for row in meta["evidence_pool"]] == [1, 2]
    assert meta["promoted"] == []
    assert meta["selector_errors"] == ["quote_not_in_source:N1"]


def test_basis_exchange_never_evicts_mandatory_incumbent():
    index = _index()
    mandatory = _branch(index, 1, mandatory=True)
    ordinary = _branch(index, 2)
    fresh = _branch(index, 3)

    selected, evicted = recall._select_with_exchange(
        [mandatory, ordinary], [fresh], cap=2)

    assert [row.node for row in selected] == [1, 3]
    assert [row.node for row in evicted] == [2]
