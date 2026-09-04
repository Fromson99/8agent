"""정의 조는 일반 근거에서 분리하고 선택 규정의 필요한 정의만 부록으로 준다."""

from lawrag.core.rag import answer, definitions, legalclosure, termexplore
from lawrag.core.rag.answer import Section
from lawrag.core.rag.index import Index


def _index():
    return Index.from_docs([("d", {"name": "증권 인수업무 등에 관한 규정"}, {
        "nodes": [
            {"id": 1, "parent": None, "level": 1, "surface": "제1조",
             "title": "정의", "span": [0, 3]},
            {"id": 2, "parent": None, "level": 1, "surface": "제2조",
             "title": "인수업무", "span": [3, 4]},
            {"id": 3, "parent": None, "level": 1, "surface": "제3조",
             "title": "보고", "span": [4, 5]},
        ],
        "blocks": [
            {"idx": 0, "text": "제1조(정의) 이 규정에서 사용하는 용어의 뜻은 다음과 같다.",
             "kind": "text"},
            {"idx": 1, "text": '1. "주관회사"란 증권의 인수업무를 총괄하는 회사를 말한다.',
             "kind": "text"},
            {"idx": 2, "text": '2. "수요예측"이란 공모가격 결정을 위한 조사를 말한다.',
             "kind": "text"},
            {"idx": 3, "text": "제2조(인수업무) 주관회사는 인수업무를 수행하여야 한다.",
             "kind": "text"},
            {"idx": 4, "text": "제3조(보고) 회사는 결과를 보고하여야 한다.",
             "kind": "text"},
        ],
    })])


def _branch(index, node, origin="test"):
    return termexplore._branch(index, "d", node, (), origin=origin)


def test_일반질문은_정의조를_최종근거에서_제외한다():
    index = _index()
    kept, dropped = legalclosure._without_definition_articles(
        index, "주관회사가 인수업무를 해야 하나?",
        [_branch(index, 1), _branch(index, 2)])

    assert [row.node for row in kept] == [2]
    assert [row["node"] for row in dropped] == [1]


def test_정의직접질문은_정의조를_그대로_허용한다():
    index = _index()
    kept, dropped = legalclosure._without_definition_articles(
        index, "주관회사의 정의는 무엇인가?", [_branch(index, 1)])

    assert [row.node for row in kept] == [1]
    assert dropped == []


def test_선택조문에서_쓰인_정의만_원문좌표와_함께_붙는다():
    index = _index()
    view = index.docs["d"]
    rows = definitions.context_entries(
        view, "인수업무 의무는?", [2])

    assert [row["term"] for row in rows] == ["주관회사"]
    assert rows[0]["doc"] == "증권 인수업무 등에 관한 규정"
    assert rows[0]["block"] == 1
    assert rows[0]["quote"] == '1. "주관회사"란 증권의 인수업무를 총괄하는 회사를 말한다.'
    assert "수요예측" not in {row["term"] for row in rows}


def test_질문에_정의어가_있으면_같은조문의_다른정의는_보태지_않는다():
    index = _index()
    view = index.docs["d"]
    rows = definitions.context_entries(
        view, "주관회사 의무는?", [2])

    assert [row["term"] for row in rows] == ["주관회사"]
    assert rows[0]["matched_in"] == ["question", "selected_provision"]


def test_정의부록은_독립인용번호_없이_별도블록으로_렌더링한다():
    index = _index()
    view = index.docs["d"]
    section = Section(
        n=1, doc_id="d", doc=view.name, node=2, path=view.path(2), page=None,
        kind="법률좌표폐쇄", matched="test", text=view.section_text(view.by_id[2]),
        definition_context=definitions.context_entries(view, "인수업무 의무는?", [2]))

    rendered = answer._definition_context_text([section])

    assert "해석 보조, 독립 인용 근거 아님" in rendered
    assert "용어: 주관회사" in rendered
    assert "정의 원문:" in rendered
    assert "[2]" not in rendered


def test_정의조를_제거한_문서만_부록대상이_된다():
    index = _index()
    view = index.docs["d"]
    section = Section(
        n=1, doc_id="d", doc=view.name, node=2, path=view.path(2), page=None,
        kind="법률좌표폐쇄", matched="test", text=view.section_text(view.by_id[2]))

    assert legalclosure._attach_definition_context(
        index, "주관회사 의무는?", [section], eligible_doc_ids=set()) == []
    rows = legalclosure._attach_definition_context(
        index, "주관회사 의무는?", [section], eligible_doc_ids={"d"})
    assert [row["term"] for row in rows] == ["주관회사"]
