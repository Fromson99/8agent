"""조문 상호참조 — 본문의 "제4조를 참고한다" 가 구역 간선으로 서고,
회수가 그 간선을 타고 참조 구역을 같이 드는지 시험한다. 문서 사이는
이름 대조가 확정하고, 못 정한 것은 보류 → 판정(judge)으로 넘어간다."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.rag import judge, refs                   # noqa: E402
from core.rag.answer import assemble               # noqa: E402
from core.rag.graph import Graph                   # noqa: E402
from core.rag.index import Index                   # noqa: E402
from core.rag.search import Hit, SearchResult      # noqa: E402


def _doc():
    """법령 모양 문서 — 장/조/항 계층, 부칙(번호 겹침), 별표."""
    return ("d1", {"name": "TRUST.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제1장",
         "title": "총칙", "page": 1, "span": [0, 5]},
        {"id": 2, "parent": 1, "level": 2, "surface": "제1조",
         "title": "목적", "page": 1, "span": [1, 2]},
        {"id": 3, "parent": 1, "level": 2, "surface": "제2조",
         "title": "정의", "page": 1, "span": [2, 3]},
        {"id": 9, "parent": 3, "level": 3, "surface": "①",
         "title": "", "page": 1, "span": [2, 3]},
        {"id": 4, "parent": 1, "level": 2, "surface": "제4조",
         "title": "신탁의 설정", "page": 2, "span": [3, 4]},
        {"id": 5, "parent": 1, "level": 2, "surface": "제4조의2",
         "title": "특례", "page": 2, "span": [4, 5]},
        {"id": 6, "parent": None, "level": 1, "surface": "부칙",
         "title": "", "page": 3, "span": [5, 7]},
        {"id": 7, "parent": 6, "level": 2, "surface": "제1조",
         "title": "시행일", "page": 3, "span": [6, 7]},
        {"id": 8, "parent": None, "level": 1, "surface": "별표 1",
         "title": "수수료율", "page": 4, "span": [7, 8]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제1장 총칙", "kind": "text"},
        {"idx": 1, "page": 1, "text": "제1조(목적) 이 약관은 신탁계약의 내용을 정한다.",
         "kind": "text"},
        {"idx": 2, "page": 1, "text": "제2조(정의) ① 그 밖의 용어는 제4조와 별표 1을 "
         "참고하고, 제1조의 목적을 따른다. 「신탁법」 제10조와 동법 제12조는 별개다.",
         "kind": "text"},
        {"idx": 3, "page": 2, "text": "제4조(신탁의 설정) 신탁은 계약으로 설정한다.",
         "kind": "text"},
        {"idx": 4, "page": 2, "text": "제4조의2(특례) 제4조에도 불구하고 특례를 둘 수 있다. "
         "보수는 「수수료규정」 제2조에 따르고, 동법 제12조를 준용한다.", "kind": "text"},
        {"idx": 5, "page": 3, "text": "부칙", "kind": "text"},
        {"idx": 6, "page": 3, "text": "이 약관은 공포한 날부터 시행하며, "
         "제2조제1항은 시행일부터 적용한다.", "kind": "text"},
        {"idx": 7, "page": 4, "text": "별표 1 수수료율", "kind": "text"},
    ]})


def _d2():
    """d1 이 「수수료규정」 으로 부르는 문서 — 이름 대조의 상대."""
    return ("d2", {"name": "수수료규정.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제2조",
         "title": "보수", "page": 1, "span": [0, 1]},
        {"id": 2, "parent": None, "level": 1, "surface": "제12조",
         "title": "정산", "page": 2, "span": [1, 2]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제2조(보수) 보수는 수수료규정 제12조에 따라 "
         "정산한다.", "kind": "text"},
        {"idx": 1, "page": 2, "text": "제12조(정산) 정산은 분기별로 한다.", "kind": "text"},
    ]})


def _d3():
    """제12조를 하나 더 가진 문서 — 동법 제12조 를 애매하게 만든다."""
    return ("d3", {"name": "위탁계약서.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제12조",
         "title": "손해배상", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제12조(손해배상) 수탁자는 손해를 배상한다.",
         "kind": "text"},
    ]})


def _index():
    return Index.from_docs([_doc()])


def _corpus():
    return Index.from_docs([_doc(), _d2(), _d3()])


# ------------------------------------------------------------------ 찾기
def test_찾기_조_가지_항():
    r = refs.find("제 4 조를 참고한다")[0]                 # 자간 벌어짐
    assert (r.unit, r.n) == ("조", 4)
    r = refs.find("제4조의2제3항에 따른다")[0]             # 가지조문 + 항
    assert (r.n, r.sub, r.chain) == (4, 2, (("항", 3),))
    units = {(r.unit, r.n) for r in refs.find("제3장과 별지 제2호를 따른다")}
    assert ("장", 3) in units and ("별지", 2) in units


def test_찾기_사슬_호목_표면형():
    r = refs.find("제1조제1항제2호나목을 따른다")[0]
    assert r.chain == (("항", 1), ("호", 2), ("목", 2))
    assert r.surface == "제1조제1항제2호나목"              # 링크 글자가 사슬 전체를 덮는다
    assert refs.find("제1조 2목에 따른다")[0].chain == (("목", 2),)
    assert refs.find("제1조 (2) 를 준용한다")[0].chain == ((None, 2),)
    assert refs.find("제2조 ①에 따른다")[0].chain == (("항", 1),)
    assert refs.find("제1조(목적) 이 약관은")[0].chain == ()     # 제목 괄호는 참조가 아니다
    assert refs.find("제4조 다목적 설비 기준")[0].chain == ()   # "다목적" 은 목이 아니다


def test_찾기_열거와_범위():
    rs = refs.find("제22조제1항ㆍ제3항 또는 제4항을 위반하면")
    assert [r.chain for r in rs] == [(("항", 1),), (("항", 3),), (("항", 4),)]
    assert {r.n for r in rs} == {22}                  # 셋 다 제22조의 가지다
    rs = refs.find("제2조제6호가목ㆍ다목ㆍ마목, 같은 조 제7호라목")
    assert [r.chain for r in rs] == [                 # "같은 조" 는 대용어 — 멈춘다
        (("호", 6), ("목", 1)), (("호", 6), ("목", 3)), (("호", 6), ("목", 5))]
    rs = refs.find("「형법」 제129조부터 제132조까지의 규정을 적용한다")
    assert all(r.external and r.hint == "형법" for r in rs)   # 이름이 뒤 끝도 덮는다
    rs = refs.find("근로자퇴직급여보장법 시행령 제13조의4 및 제13조의6에 따른")
    assert rs[0].hint == "근로자퇴직급여보장법 시행령"          # 두 단어 이름
    assert rs[1].external and rs[1].hint == rs[0].hint
    assert (rs[1].n, rs[1].sub) == (13, 6)
    assert refs.find("퇴직연금감독규정시행세칙 제5조의2에 따른")[0].external
    assert refs.find("영 제34조에 따라")[0].external           # 이하 '영' — 대용어


def test_찾기_단서를_사이에_둔_열거도_이름이_덮는다():
    """"법 제81조제1항 단서 및 제234조제4항" — 단서(부속 표현)가 끼어도
    앞의 '법'이 뒤 끝을 덮는다. 끊기면 뒤 참조가 이 문서의 같은 번호 조로
    잘못 붙는다(시행령 운용특례에서 실측된 오연결)."""
    rs = refs.find("법 제81조제1항 단서 및 제234조제4항에 따라 운용할 수 있다")
    assert [(r.n, r.external, r.hint) for r in rs] == [
        (81, True, "법"), (234, True, "법")]
    rs = refs.find("제22조제1항 본문 및 제3항을 준용한다")
    assert [r.chain for r in rs] == [(("항", 1),), (("항", 3),)]
    assert {r.n for r in rs} == {22}          # 본문이 끼어도 같은 조의 열거다


def test_찾기_외부참조는_표시된다():
    r = refs.find("「신탁법」 제10조에 따라")[0]
    assert r.external and r.hint == "신탁법"          # 문서 힌트 — 문서 사이 대조의 재료
    assert refs.find("동법 제12조를 준용한다")[0].hint == "동법"
    assert refs.find("자본시장법 제9조의 신탁업자")[0].external
    long_title = "「" + "가" * 45 + "」 제9조에 따른다"
    assert refs.find(long_title)[0].external          # 제목이 창보다 길어도 외부는 안다
    assert refs.find("동법 별표 1의 요율")[0].external  # 별표·별지도 앞말을 본다
    assert not refs.find("이 약관 제6조를 따른다")[0].external   # 이 문서 자신
    assert not refs.find("그 절차는 제6조를 따른다")[0].external


# ------------------------------------------------------------------ 해소
def _edges():
    view = _index().docs["d1"]
    return refs.resolve(view)


def test_해소_가로참조만_잇는다():
    pairs = {(e["src"], e["dst"]) for e in _edges()}
    assert (9, 4) in pairs                    # 제2조① → 제4조
    assert (9, 8) in pairs                    # 제2조① → 별표 1
    assert (5, 4) in pairs                    # 제4조의2 → 제4조 (의2 는 자기라 빠짐)
    # 조문 제목 블록의 자기 번호("제4조(신탁의 설정)")는 간선이 아니다
    assert all(src != dst for src, dst in pairs)
    # 외부 참조(「신탁법」 제10조·동법 제12조)는 잇지 않는다 — 10·12 대상 없음
    assert all(dst in {2, 4, 8, 9} for _, dst in pairs)


def test_해소_번호가_겹치면_가까운_조상():
    pairs = {(e["src"], e["dst"]) for e in _edges()}
    assert (9, 2) in pairs                    # 본문의 "제1조" → 본문 제1조(2)
    assert (9, 7) not in pairs                # 부칙 제1조(7)가 아니다


def test_해소_항까지_내려간다():
    pairs = {(e["src"], e["dst"]) for e in _edges()}
    assert (7, 9) in pairs                    # 부칙의 "제2조제1항" → 제2조의 ①


def _deep():
    """항·호·목이 실제로 있는 문서 — 사슬 하강의 무대."""
    return ("d4", {"name": "시행세칙.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "구분", "page": 1, "span": [0, 6]},
        {"id": 2, "parent": 1, "level": 2, "surface": "①",
         "title": "", "page": 1, "span": [1, 6]},
        {"id": 3, "parent": 2, "level": 3, "surface": "1.",
         "title": "", "page": 1, "span": [2, 3]},
        {"id": 4, "parent": 2, "level": 3, "surface": "2.",
         "title": "", "page": 1, "span": [3, 6]},
        {"id": 5, "parent": 4, "level": 4, "surface": "가.",
         "title": "", "page": 1, "span": [4, 5]},
        {"id": 6, "parent": 4, "level": 4, "surface": "나.",
         "title": "", "page": 1, "span": [5, 6]},
        {"id": 7, "parent": None, "level": 1, "surface": "제2조",
         "title": "적용", "page": 2, "span": [6, 10]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제1조(구분) 기준은 다음과 같다.", "kind": "text"},
        {"idx": 1, "page": 1, "text": "① 다음 각 호로 구분한다.", "kind": "text"},
        {"idx": 2, "page": 1, "text": "1. 첫째 기준", "kind": "text"},
        {"idx": 3, "page": 1, "text": "2. 둘째 기준은 다음 각 목과 같다.", "kind": "text"},
        {"idx": 4, "page": 1, "text": "가. 하나", "kind": "text"},
        {"idx": 5, "page": 1, "text": "나. 둘", "kind": "text"},
        {"idx": 6, "page": 2, "text": "제2조(적용) 위임 사무는 제1조제1항제2호나목을 "
         "따른다.", "kind": "text"},
        {"idx": 7, "page": 2, "text": "수수료는 제1조 (2) 를 준용한다.", "kind": "text"},
        {"idx": 8, "page": 2, "text": "제1조제3항은 아직 없다.", "kind": "text"},
        {"idx": 9, "page": 2, "text": "그 절차는 제1조제1항제1호 및 제2호가목을 "
         "따른다.", "kind": "text"},
    ]})


def test_해소_사슬은_실존까지_내려간다():
    view = Index.from_docs([_deep()]).docs["d4"]
    got = {(e["src"], e["dst"], e["surface"]) for e in refs.resolve(view)}
    assert (7, 6, "제1조제1항제2호나목") in got   # 조→항→호→목 끝까지
    assert (7, 4, "제1조 (2)") in got            # 표면형 (2) — 서수로 물어 제2호
    assert (7, 1, "제1조제3항") in got           # ③은 없다 — 조에 머문다, 버리지 않는다
    assert (7, 3, "제1조제1항제1호") in got      # 열거의 앞 끝
    assert (7, 5, "제2호가목") in got            # "및 제2호가목" — 같은 조의 다른 가지


def test_해소_동률은_사슬_실존으로_가른다():
    """본문과 개정문이 같은 번호의 조를 가질 때(조상 공유 0 동률) —
    사슬이 실제로 내려가지는 제2조가 그 제2조다. KSB 실측 사례."""
    doc = ("d6", {"name": "금소법.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "총칙",
         "title": "", "page": 1, "span": [0, 3]},
        {"id": 2, "parent": 1, "level": 2, "surface": "제2조",
         "title": "정의", "page": 1, "span": [0, 3]},
        {"id": 3, "parent": 2, "level": 3, "surface": "1.",
         "title": "", "page": 1, "span": [1, 3]},
        {"id": 4, "parent": 3, "level": 4, "surface": "가.",
         "title": "", "page": 1, "span": [2, 3]},
        {"id": 5, "parent": None, "level": 1, "surface": "<제9999호>",
         "title": "", "page": 2, "span": [3, 4]},
        {"id": 6, "parent": 5, "level": 2, "surface": "제2조",
         "title": "", "page": 2, "span": [3, 4]},
        {"id": 7, "parent": None, "level": 1, "surface": "감독",
         "title": "", "page": 3, "span": [4, 5]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제2조(정의)", "kind": "text"},
        {"idx": 1, "page": 1, "text": "1. 예금성 상품", "kind": "text"},
        {"idx": 2, "page": 1, "text": "가. 은행법에 따른 예금", "kind": "text"},
        {"idx": 3, "page": 2, "text": "<제9999호> 제2조 중 일부를 개정한다.",
         "kind": "text"},
        {"idx": 4, "page": 3, "text": "감독 대상은 제2조제1호가목에 따른다.",
         "kind": "text"},
    ]})
    view = Index.from_docs([doc]).docs["d6"]
    pairs = {(e["src"], e["dst"]) for e in refs.resolve(view)}
    assert (7, 4) in pairs                    # 빈 제2조(6)가 아니라 정의의 가목(4)


def test_문서사이_총칭_힌트는_확정하지_않는다():
    """"법 제2조"의 '법'은 이름이 아니라 대용어 — 이름에 '법'이 든 문서가
    있어도 확정하지 않고 보류로 보낸다."""
    caller = ("d7", {"name": "약정서.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제1조 이 약정은 법 제2조에 따른다.",
         "kind": "text"},
    ]})
    law = ("d8", {"name": "금융소비자보호법.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제2조",
         "title": "정의", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제2조(정의)", "kind": "text"},
    ]})
    edges, pending = refs.cross_resolve(Index.from_docs([caller, law]).docs)
    assert not any(e["src_doc"] == "d7" for e in edges)
    rows = [p for p in pending if p["src_doc"] == "d7"]
    assert rows and rows[0]["hint"] == "법"
    assert {(c["doc_id"], c["node"]) for c in rows[0]["candidates"]} == {("d8", 1)}


def test_문서사이_총칭_힌트는_종별로_후보를_거른다():
    """"법 제238조"의 '법'은 법률을 부른 것이다 — 시행령이 같은 번호의 조를
    가져도 후보가 아니다. 종별 접미(법·령·규칙…)는 문서 무관 명명 관례다."""
    caller = ("p1", {"name": "상품설명서.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "1.",
         "title": "", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "1. 법 제238조에 따라 평가한 집합투자재산의 "
         "평가이익", "kind": "text"},
    ]})
    law = ("p2", {"name": "자본시장과 금융투자업에 관한 법률.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제238조",
         "title": "집합투자재산의 평가", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제238조(집합투자재산의 평가)", "kind": "text"},
    ]})
    decree = ("p3", {"name": "자본시장과 금융투자업에 관한 법률 시행령.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제238조",
         "title": "해산의 보고 등", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제238조(해산의 보고 등)", "kind": "text"},
    ]})
    edges, pending = refs.cross_resolve(Index.from_docs([caller, law, decree]).docs)
    assert not any(e["src_doc"] == "p1" for e in edges)   # 총칭 — 확정 금지는 그대로
    rows = [p for p in pending if p["src_doc"] == "p1"]
    assert rows and rows[0]["hint"] == "법"
    # 시행령의 제238조(해산의 보고)는 후보에서 빠진다 — 법률의 제238조만 남는다
    assert {(c["doc_id"], c["node"]) for c in rows[0]["candidates"]} == {("p2", 1)}


def test_문서사이_자기범위밖_조는_보류로():
    """이름 없이 쓴 남의 조("제279조" — 이 문서는 제2조까지다)는 resolve 가
    못 잇는다 — 문서 사이에서 이름 없는 외부로 받아 보류에 올린다."""
    caller = ("d9", {"name": "규약.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "", "page": 1, "span": [0, 1]},
        {"id": 2, "parent": None, "level": 1, "surface": "제2조",
         "title": "", "page": 1, "span": [1, 2]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제1조 총칙.", "kind": "text"},
        {"idx": 1, "page": 1, "text": "제2조 제279조제1항의 외국 집합투자업자를 "
         "포함한다.", "kind": "text"},
    ]})
    law = ("d10", {"name": "자본시장법.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제279조",
         "title": "외국 집합투자증권", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제279조(외국 집합투자증권)", "kind": "text"},
    ]})
    edges, pending = refs.cross_resolve(Index.from_docs([caller, law]).docs)
    assert not any(e["src_doc"] == "d9" for e in edges)   # 이름이 없다 — 확정 금지
    rows = [p for p in pending if p["src_doc"] == "d9"]
    assert rows and rows[0]["key"] == ["조", 279, None]
    assert {(c["doc_id"], c["node"]) for c in rows[0]["candidates"]} == {("d10", 1)}


def test_문서사이_사슬도_내려간다():
    caller = ("d5", {"name": "위임전결.pdf"}, {"nodes": [
        {"id": 1, "parent": None, "level": 1, "surface": "제1조",
         "title": "위임", "page": 1, "span": [0, 1]},
    ], "blocks": [
        {"idx": 0, "page": 1, "text": "제1조(위임) 「시행세칙」 제1조제1항제2호나목을 "
         "따른다.", "kind": "text"},
    ]})
    docs = Index.from_docs([caller, _deep()]).docs
    edges, _ = refs.cross_resolve(docs)
    assert any(e["src_doc"] == "d5" and e["dst_doc"] == "d4" and e["dst"] == 6
               for e in edges)                   # 남의 문서 안에서도 목까지 내려간다


# ------------------------------------------------------------------ 그래프
def test_그래프_참조간선():
    g = Graph.from_index(_index())
    out = {sec for sec, _ in g.references(("d1", 9))}
    assert {("d1", 4), ("d1", 8), ("d1", 2)} <= out
    back = {sec for sec, _ in g.cited_by(("d1", 4))}
    assert back == {("d1", 9), ("d1", 5)}


# ------------------------------------------------------------------ 회수 확장
def test_회수가_참조_구역을_같이_든다():
    idx = _index()
    hit = Hit(target="doc:d1:3", kind="제목", value="정의", score=1.0,
              match="정확", doc_id="d1", doc="TRUST.pdf", node=3)
    sections = assemble(idx, SearchResult(query="정의", mode="정확",
                                          hits=[hit], ladder=[]))
    kinds = {(s.node, s.kind) for s in sections}
    assert (3, "제목") in kinds                       # 원 히트가 먼저
    assert (4, "참조") in kinds                       # 본문 참조가 끌어온 구역
    assert (8, "참조") in kinds
    ref4 = next(s for s in sections if s.node == 4)
    assert "제4조" in ref4.matched                    # 어느 연결점으로 왔는지 남는다
    assert "신탁은 계약으로 설정한다" in ref4.text     # 데이터가 실제로 실린다
    assert [s.n for s in sections] == list(range(1, len(sections) + 1))


# ------------------------------------------------------------------ 문서 사이
def test_문서사이_이름대조가_확정한다():
    edges, _ = _corpus().cross_refs()
    pairs = {(e["src_doc"], e["src"], e["dst_doc"], e["dst"]) for e in edges}
    assert ("d1", 5, "d2", 1) in pairs        # 「수수료규정」 제2조 → 그 문서의 제2조
    assert ("d2", 1, "d2", 2) in pairs        # 제 이름을 부른 참조 — 수수료규정 제12조


def test_문서사이_대용어는_보류():
    _, pending = _corpus().cross_refs()
    rows = [p for p in pending if p["hint"] == "동법"]
    assert rows                                # 동법 제12조 — 이름으로 못 정한다
    cand = {(c["doc_id"], c["node"]) for c in rows[0]["candidates"]}
    assert cand == {("d2", 2), ("d3", 1)}      # 닫힌 후보 — 제12조를 가진 문서들
    assert "동법 제12조" in rows[0]["context"]  # 판정 재료 — 참조가 쓰인 원문


def test_새_문서가_오면_연결이_생긴다():
    alone = Index.from_docs([_doc()])
    assert alone.cross_ref_edges() == []       # 수수료규정이 아직 저장소에 없다
    later = Index.from_docs([_doc(), _d2()])
    pairs = {(e["src_doc"], e["dst_doc"]) for e in later.cross_ref_edges()}
    assert ("d1", "d2") in pairs               # 올라오는 순간 같은 대조가 잇는다


def test_저장된_판정은_보류에서_빠진다():
    link = {"src_doc": "d1", "src": 9, "dst_doc": "d2", "dst": 2,
            "surface": "제12조", "hint": "동법", "key": ["조", 12, None],
            "block": 2, "via": "LLM", "confidence": 0.9}
    idx = Index.from_docs([_doc(), _d2(), _d3()], saved_links=[link])
    edges, pending = idx.cross_refs()
    assert any(e["src"] == 9 and e["dst_doc"] == "d2" and e["via"] == "LLM"
               for e in edges)                 # 판정 링크가 간선으로 실린다
    assert not any(p["src"] == 9 and p["hint"] == "동법" for p in pending)
    assert any(p["src"] == 5 and p["hint"] == "동법" for p in pending)  # 좌표 단위


class _FakeLLM:
    def __init__(self, out):
        self.out, self.log = out, []

    def structured(self, kind, system, user, schema, **kw):
        return self.out


def test_판정은_닫힌_후보와_fail_closed():
    idx = _corpus()
    out = {"picks": [
        {"id": "p0", "cid": "d2:2", "confidence": 0.9, "reason": "동법=수수료규정"},
        {"id": "p1", "cid": "d3:1", "confidence": 0.3, "reason": "확신 없음"},
    ]}
    links, meta = judge.settle_cross(_FakeLLM(out), idx)
    assert meta["settled"] == 1                # 저신뢰는 버려진다 — fail-closed
    assert links[0]["dst_doc"] == "d2" and links[0]["via"] == "LLM"
    assert judge.settle_cross(None, _corpus())[0] == []   # LLM 없으면 링크도 없다


def test_판정은_목록_밖_후보를_거른다():
    got = judge.judge(_FakeLLM({"picks": [
        {"id": "x", "cid": "없는후보", "confidence": 0.99, "reason": "지어냄"}]}),
        [{"id": "x", "ask": "?", "context": "…",
          "candidates": [{"cid": "a:1", "label": "A"}]}])
    assert got == {}                           # 모델이 좌표를 지어낼 자리가 없다


def test_그래프_문서사이_간선():
    g = Graph.from_index(_corpus())
    assert (("d2", 1), "제2조") in g.references(("d1", 5))
    assert ("d1", 5) in {sec for sec, _ in g.cited_by(("d2", 1))}


def test_회수가_문서_사이_참조도_든다():
    idx = _corpus()
    hit = Hit(target="doc:d1:5", kind="제목", value="특례", score=1.0,
              match="정확", doc_id="d1", doc="TRUST.pdf", node=5)
    sections = assemble(idx, SearchResult(query="특례", mode="정확",
                                          hits=[hit], ladder=[]))
    got = {(s.doc_id, s.node, s.kind) for s in sections}
    assert ("d1", 4, "참조") in got            # 문서 안 — 제4조
    assert ("d2", 1, "참조") in got            # 문서 사이 — 수수료규정 제2조
    far = next(s for s in sections if s.doc_id == "d2")
    assert "보수는 수수료규정" in far.text      # 남의 문서의 데이터가 실려 온다
