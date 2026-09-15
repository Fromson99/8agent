from types import SimpleNamespace

from lawrag.core.rag import (
    legal_coordinates,
    legal_evidence,
    legal_references,
    legalclosure,
    termexplore,
)
from lawrag.core.rag.index import Index


def _branch(idx, node, origin):
    return termexplore._branch(idx, "d", node, (), origin=origin)


def test_merge_조문좌표를_접고_채널_우선순위와_상한을_지킨다():
    idx = Index.from_docs([("d", {"name": "시험법"}, {
        "nodes": [
            {"id": 1, "parent": None, "level": 1,
             "surface": "제1조", "title": "원칙", "span": [0, 1]},
            {"id": 2, "parent": None, "level": 1,
             "surface": "제2조", "title": "예외", "span": [1, 2]},
            {"id": 3, "parent": None, "level": 1,
             "surface": "제3조", "title": "절차", "span": [2, 3]},
        ],
        "blocks": [
            {"idx": 0, "text": "원칙", "kind": "text"},
            {"idx": 1, "text": "예외", "kind": "text"},
            {"idx": 2, "text": "절차", "kind": "text"},
        ],
    })])

    selected = legal_coordinates.merge(
        2, [_branch(idx, 1, "primary")],
        [_branch(idx, 1, "duplicate"), _branch(idx, 2, "assertion")],
        [_branch(idx, 3, "keyword")])

    assert [(row.node, row.origin) for row in selected] == [
        (1, "primary"), (2, "assertion")]


def test_article_branch_구판_assertion_좌표를_같은_조의_현행본에_재결합한다():
    def doc(text):
        return {"nodes": [{"id": 1, "parent": None, "level": 1,
                           "surface": "제8조", "title": "운영", "span": [0, 1]}],
                "blocks": [{"idx": 0, "text": text, "kind": "text"}]}
    idx = Index.from_docs([
        ("old", {"name": "시험법", "kind": "law", "status": "구판"}, doc("옛 본문")),
        ("new", {"name": "시험법", "kind": "law", "status": "현행"}, doc("새 본문")),
    ]).scoped(None)

    row = legal_coordinates.article_branch(
        idx, "old", 1, (), origin="assertion-tree")

    assert row is not None
    assert row.doc_id == "new"
    assert "새 본문" in row.body


def test_question_terms_법률_합성명사_뒤의_조사를_제거한다():
    terms = legalclosure._question_terms("질적심사요건과 보유기간이 필요한가?")

    assert "질적심사요건" in terms
    assert "보유기간" in terms


def test_context_terms_업무문맥만_보충하고_조사를_제거한다():
    terms = legalclosure._context_terms(
        "무엇인가?\n(업무 문맥: 질적심사요건과 사내규정 정비)")

    assert terms == ("질적심사요건과", "질적심사요건", "사내규정", "정비")


def test_retrieve_검증_primary_cap_12와_사용자_scope를_보존한다(monkeypatch):
    idx = Index.from_docs([
        ("a", {"name": "가법"}, {"nodes": [], "blocks": []}),
        ("b", {"name": "나법"}, {"nodes": [], "blocks": []}),
    ]).scoped({"a"}, name="가법만")
    seen = {}

    def primary(index, question, *, llm, cap):
        seen["primary_scope"] = index.scope
        seen["primary_cap"] = cap
        return [], {"term_plan": {"used_terms": []}}

    def assertion(index, question, registry, *, llm, cap):
        seen["assertion_scope"] = index.scope
        seen["assertion_cap"] = cap
        return [], {}

    monkeypatch.setattr(legalclosure.termexplore, "retrieve", primary)
    monkeypatch.setattr(legalclosure.assertionfirst, "retrieve", assertion)
    monkeypatch.setattr(legalclosure.general_search, "extract_keywords",
                        lambda llm, question: SimpleNamespace(as_dict=lambda: {}))
    monkeypatch.setattr(legalclosure, "_keyword_articles", lambda *args: ([], {}))
    monkeypatch.setattr(legalclosure, "_supplemental_closure", lambda *args: ([], {}))

    sections, meta = legalclosure.retrieve(idx, "질문", object(), llm=None)

    assert sections == [] and meta["cap"] == 20
    assert seen == {
        "primary_scope": frozenset({"a"}), "primary_cap": 12,
        "assertion_scope": frozenset({"a"}), "assertion_cap": 8,
    }


