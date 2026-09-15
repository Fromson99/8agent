"""Word 스타일 두 경로 — ① 유도 경로의 style_heading 제안자 · ② docxstyle 통짜 신뢰.

두 경로가 지키는 것:
  ① 제안자: 스타일 선언은 **너비 0 후보**로 서고, 같은 자리에 표면 마커가 있으면
     자리를 내준다. 마커 없는 제목(`총칙`)이 정확히 이 계열의 지분이다.
  ② 통짜 신뢰: lawxml 처럼 선언을 그대로 트리로 옮기되, 커버리지·층 건너뜀으로
     **점수로 고백한다** — 스타일이 없거나 반쯤인 문서는 cold 로 떨어져야 한다.

파서 없이 Block/Element 를 직접 만들어 돈다 — docx 파싱 경로는 test_parse_docx 가
지키고, 여기서는 그 신호(meta.level → heading_level)의 소비만 본다.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pytest

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT))

from lawrag.core.parse_adapter import Element, ParseResult                    # noqa: E402
from lawrag.core.structure import from_styles, pipeline, registry, scoring    # noqa: E402
from lawrag.core.structure import lexicon as lexicon_mod                      # noqa: E402
from lawrag.core.structure.model import Block                                 # noqa: E402
from lawrag.core.structure.proposers import style_heading                     # noqa: E402


def _block(idx: int, text: str, level: Optional[int] = None) -> Block:
    return Block(idx=idx, text=text, page=1,
                 is_heading=level is not None, heading_level=level)


# ===========================================================================
# ① 유도 경로 — style_heading 제안자
# ===========================================================================

def test_style_candidate_is_zero_width_and_self_deep():
    cands = style_heading.propose(_block(0, "총칙", level=1), lexicon_mod.default())
    assert len(cands) == 1
    c = cands[0]
    assert (c.offset, c.end) == (0, 0), "표면이 없다 — 너비 0 이어야 한다"
    assert c.family_key == "style_h:1", "Heading N 은 자기계열 depth 로 실린다"
    assert c.construction == "style"
    assert c.ordinal is None, "스타일 제목은 자기가 몇 번째인지 말하지 않는다"


def test_style_does_not_fire_without_declared_level():
    assert style_heading.propose(_block(0, "총칙"), lexicon_mod.default()) == []


def test_surface_marker_takes_the_spot():
    """`제1장 총칙` 이 Heading 1 이면 kr_장 이 서고 스타일 후보는 사라진다 —
    같은 절단이면 서수를 실은 마커가 엄격히 더 많은 정보를 준다."""
    blocks = [_block(0, "제1장 총칙", level=1),
              _block(1, "이 규정은 시험을 위한 것이다.")]
    cands = pipeline.s0_propose(blocks, registry.default(), lexicon_mod.default(), "ko")
    fams = {c.family for c in cands if c.block_idx == 0}
    assert "kr_장" in {c.family_key.split("@")[0].split(":")[0] for c in cands} or fams
    assert not any(c.family == "style_h" for c in cands), \
        "표면 마커가 offset 0 에 섰으면 스타일 후보는 자리를 내줘야 한다"


def test_markerless_heading_is_exactly_the_style_share():
    """마커 없는 제목(`총칙`)에는 스타일 후보만 선다."""
    blocks = [_block(0, "총칙", level=1),
              _block(1, "이 규정은 시험을 위한 것이다.")]
    cands = pipeline.s0_propose(blocks, registry.default(), lexicon_mod.default(), "ko")
    assert [c.family for c in cands if c.block_idx == 0] == ["style_h"]


def test_josa_initial_heading_is_not_penalized():
    """`은행…` 처럼 조사 글자로 시작하는 제목 — 너비 0 마커에는 조사가 붙을 표면이
    없으므로 clean 이어야 한다."""
    blocks = [_block(0, "은행 내규 총칙", level=1),
              _block(1, "이 내규는 시험을 위한 것이다."),
              _block(2, "적용 범위", level=2),
              _block(3, "본점과 지점에 적용한다.")]
    result = pipeline.interpret(blocks, doc="josa")
    c = next(c for c in result.candidates if c.block_idx == 0)
    assert c.guards["particle_ko"] == scoring.PARTICLE_CLEAN
    assert c.s == pytest.approx(scoring.BLOCK_OPEN + scoring.CONSTRUCTION_FULL
                                + scoring.PARTICLE_CLEAN)


def test_style_only_document_builds_a_tree():
    """스타일 선언만 있는 문서 — H1 두 개, 각각 아래 H2. 사다리는 자기계열 depth 로
    H1 < H2 를 관측 없이 얻는다. 레벨마다 둘 이상이어야 한다 — 등재 심사는
    "하나짜리는 계열이 아니다"(reg_score)를 스타일에도 똑같이 적용한다."""
    blocks = [_block(0, "총칙", level=1),
              _block(1, "이 규정은 시험을 위한 것이다."),
              _block(2, "적용 범위", level=2),
              _block(3, "본점과 지점에 적용한다."),
              _block(4, "운용", level=1),
              _block(5, "운용은 별도 기준을 따른다."),
              _block(6, "운용 기준", level=2),
              _block(7, "기준은 따로 정한다.")]
    result = pipeline.interpret(blocks, doc="style-only")
    lad = result.ladder
    assert lad.level_of("style_h:1") is not None
    assert lad.level_of("style_h:2") is not None
    assert lad.level_of("style_h:1") < lad.level_of("style_h:2")
    roots = [n for n in result.tree]
    assert [n.family for n in roots] == ["style_h:1", "style_h:1"]
    assert [c.family for c in roots[0].children] == ["style_h:2"]
    assert [c.family for c in roots[1].children] == ["style_h:2"]
    assert result.fitness_passed, f"경고: {result.warnings}"


def test_articles_nest_under_style_headings():
    """스타일 제목(장 노릇)과 마커(조)가 섞인 문서 — 조가 스타일 제목 아래로 들어간다.
    상하는 여기서 선언하지 않는다: 조가 스타일 구간 **안에서** 관측되는 것이 증거다."""
    blocks = [_block(0, "총칙", level=1),
              _block(1, "제1조(목적) 이 규정은 시험을 위한 것이다."),
              _block(2, "제2조(정의) 용어의 뜻은 다음과 같다."),
              _block(3, "운용", level=1),
              _block(4, "제3조(방법) 운용 방법을 정한다."),
              _block(5, "제4조(한도) 운용 한도를 정한다.")]
    result = pipeline.interpret(blocks, doc="mixed")
    roots = result.tree
    assert [n.family for n in roots] == ["style_h:1", "style_h:1"]
    for root in roots:
        assert all(c.family == "kr_article" for c in root.children), \
            [c.family for c in root.children]


# ===========================================================================
# ② docxstyle — 통짜 신뢰 경로
# ===========================================================================

def _element(index: int, text: str, level: Optional[int] = None) -> Element:
    if level is not None:
        return Element(index=index, type="section_header", text=text,
                       meta={"level": level})
    return Element(index=index, type="text", text=text)


def _parsed(els: list[Element]) -> ParseResult:
    return ParseResult(path="시험.docx", doc_id="d", parser="test",
                       born_digital=True, elements=els)


def test_from_styles_moves_declarations_into_a_tree():
    parsed = _parsed([
        _element(0, "총칙", level=1),
        _element(1, "이 규정은 시험을 위한 것이다."),
        _element(2, "적용 범위", level=2),
        _element(3, "본점과 지점에 적용한다."),
        _element(4, "운용", level=1),
        _element(5, "운용은 별도 기준을 따른다."),
    ])
    result, blocks = from_styles.result_from_styles(parsed, doc="시험.docx")
    assert [n.surface for n in result.tree] == ["총칙", "운용"]
    assert [n.surface for n in result.tree[0].children] == ["적용 범위"]
    # 제목은 작성자 선언 그대로다 — 유도 경로처럼 꼬리를 자를 필요가 없다
    assert result.tree[0].title == "총칙"
    # span — 다음 같은/얕은 제목 직전까지
    assert result.tree[0].span == (0, 4)
    assert result.tree[0].children[0].span == (2, 4)
    assert result.fitness_passed
    assert result.stats["source"] == "docxstyle"


def test_from_styles_without_styles_is_cold():
    parsed = _parsed([_element(0, "제1조(목적) 이 규정은 시험을 위한 것이다."),
                      _element(1, "제2조(정의) 용어의 뜻은 다음과 같다.")])
    result, _ = from_styles.result_from_styles(parsed, doc="무스타일.docx")
    assert result.fitness_score == 0.0
    assert result.tier == "cold"
    assert any("스타일 제목이 하나도 없습니다" in w for w in result.warnings)


def test_from_styles_folds_sparse_levels_and_reports_skips():
    """Word 가 2·4 레벨만 쓴 문서 — 층은 상하만 취해 0·1 로 접고, 건너뜀은
    접기 전의 원래 값으로 세어 점수로 고백한다."""
    parsed = _parsed([
        _element(0, "총칙", level=2),
        _element(1, "본문이 이어진다."),
        _element(2, "세부 기준", level=4),
        _element(3, "세부 본문이다."),
    ])
    result, _ = from_styles.result_from_styles(parsed, doc="듬성.docx")
    assert result.tree[0].level == 0
    assert result.tree[0].children[0].level == 1
    assert result.stats["declared_levels"] == [2, 4]
    assert result.stats["level_skips"] == 1
    assert result.stats["consistency"] < 1.0
    assert any("층 건너뜀" in w for w in result.warnings)


def test_block_carries_the_declared_level():
    """meta.level → Block.heading_level 배선 — 이게 끊기면 두 경로가 다 침묵한다."""
    blocks = Block.from_elements([_element(0, "총칙", level=3),
                                  _element(1, "본문.")])
    assert blocks[0].heading_level == 3
    assert blocks[1].heading_level is None


# ===========================================================================
# 라우팅 표식 — structured_by
# ===========================================================================

def test_structured_by_marks_the_engine():
    pytest.importorskip("fastapi", reason="FastAPI 필요")
    from lawrag.api.routers.structure import _structured_by

    assert _structured_by({"engine": "docxstyle"}, "docx") == "docxstyle"
    assert _structured_by({}, "docx") == "induce"
    assert _structured_by({"engine": "docxstyle"}, "lawxml") == "lawxml"
