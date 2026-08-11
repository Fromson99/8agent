"""RAG 질의 경로 — 검색 사다리·조립·인용의 계약을 시험한다.

LLM 은 부르지 않는다. 검색과 조립은 결정론이라 그대로 시험하고, LLM 이
필요한 자리(필터·합성)는 **없을 때의 행동**(생략·정직한 실패)을 시험한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.rag import answer as answer_mod          # noqa: E402
from core.rag.index import DocView, Index, norm    # noqa: E402
from core.rag.search import search, similarity     # noqa: E402


# ---------------------------------------------------------------- 재료
def _doc():
    nodes = [
        {"id": 1, "parent": None, "level": 1, "surface": "제2장",
         "title": "영업행위 준수사항", "page": 1, "span": [0, 6]},
        {"id": 2, "parent": 1, "level": 2, "surface": "제19조",
         "title": "설명의무", "page": 1, "span": [1, 3]},
        {"id": 3, "parent": 1, "level": 2, "surface": "제21조",
         "title": "부당권유행위 금지", "page": 2, "span": [3, 6]},
    ]
    blocks = [
        {"idx": 0, "page": 1, "text": "제2장 영업행위 준수사항", "kind": "text"},
        {"idx": 1, "page": 1, "text": "제19조(설명의무) 금융상품판매업자등은", "kind": "text"},
        {"idx": 2, "page": 1, "text": "중요한 사항을 이해할 수 있도록 설명하여야 한다.", "kind": "text"},
        {"idx": 3, "page": 2, "text": "제21조(부당권유행위 금지)", "kind": "text"},
        {"idx": 4, "page": 2, "text": "단정적 판단을 제공하는 행위 금지", "kind": "text"},
        {"idx": 5, "page": 2, "text": "청약철회권 행사 기간은 계약일로부터 7일", "kind": "text"},
    ]
    return ("d1", {"name": "KSB.pdf"}, {"nodes": nodes, "blocks": blocks})


def _doc_ascii():
    nodes = [{"id": 1, "parent": None, "level": 1, "surface": "1.",
              "title": "ER", "page": 1, "span": [0, 1]}]
    blocks = [{"idx": 0, "page": 1, "text": "ER 절차", "kind": "text"}]
    return ("d2", {"name": "EN.pdf"}, {"nodes": nodes, "blocks": blocks})


def _index(user_terms=None):
    return Index.from_docs([_doc(), _doc_ascii()], user_terms or [])


# ---------------------------------------------------------------- 검색 사다리
def test_정확_일치_색인값이_질의_안에():
    r = search(_index(), "부당권유행위 금지가 뭐야?")
    assert r.mode == "정확"
    top = r.hits[0]
    assert top.value == "부당권유행위 금지"
    assert (top.doc_id, top.node) == ("d1", 3)


def test_정확_일치는_공백_흔들림을_넘는다():
    # `부당 권유행위` 로 띄어 써도 같은 말이다 — norm 이 잇는다.
    r = search(_index(), "부당 권유행위 금지 조항 알려줘")
    assert r.mode == "정확"
    assert r.hits[0].value == "부당권유행위 금지"


def test_정확이_있으면_부분은_돌지_않는다():
    r = search(_index(), "설명의무에 대해 설명해줘")
    assert r.mode == "정확"
    assert [s["stage"] for s in r.ladder] == ["정확 일치"]


def test_ascii_값은_낱말_경계를_요구한다():
    # 'ER' 이 'filtER' 안에 있다고 잡히면 안 된다.
    r = search(_index(), "filter 교체 주기")
    assert all(h.value != "ER" for h in r.hits)
    # 낱말로 서 있으면 잡힌다 — 한글 조사가 붙어도 경계다.
    r2 = search(_index(), "ER 절차가 뭐야")
    assert r2.mode == "정확" and r2.hits[0].value == "ER"


def test_부분_일치_토큰이_색인값_안에():
    # "부당권유 금지" — 어느 색인값도 질의에 통째로 없지만 토큰은 겹친다.
    r = search(_index(), "부당권유 금지")
    assert r.mode == "부분"
    assert r.hits[0].value == "부당권유행위 금지"
    assert r.hits[0].score <= 1.0


def test_본문_폴백_블록에서_찾는다():
    # '청약철회권' 은 제목·용어 어디에도 없고 본문 블록에만 있다.
    r = search(_index(), "청약철회권 행사")
    assert r.mode == "본문"
    top = r.hits[0]
    assert top.block == 5 and top.node == 3          # 덮는 마디로 되짚는다
    # ③단은 하이브리드 개편(2026-08)으로 이름이 바뀌었다 — 벡터 색인이 없는
    # 이 시험 환경에서는 렉시컬만 돌고 동작은 예전 그대로다.
    assert [s["stage"] for s in r.ladder] == ["정확 일치", "부분 일치", "본문+벡터"]


def test_빈_질의와_빗나간_질의():
    assert search(_index(), "").mode == "없음"
    assert search(_index(), "존재하지않는외계어구절").mode == "없음"


def test_trigram_정의():
    assert similarity("부당권유금지", "부당권유금지") == 1.0
    assert similarity("", "부당") == 0.0
    assert 0.0 < similarity("부당권유금지", "부당권유행위금지") < 1.0


def test_용어_엔트리는_출현_좌표를_실어온다():
    terms = [{"term": "청약철회권", "key": norm("청약철회권"), "occurrences": [
        {"doc_id": "d1", "doc": "KSB.pdf", "node": 3, "page": 2,
         "block": 5, "via": "본문"}]}]
    r = search(_index(terms), "청약철회권이 뭐야?")
    assert r.mode == "정확"
    assert r.hits[0].kind == "용어"
    assert r.hits[0].occurrences[0]["block"] == 5


# ---------------------------------------------------------------- 조립·인용
def test_조립_같은_마디는_한_번만():
    idx = _index([{"term": "부당권유행위 금지", "key": norm("부당권유행위 금지"),
                   "occurrences": [{"doc_id": "d1", "doc": "KSB.pdf",
                                    "node": 3, "page": 2, "block": 3, "via": "제목"}]}])
    r = search(idx, "부당권유행위 금지가 뭐야?")
    sections = answer_mod.assemble(idx, r)
    keys = [(s.doc_id, s.node) for s in sections]
    assert len(keys) == len(set(keys))               # (문서, 마디) 중복 없음
    assert any(s.node == 3 for s in sections)


def test_조립_경로와_본문():
    idx = _index()
    r = search(idx, "부당권유행위 금지가 뭐야?")
    s = answer_mod.assemble(idx, r)[0]
    assert s.path == "영업행위 준수사항 ▸ 부당권유행위 금지"
    assert "단정적 판단" in s.text                    # span 의 블록이 본문이 된다
    assert s.n == 1 and s.page == 2


def test_경로는_조상_사슬():
    v = DocView.build(*_doc())
    assert v.path(3) == "영업행위 준수사항 ▸ 부당권유행위 금지"
    assert v.path(1) == "영업행위 준수사항"
    assert v.path(None) == ""


# ---------------------------------------------------------------- LLM 없는 자리
def test_필터는_LLM_없으면_생략():
    idx = _index()
    r = search(idx, "부당권유행위 금지가 뭐야?")
    sections = answer_mod.assemble(idx, r)
    kept, meta = answer_mod.filter_sections(None, "질문", sections)
    assert kept == sections and meta["applied"] is False


def test_합성은_LLM_없으면_정직하게_실패():
    idx = _index()
    r = search(idx, "부당권유행위 금지가 뭐야?")
    sections = answer_mod.assemble(idx, r)
    ans = answer_mod.synthesize(None, "질문", sections)
    assert ans.error and not ans.answerable


def test_회수_없음은_부재_단정이_아니다():
    ans = answer_mod.synthesize(None, "질문", [])
    # §0-0 ② — "문서에 없다" 가 아니라 "이번 검색으로는 회수되지 않았다".
    assert "회수되지 않았" in ans.answer
    assert not ans.answerable


def test_라우터가_두_앱에_실린다():
    sys.path.insert(0, str(ROOT))
    from api.routers import rag as rag_router
    paths = {r.path for r in rag_router.router.routes}
    assert "/v1/rag/search" in paths and "/v1/rag/ask" in paths
