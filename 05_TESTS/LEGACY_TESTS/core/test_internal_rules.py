"""내규(회사 규정·지침·세칙)를 유도(DP) 경로로 구조화할 때의 규칙 — 2026-08 실측에서 나온 것들.

외규는 lawxml 태그가 계층을 주지만 내규 docx 는 `제1조`·`①`·`1.` 마커뿐이라 유도 경로로
간다. 예시 내규 3종과 실무 관례 변형 3종(제 1 조 【목적】 · 부 칙 <일자> · 장 없이
조만 · 부칙 여럿)을 돌려 보고 고친 자리마다 하나씩 잠근다. docling 없이
`pipeline.interpret(_blocks(...))` 로 돈다.
"""
from __future__ import annotations

import pytest

from lawrag.core import internal_rules
from lawrag.core.structure import pipeline
from lawrag.core.structure.model import Block
from lawrag.core.structure.proposers import dot_number


def _blocks(lines) -> list[Block]:
    return [Block(idx=i, text=t, page=1) for i, t in enumerate(lines)]


def _tree(r) -> list[tuple[int, str]]:
    out = []
    def walk(nodes, d=0):
        for n in nodes:
            out.append((d, n.surface))
            walk(n.children, d + 1)
    walk(r.tree)
    return out


PO = internal_rules.PROFILE["partial_order"]


# ===========================================================================
# 조 제목 — 【목적】 · [목적] 도 마커 직후 괄호다
# ===========================================================================

def test_title_accepts_corner_and_square_brackets():
    """`제 1 조 【목적】` · `제2조 [정의]` — 여닫는 짝만 다른 같은 규약."""
    r = pipeline.interpret(_blocks([
        "제 1 조 【목적】 이 지침은 투자·인수업무의 위험을 관리하기 위하여 필요한 사항을 정한다.",
        "제 2 조 [정의] 이 지침에서 사용하는 용어의 뜻은 다음과 같다.",
        "제 3 조 【딜 승인】",
        "① 인수금액이 500억 원 이상인 딜은 투자심사위원회의 심의를 거쳐야 한다.",
        "② 인수금액이 1,000억 원 이상인 딜은 위험관리위원회에 상정하여야 한다.",
        "제 4 조 〔보고〕 리스크관리부는 월 1회 위원회에 보고한다."]), doc="t")
    got = {n.surface: n.title for n in r.nodes() if n.family == "kr_article"}
    assert got == {"제 1 조": "목적", "제 2 조": "정의", "제 3 조": "딜 승인", "제 4 조": "보고"}, got


def test_title_bracket_pairs_must_match():
    """`제1조 (목적]` 처럼 짝이 어긋나면 괄호가 아니다 — 억지로 이름을 만들지 않는다."""
    r = pipeline.interpret(_blocks([
        "제1조 (목적] 이 세칙은 위험관리에 필요한 사항을 정한다.",
        "제2조(정의) 이 세칙에서 사용하는 용어의 정의는 다음과 같다.",
        "제3조(범위) 가"]), doc="t")
    got = {n.surface: n.title for n in r.nodes() if n.family == "kr_article"}
    assert got["제1조"] == "" and got["제2조"] == "정의", got


def test_buchik_title_is_not_its_first_article():
    """`부칙` 다음 줄 `제1조(시행일)` 은 부칙의 이름이 아니라 부칙의 첫 조다."""
    r = pipeline.interpret(_blocks([
        "제1장 총칙", "제1조(목적) 가", "제2조(정의) 나",
        "제2장 조치", "제3조(조치) 다", "제4조(보고) 라",
        "부칙", "제1조(시행일) 이 세칙은 2024년 1월 2일부터 시행한다."]),
        doc="t", partial_order=PO)
    bu = next(n for n in r.nodes() if n.family == "buchik")
    assert bu.title == "", (bu.title, bu.title_reason)
    assert [c.surface for c in bu.children] == ["제1조"]


# ===========================================================================
# 점번호 — 날짜 성분은 마커가 아니다
# ===========================================================================

def test_dot_number_skips_date_components():
    """`부칙(2024. 1. 2.)` · `<개정 2026. 7. 1.>` 의 `1.` `2.` 는 후보로 서지 않는다."""
    for text in ("부칙(2024. 1. 2.) 제1조(시행일)",
                 "③ 위원회는 분기 1회 정기 개최한다. <개정 2026. 7. 1.>",
                 "부 칙 <2025. 3. 1.>"):
        cands = dot_number.propose(Block(idx=0, text=text, page=1), None)
        assert not cands, (text, [c.surface for c in cands])


