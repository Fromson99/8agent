from dataclasses import replace

from lawrag.core.rag import legal_conditional_closure, termexplore
from lawrag.core.rag.index import Index


def _branch(index, node, terms=(), *, mandatory=False):
    return termexplore._branch(
        index, "d", node, terms, origin="test", mandatory=mandatory,
        mandatory_reason="relation" if mandatory else "")


def test_conditional_D는_질문에_근거화된_필수관계만_선택한다():
    index = Index.from_docs([("d", {"name": "시험법", "kind": "law"}, {
        "nodes": [
            {"id": 1, "parent": None, "surface": "제1조", "span": [0, 1]},
            {"id": 2, "parent": None, "surface": "제2조", "span": [1, 2]},
            {"id": 3, "parent": None, "surface": "제3조", "span": [2, 3]},
        ],
        "blocks": [
            {"idx": 0, "text": "재무서류를 제출한다.", "kind": "text"},
            {"idx": 1, "text": "재무서류의 심사 절차", "kind": "text"},
            {"idx": 2, "text": "질문과 무관한 정의", "kind": "text"},
        ],
    })])
    base = [_branch(index, 1, ("재무서류",))]
    grounded = _branch(index, 2, ("절차",), mandatory=True)
    ungrounded = _branch(index, 3, ("절차",), mandatory=True)

    selected, audit = legal_conditional_closure.select(
        index, "심사 절차는?", base, [grounded, ungrounded])

    assert [row.node for row in selected] == [2]
    assert audit["eligible_count"] == 1


def test_conditional_D는_필수가_아닌_일반인접을_열지_않는다():
    index = Index.from_docs([("d", {"name": "시험법", "kind": "law"}, {
        "nodes": [
            {"id": 1, "parent": None, "surface": "제1조", "span": [0, 1]},
            {"id": 2, "parent": None, "surface": "제2조", "span": [1, 2]},
        ],
        "blocks": [
            {"idx": 0, "text": "재무서류", "kind": "text"},
            {"idx": 1, "text": "재무서류", "kind": "text"},
        ],
    })])

    selected, _ = legal_conditional_closure.select(
        index, "재무요건은?", [_branch(index, 1)],
        [_branch(index, 2, ("재무서류",), mandatory=False)])

    assert selected == []


def test_conditional_D는_verifier가_고유참조를_확정하면_열지_않는다():
    index = Index.from_docs([("d", {"name": "시험법", "kind": "law"}, {
        "nodes": [
            {"id": 1, "parent": None, "surface": "제1조", "span": [0, 1]},
            {"id": 2, "parent": None, "surface": "제2조", "span": [1, 2]},
        ],
        "blocks": [
            {"idx": 0, "text": "보수 준용", "kind": "text"},
            {"idx": 1, "text": "보수 경쟁 조문", "kind": "text"},
        ],
    })])
    verified = _branch(index, 1, ("보수",), mandatory=True)
    verified = replace(verified, origin="normative-reference-verifier")

    selected, audit = legal_conditional_closure.select(
        index, "보수 준용", [verified],
        [_branch(index, 2, ("보수",), mandatory=True)])

    assert selected == []
    assert audit["fallback"] == "verified_reference_already_closes_relation_need"


def test_conditional_D는_존재여부_질문의_질문근거_대조조문을_허용한다():
    index = Index.from_docs([("d", {"name": "시험법", "kind": "law"}, {
        "nodes": [
            {"id": 1, "parent": None, "surface": "제1조", "span": [0, 1]},
            {"id": 2, "parent": None, "surface": "제2조", "span": [1, 2]},
        ],
        "blocks": [
            {"idx": 0, "text": "전문투자자 의무보유", "kind": "text"},
            {"idx": 1, "text": "벤처금융 전문투자자 의무보유", "kind": "text"},
        ],
    })])

    selected, audit = legal_conditional_closure.select(
        index, "벤처금융에도 전문투자자 의무보유 규정이 있는가?",
        [_branch(index, 1)],
        [_branch(index, 2, ("벤처금융", "전문투자자"), mandatory=False)])

    assert [row.node for row in selected] == [2]
    assert audit["asks_comparison_or_existence"] is True


def test_conditional_D는_문서근거_질문에만_복수_관계를_허용한다():
    nodes = [{"id": i, "parent": None, "surface": f"제{i}조", "span": [i-1, i]}
             for i in range(1, 5)]
    index = Index.from_docs([("d", {"name": "시험법", "kind": "law"}, {
        "nodes": nodes,
        "blocks": [{"idx": i-1, "text": f"시장 {i} 재무서류 제출",
                    "kind": "text"} for i in range(1, 5)],
    })])
    candidates = [_branch(index, node, mandatory=True) for node in (2, 3, 4)]

    selected, audit = legal_conditional_closure.select(
        index, "거래소별 제출서류 범위는?", [_branch(index, 1)], candidates, cap=1)

    assert [row.node for row in selected] == [2, 3, 4]
    assert audit["asks_document_evidence"] is True
    assert audit["cap"] == 6
