from dataclasses import replace

from lawrag.core.rag import relation_navigation, retrieval_feedback, termexplore
from lawrag.core.rag.index import Index


def _index():
    return Index.from_docs([("d", {"name": "시험법"}, {
        "nodes": [
            {"id": 1, "parent": None, "level": 1,
             "surface": "제1조", "title": "일반", "span": [0, 1]},
            {"id": 2, "parent": None, "level": 1,
             "surface": "제2조", "title": "채무조정", "span": [1, 2]},
        ],
        "blocks": [
            {"idx": 0, "text": "일반 규정", "kind": "text"},
            {"idx": 1, "text": "채무조정 업무를 정한다", "kind": "text"},
        ],
    })])


class _LLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def structured(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.pop(0)


def _decision(*, sufficient, keep, reject=(), kind="stop", edge_ids=()):
    return {
        "sufficient": sufficient, "keep": list(keep), "reject": list(reject),
        "reason": "지배 규정 확인" if sufficient else "업무유형 규정 부족",
        "missing": [] if sufficient else ["채무조정 업무"],
        "action": {"kind": kind, "from_ids": ["C1"],
                   "edge_ids": list(edge_ids),
                   "keywords": ["채무조정"], "query": "채무조정 업무 규정",
                   "reason": "새 의미권으로 점프"},
    }


def test_부족판정이면_점프후_새후보를_다시_판정한다(monkeypatch):
    idx = _index()
    first = termexplore._branch(idx, "d", 1, (), origin="initial")
    second = termexplore._branch(idx, "d", 2, ("채무조정",), origin="jump")
    llm = _LLM([
        _decision(sufficient=False, keep=["C1"], kind="hybrid_jump"),
        _decision(sufficient=True, keep=["C2"]),
    ])
    monkeypatch.setattr(
        retrieval_feedback, "_execute",
        lambda *args, **kwargs: ([second], {"tool": "hybrid"}))

    selected, meta = retrieval_feedback.run(
        idx, "채무를 재조정할 수 있나", llm, [first], (), max_steps=3)

    assert [row.node for row in selected] == [2]
    assert meta["sufficient"] is True and meta["steps"] == 2
    assert meta["trail"][0]["action"] == "hybrid_jump"
    assert all(call[1]["model"] == retrieval_feedback.PRODUCT_MODEL
               for call in llm.calls)


def test_더_찾을_방향이_없으면_충분하지_않은_상태로_닫는다():
    idx = _index()
    first = termexplore._branch(idx, "d", 1, (), origin="initial")
    llm = _LLM([_decision(
        sufficient=False, keep=[], reject=["C1"], kind="stop")])

    selected, meta = retrieval_feedback.run(
        idx, "채무를 재조정할 수 있나", llm, [first], (), max_steps=3)

    assert selected == []
    assert meta["sufficient"] is False
    assert meta["trail"][0]["action"] == "stop"


def test_판정카드는_requirement와_실제_간선_E메뉴를_함께_보여준다(monkeypatch):
    idx = _index()
    first = termexplore._branch(idx, "d", 1, (), origin="initial")
    body = "10일 이내에 서면으로 제출하여야 한다."
    first = replace(first, body=body, body_chars=len(body))
    hop = relation_navigation.RelationHop(
        "d", 1, "d", 2, "위임", "out", "test:bundle",
        "대통령령", "DELEGATES_TO", True, "E1")
    monkeypatch.setattr(
        retrieval_feedback.relation_navigation, "neighbors",
        lambda *args, **kwargs: ([hop], {"source": "relations.RelationBundle"}))

    public, _by_id, by_edge, meta = retrieval_feedback._cards(
        idx, [first], blocked=set(), visited_edges=set())

    assert {row["kind"] for row in public[0]["requirements"]} >= {"TIME", "METHOD"}
    assert public[0]["unopened_edges"][0]["id"] == "E1"
    assert by_edge["E1"].target == ("d", 2)
    assert meta["available"] == 1


def test_relation_jump는_LLM이_고른_E간선만_연다(monkeypatch):
    idx = _index()
    first = termexplore._branch(idx, "d", 1, (), origin="initial")
    hop = relation_navigation.RelationHop(
        "d", 1, "d", 2, "위임", "out", "test:bundle",
        "대통령령", "DELEGATES_TO", True, "E1")
    monkeypatch.setattr(
        retrieval_feedback.relation_navigation, "neighbors",
        lambda *args, **kwargs: ([hop], {"source": "relations.RelationBundle"}))
    llm = _LLM([
        _decision(sufficient=False, keep=["C1"], kind="relation_jump",
                  edge_ids=["E1"]),
        _decision(sufficient=True, keep=["C2"]),
    ])

    selected, meta = retrieval_feedback.run(
        idx, "시행령의 구체화 규정은?", llm, [first], (), max_steps=3)

    assert [row.node for row in selected] == [2]
    assert meta["trail"][0]["edge_ids"] == ["E1"]
    assert meta["trail"][0]["meta"]["source"] == "selected_edge_ids"


def test_열_간선이_없으면_relation_jump를_행동메뉴에서_제외한다():
    schema = retrieval_feedback._schema(["C1"], [])

    kinds = schema["properties"]["action"]["properties"]["kind"]["enum"]
    assert "relation_jump" not in kinds