def test_supplemental_closure_동반의_출발좌표를_보존한다(monkeypatch):
    idx = Index.from_docs([("d", {"name": "시험법"}, {
        "nodes": [
            {"id": 1, "parent": None, "surface": "제1조", "span": [0, 1]},
            {"id": 2, "parent": None, "surface": "제2조", "span": [1, 2]},
        ],
        "blocks": [
            {"idx": 0, "text": "제1조 원칙", "kind": "text"},
            {"idx": 1, "text": "제2조 예외", "kind": "text"},
        ],
    })])
    seed = _branch(idx, 1, "keyword")
    expanded = termexplore._branch(
        idx, "d", 2, (), origin="reference:outgoing:배제",
        mandatory=True, mandatory_reason="relation:배제")
    monkeypatch.setattr(
        legalclosure.termexplore, "expand_structural",
        lambda *args, **kwargs: ([expanded], {"events": []}))

    rows, _ = legalclosure._supplemental_closure(idx, [seed], ())

    assert len(rows) == 1
    assert (rows[0].source_doc_id, rows[0].source_node) == ("d", 1)


def test_top20_병합은_일반후보보다_필수동반의_슬롯을_예약한다():
    idx = Index.from_docs([("d", {"name": "시험법"}, {
        "nodes": [
            {"id": node, "parent": None, "surface": f"제{node}조",
             "span": [node - 1, node]} for node in range(1, 5)
        ],
        "blocks": [
            {"idx": node - 1, "text": f"제{node}조", "kind": "text"}
            for node in range(1, 5)
        ],
    })])
    preferred = [_branch(idx, node, "primary") for node in (1, 2, 3)]
    required = [termexplore._branch(
        idx, "d", 4, (), origin="unified-relation:위임",
        mandatory=True, mandatory_reason="relation:위임")]

    selected = legalclosure._merge_with_required(3, preferred, required)

    assert [row.node for row in selected] == [1, 2, 4]
    assert selected[-1].mandatory is True


def test_reference_requirement_rescue_준용표제의_고유한_질문대상만_연다():
    idx = Index.from_docs([("d", {"name": "시험법", "kind": "law"}, {
        "nodes": [
            {"id": 1, "parent": None, "level": 1,
             "surface": "제10조", "title": "준용규정", "span": [0, 1]},
            {"id": 2, "parent": None, "level": 1,
             "surface": "제20조", "title": "이사의 보수", "span": [1, 2]},
            {"id": 3, "parent": None, "level": 1,
             "surface": "제21조", "title": "이사의 책임", "span": [2, 3]},
        ],
        "blocks": [
            {"idx": 0, "text": "제20조와 제21조는 감사에 준용한다.", "kind": "text"},
            {"idx": 1, "text": "보수는 주주총회에서 정한다.", "kind": "text"},
            {"idx": 2, "text": "책임을 진다.", "kind": "text"},
        ],
    })])
    idx._refs = {"d": [
        {"src": 1, "dst": 2, "surface": "제20조", "block": 0, "rel": "인용"},
        {"src": 1, "dst": 3, "surface": "제21조", "block": 0, "rel": "인용"},
    ]}
    seed = _branch(idx, 1, "assertion-tree")

    question = "감사의 보수를 이사회에 위임할 수 있는가?"
    rows, meta = legal_references.requirement_rescue(
        idx, question, [seed], ("감사 보수",), cap=1,
        question_terms=legalclosure._question_terms(question))

    assert [(row.node, row.origin) for row in rows] == [
        (2, "normative-reference-verifier")]
    assert meta["fallback"] == ""


def test_legal_annotations_원문요건과_법원성메타를_좌표에_붙인다():
    idx = Index.from_docs([("d", {"name": "시험법", "kind": "law",
                                  "enforce": "20250101", "revised": "20250101"}, {
        "nodes": [{"id": 1, "parent": None, "surface": "제1조", "span": [0, 1]}],
        "blocks": [{"idx": 0, "text": "10일 이내에 서면으로 제출하여야 한다.",
                    "kind": "text"}],
    })])
    branch = _branch(idx, 1, "primary")

    meta = legal_evidence.annotate(
        idx, "2024-12-31 기준 제출기한은?", [branch])

    assert meta["rows"][0]["validity"]["temporal_status"] == "not_yet_effective"
    assert {"TIME", "METHOD"}.issubset(meta["rows"][0]["present_kinds"])
