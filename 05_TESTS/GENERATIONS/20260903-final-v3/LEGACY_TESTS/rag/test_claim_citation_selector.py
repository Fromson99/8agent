from lawrag.core.rag import claim_citation_selector as selector
from lawrag.core.rag import termexplore
from lawrag.core.rag.index import Index


def _index():
    return Index.from_docs([("d", {"name": "시험법", "kind": "law"}, {
        "nodes": [
            {"id": node, "parent": None, "level": 1,
             "surface": f"제{node}조", "title": title,
             "span": [node - 1, node]}
            for node, title in ((1, "일반"), (2, "겸직 금지"), (3, "신청서"))
        ],
        "blocks": [
            {"idx": 0, "text": "일반 규정이다.", "kind": "text"},
            {"idx": 1, "text": "준법감시인은 해당 업무를 겸직할 수 없다.", "kind": "text"},
            {"idx": 2, "text": "신청서를 제출한다.", "kind": "text"},
        ],
    })])


def _branch(index, node, origin="initial"):
    return termexplore._branch(index, "d", node, (), origin=origin)


class _LLM:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def structured(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.output


def test_exact_quote_selection_promotes_closed_menu_candidate():
    index = _index()
    incumbent = [_branch(index, 1)]
    candidate = _branch(index, 2, "source-registry")
    llm = _LLM({
        "selections": [{
            "candidate_id": "R1", "role": "direct",
            "quote": "준법감시인은 해당 업무를 겸직할 수 없다.",
            "reason": "질문의 겸직 가능성을 직접 규율한다",
        }],
        "remaining_gap": "",
    })

    selected, meta = selector.run(
        index, "준법감시인이 겸직할 수 있는가", llm,
        incumbent, incumbent, [candidate], "겸직 가능 여부", cap=2)

    assert [row.node for row in selected] == [1, 2]
    assert [row["node"] for row in meta["promoted"]] == [2]
    assert meta["validation_errors"] == []


def test_non_source_quote_cannot_promote():
    index = _index()
    incumbent = [_branch(index, 1)]
    candidate = _branch(index, 3, "source-registry")
    llm = _LLM({
        "selections": [{
            "candidate_id": "R1", "role": "direct",
            "quote": "겸직할 수 없다.", "reason": "관련 있어 보인다",
        }],
        "remaining_gap": "",
    })

    selected, meta = selector.run(
        index, "준법감시인이 겸직할 수 있는가", llm,
        incumbent, incumbent, [candidate], "겸직 가능 여부", cap=2)

    assert [row.node for row in selected] == [1]
    assert meta["validation_errors"] == ["quote_not_in_source:R1"]


def test_full_incumbent_skips_selector_and_never_exchanges():
    index = _index()
    incumbent = [_branch(index, 1), _branch(index, 3)]
    candidate = _branch(index, 2, "source-registry")
    llm = _LLM({"selections": [], "remaining_gap": ""})

    selected, meta = selector.run(
        index, "준법감시인이 겸직할 수 있는가", llm,
        incumbent, incumbent, [candidate], "겸직 가능 여부", cap=2)

    assert [row.node for row in selected] == [1, 3]
    assert meta["ran"] is False
    assert llm.calls == []


def test_registry_remains_in_pool_when_selector_rejects_all():
    index = _index()
    incumbent = [_branch(index, 1)]
    candidate = _branch(index, 3, "source-registry")
    llm = _LLM({"selections": [], "remaining_gap": "직접 근거 없음"})

    selected, meta = selector.run(
        index, "준법감시인이 겸직할 수 있는가", llm,
        incumbent, incumbent, [candidate], "겸직 가능 여부", cap=2)

    assert [row.node for row in selected] == [1]
    assert {row["node"] for row in meta["evidence_pool"]} == {1, 3}
    assert meta["hard_deletes"] == 0