def test_dot_number_still_fires_after_a_sentence():
    """HWP 평탄화로 항과 호가 한 줄에 온 `…와 같다. 1. 시장위험액` 은 여전히 후보다."""
    cands = dot_number.propose(
        Block(idx=0, text="② 총위험액은 다음 각 호와 같다. 1. 시장위험액 2. 신용위험액", page=1), None)
    assert [c.surface for c in cands] == ["1.", "2."]


def test_no_ghost_node_under_buchik_from_a_date():
    """실측(예시 세칙 v2): `부칙(2024. 1. 2.) 제1조(시행일)` 아래에 가짜 `1.` 마디가 섰다."""
    r = pipeline.interpret(_blocks([
        "제1장 총칙", "제1조(목적) 가", "제2조(정의) 나",
        "제2장 조치", "제3조(조치) 다", "제4조(보고) 라",
        "부칙(2024. 1. 2.) 제1조(시행일)", "이 세칙은 2024년 1월 2일부터 시행한다."]),
        doc="t", partial_order=PO)
    assert not [n for n in r.nodes() if n.family.startswith("dot_number")]


# ===========================================================================
# DP — 같은 계열은 자기 안에 중첩하지 않는다 · 층 해제 뒤의 novelty
# ===========================================================================

_NO_CHAPTER_TWO_ADDENDA = [
    "제1조(목적) 이 세칙은 외환리스크의 관리에 필요한 사항을 정한다.",
    "제2조(한도) 회사의 외환포지션 한도는 다음 각 호와 같다.",
    "1. 종합포지션: 100분의 50", "2. 선물환포지션: 100분의 30",
    "제3조(조치)",
    "① 한도를 초과한 부서의 장은 즉시 보고한다.",
    "② 위험관리책임자는 3영업일 이내에 해소계획을 보고한다.",
    "제4조(준용) 이 세칙에 정하지 아니한 사항은 「위험관리기준시행세칙」을 준용한다.",
    "부칙 (2024.1.2.)", "제1조(시행일) 이 세칙은 2024년 1월 2일부터 시행한다.",
    "부칙 (2025.6.30.)", "제1조(시행일) 이 세칙은 2025년 6월 30일부터 시행한다.",
    "제2조(경과조치) 종전 한도는 이 세칙에 따른 것으로 본다.",
]


def test_articles_do_not_nest_inside_articles_when_ladder_seats_them_below_buchik():
    """장 없이 조만 있고 부칙이 둘 — 사다리는 `부칙 > 조` 로 서서 조가 L1 이 되지만
    첫 조를 열 L0 가 없다. 층 해제 뒤 제2조·제3조·제4조가 제1조 **안으로** 들어가고
    적합도 0.83 으로 통과하던 조용한 실패를 잠근다."""
    r = pipeline.interpret(_blocks(_NO_CHAPTER_TWO_ADDENDA), doc="t", partial_order=PO)
    tree = _tree(r)
    body = [(d, s) for d, s in tree if s in ("제1조", "제2조", "제3조", "제4조")][:4]
    assert body == [(0, "제1조"), (0, "제2조"), (0, "제3조"), (0, "제4조")], tree
    assert (1, "1.") in tree and (1, "①") in tree, tree
    assert "kr_article" in r.ladder.freed, r.ladder.dump()


def test_addendum_articles_stay_inside_their_addendum():
    """풀린 조라도 사다리의 상대 순서(부칙 > 조)는 살아 있다 — 부칙의 제1조는 부칙 안이다."""
    r = pipeline.interpret(_blocks(_NO_CHAPTER_TWO_ADDENDA), doc="t", partial_order=PO)
    bu = [n for n in r.nodes() if n.family == "buchik"]
    assert [[c.surface for c in b.children] for b in bu] == [["제1조"], ["제1조", "제2조"]], _tree(r)
    assert r.fitness_passed and r.fitness_score >= 0.85, (r.fitness_score, r.warnings)


def test_self_nesting_allows_the_golden_inner_list():
    """골든 §8: `2. → 2.1 → 1. 국내채권` — 사이에 다른 계열이 끼면 같은 계열 안이어도 정답."""
    r = pipeline.interpret(_blocks([
        "1. 총칙", "1.1 목적", "① 이 약관은…", "② 수탁자는…", "1.2 정의",
        "2. 운용", "2.1 운용방법 (1.1의 원칙을 준용)", "1. 국내채권"]), doc="golden")
    assert _tree(r)[-3:] == [(0, "2."), (1, "2.1"), (2, "1.")], _tree(r)


# ===========================================================================
# 사다리 — 하나짜리 계열은 결함이 아니다 · 지정에 오른 계열은 등재된다
# ===========================================================================

def test_singleton_family_is_not_a_ladder_defect():
    """짧은 내규의 `부칙` 하나 · `[별표 1]` 하나 — 문맥판정으로 가되 감점은 없다."""
    r = pipeline.interpret(_blocks([
        "제1장 총칙", "제1조(목적) 가", "제2조(정의) 나",
        "제2장 조치", "제3조(조치) 다", "제4조(보고) 라",
        "부칙", "제1조(시행일) 이 세칙은 2024년 1월 2일부터 시행한다.",
        "[별표 1] 감독당국 보고 서식", "보고일자 / 순자본비율 / 미달 사유"]),
        doc="t", partial_order=PO)
    lad = r.ladder
    assert sorted(lad.singletons) == ["annex_별표", "buchik"], lad.dump()
    assert not lad.unregistered, lad.dump()
    assert not any("미등재" in w for w in r.warnings), r.warnings
    tops = [n.surface for n in r.tree]
    assert tops == ["제1장", "제2장", "부칙", "[별표 1]"], tops


def test_partial_order_registers_a_declared_singleton():
    """`제1장` 이 문서에 하나뿐이어도 지정 순서(장 > 조)에 이름이 오르면 등재된다."""
    body = ["제1장 총칙", "제1조(목적) 가", "제2조(정의) 나", "제3조(범위) 다"]
    plain = pipeline.interpret(_blocks(body), doc="t")
    hinted = pipeline.interpret(_blocks(body), doc="t", partial_order=[("kr_장", "kr_article")])
    assert "kr_장" in plain.ladder.singletons and plain.ladder.level_of("kr_장") is None
    assert hinted.ladder.level_of("kr_장") == 0 and hinted.ladder.level_of("kr_article") == 1
    assert _tree(hinted) == [(0, "제1장"), (1, "제1조"), (1, "제2조"), (1, "제3조")]


# ===========================================================================
# 머리 meta — 제정·개정 일자 · 문서군
# ===========================================================================

def test_header_meta_reads_enactment_and_revisions():
    meta = internal_rules.header_meta([
        "위험관리기준시행세칙",
        "※ 본 문서는 AI Agent 구축·검증용 예시 내규로, 실제 회사의 규정이 아님. (현행 v2)",
        "제정 2024. 1. 2.", "개정 2025년 6월 30일", "개정 2026. 7. 1.",
        "제1장 총칙", "제1조(목적) …", "개정 2030. 1. 1."])       # 마커 뒤는 머리가 아니다
    assert meta["kind"] == "internal"
    assert meta["title"] == "위험관리기준시행세칙"
    assert meta["enacted"] == "20240102"
    assert meta["revised"] == "20260701" and meta["enforce"] == "20260701"
    assert meta["history"] == ["제정 2024. 1. 2.", "개정 2025년 6월 30일", "개정 2026. 7. 1."]


def test_header_meta_bracketed_enactment_and_enforcement():
    meta = internal_rules.header_meta(["투자및인수위험관리지침", "(제정 2025. 3. 1.)",
                                       "시행 2025. 4. 1.", "제 1 조 【목적】 …"])
    assert (meta["enacted"], meta["revised"], meta["enforce"]) == ("20250301", "20250301", "20250401")


def test_header_meta_without_dates_keeps_the_kind():
    meta = internal_rules.header_meta(["신규 딜 리스크 검토 요청서", "1. 딜 개요"])
    assert meta == {"kind": "internal", "title": "신규 딜 리스크 검토 요청서"}


@pytest.mark.parametrize("name,expected", [
    ("위험관리기준시행세칙_v2_2026", ("위험관리기준시행세칙", "v2")),
    ("위험관리기준시행세칙 v1 2024", ("위험관리기준시행세칙", "v1")),
    ("투자및인수위험관리지침_2025", ("투자및인수위험관리지침_2025", "")),
    ("외환리스크관리세칙", ("외환리스크관리세칙", "")),
])
def test_split_series(name, expected):
    assert internal_rules.split_series(name) == expected
