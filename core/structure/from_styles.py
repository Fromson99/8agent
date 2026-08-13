"""Word 스타일 계층을 **통짜로 신뢰**하는 구조화 — docx 전용 제3의 경로.

lawxml 이 law.go.kr 의 태그 계층을 추론 없이 옮기듯, 이 경로는 Word 스타일
(`Block.heading_level` ← `Element.meta.level`)을 추론 없이 트리로 옮긴다.
유도(S0~S6)도 형식 파일도 거치지 않는다 — **스타일이 곧 구조다.**

## lawxml 과 결정적으로 다른 점 — 발행자를 못 믿는다

lawxml 의 태그는 발행 시스템이 찍으므로 통짜 신뢰가 성립한다. Word 스타일은
사람이 붙인다: 본문을 Heading 으로 찍은 문서, 장·절만 스타일이고 조부터는
수동 번호인 문서가 실무에 흔하다. 그래서 이 경로는 신뢰하되 **점수로 고백한다**:

    커버리지   첫 제목 앞·스타일이 안 덮는 블록의 비율이 낮으면 점수가 떨어진다
    정합       H1→H3 처럼 층을 건너뛴 선언은 벌점 — 스타일이 반쯤인 문서의 증거다

점수가 임계(T) 아래면 cold 다 — 그 문서는 이 경로가 아니라 유도/형식 경로로
가야 한다는 뜻이고, 화면이 그렇게 안내한다.

## 레벨은 **관측된 값을 접어서** 쓴다

Word 의 outlineLvl 은 1부터지만 문서가 2·4 만 쓰는 일도 있다. 관측된 레벨을
정렬해 촘촘한 층(0,1,2…)으로 접는다 — 트리의 깊이는 선언의 절대값이 아니라
**서로의 상하**가 정한다. 건너뜀 벌점은 접기 전의 원래 값으로 잰다(2→4 는
접으면 안 보인다).

경로 표식은 `structured_by: docxstyle` (api/routers/structure.py 의 규약).
"""
from __future__ import annotations

from core.parse_adapter import ParseResult
from core.structure import scoring
from core.structure.model import (
    Block,
    Fingerprint,
    Ladder,
    Node,
    Rung,
    StructureResult,
)

# 화면·감사 로그용 surface 길이 상한 (proposers/style_heading.py 와 같은 값)
_MAX_SURFACE = 40


def _clean(s: str) -> str:
    return " ".join((s or "").split())


def _surface(text: str) -> str:
    t = _clean(text)
    return t[:_MAX_SURFACE] + "…" if len(t) > _MAX_SURFACE else t


def result_from_styles(parsed: ParseResult, *, doc: str
                       ) -> tuple[StructureResult, list[Block]]:
    """스타일 선언만으로 (StructureResult, blocks) 를 조립한다.

    스타일 제목이 하나도 없으면 적합도 0 으로 돌아간다 — 이 경로는 Word 제목
    스타일이 있는 문서에만 유효하고, 없다는 사실을 조용히 넘기면 "빈 트리"가
    원인 없이 나타난다.
    """
    blocks = Block.from_elements(parsed.elements)
    result = StructureResult(doc=doc)
    result.applied = {"root": None, "families": None, "ladder_hint": None,
                      "partial_order": None, "llm": False, "lang": "ko",
                      "source": "docxstyle"}
    result.stats["source"] = "docxstyle"
    result.stats["deterministic"] = True
    result.stats["blocks"] = len(blocks)

    heads = [b for b in blocks
             if b.heading_level is not None and b.proposes and b.text.strip()]
    if not heads:
        result.fitness_score, result.fitness_passed, result.tier = 0.0, False, "cold"
        result.warnings.append(
            "Word 스타일 제목이 하나도 없습니다 — 이 경로(docxstyle)는 제목 스타일이 "
            "있는 문서에만 유효합니다. 유도 경로나 형식 연결로 해석하세요")
        return result, blocks

    # 관측된 선언 레벨 → 촘촘한 층 (위 주석: 상하만 취하고 절대값은 버린다)
    seen = sorted({b.heading_level for b in heads})
    fold = {lv: i for i, lv in enumerate(seen)}

    roots: list[Node] = []
    stack: list[Node] = []
    entries: list[tuple[Node, Block]] = []
    skips = 0
    prev_declared = None
    for b in heads:
        level = fold[b.heading_level]
        if prev_declared is not None and b.heading_level > prev_declared + 1:
            skips += 1          # H1→H3 — 층 건너뜀. 스타일이 반쯤인 문서의 증거
        prev_declared = b.heading_level
        node = Node(
            level=level, ordinal=None, family=f"style_h:{b.heading_level}",
            surface=_surface(b.text), block_idx=b.idx, page=b.page,
            element_index=b.element_index, candidate_id=f"style:{b.idx}",
            title=_clean(b.text), title_reason="스타일 제목 (작성자 선언)",
            activation_reason=f"Word 스타일 Heading {b.heading_level} (통짜 신뢰)",
            bbox=list(b.bbox) if b.bbox else None, bbox_origin=b.bbox_origin)
        while stack and stack[-1].level >= level:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)
        entries.append((node, b))

    # span — 다음 같은/얕은 제목 직전까지 (dp.build_tree 와 같은 규약)
    for i, (node, b) in enumerate(entries):
        end = len(blocks)
        for later, _ in entries[i + 1:]:
            if later.level <= node.level:
                end = later.block_idx
                break
        node.span = (b.idx, end)

    result.tree = roots

    # 사다리·지문 — 선언된 레벨에서 역산 (from_format 과 같은 규약)
    by_level: dict[int, set[str]] = {}
    for n, _ in entries:
        by_level.setdefault(n.level, set()).add(n.family)
    result.ladder = Ladder(rungs=[
        Rung(level=lv, families=sorted(fams), reg_score=1.0,
             evidence="Word 스타일 선언 (유도 없음)")
        for lv, fams in sorted(by_level.items())])
    result.fingerprint = Fingerprint(
        families=sorted({f for s in by_level.values() for f in s}),
        order=[sorted(by_level[lv]) for lv in sorted(by_level)])

    # 적합도 — 신뢰하되 고백한다 (위 주석)
    covered = len({i for n, _ in entries for i in range(n.span[0], n.span[1])})
    coverage = min(1.0, covered / len(blocks)) if blocks else 0.0
    consistency = 1.0 - (skips / len(heads))
    result.fitness_score = coverage * consistency
    result.fitness_passed = result.fitness_score >= scoring.FITNESS_T
    result.tier = "hot" if result.fitness_passed else "cold"
    result.stats.update({
        "headings": len(heads), "declared_levels": seen,
        "level_skips": skips,
        "covered_blocks": covered, "coverage": round(coverage, 3),
        "consistency": round(consistency, 3), "ladder_quality": 1.0,
        "candidates": 0, "activated": len(entries),
        "table_blocks": sum(1 for b in blocks if b.kind == "table"),
        "figure_blocks": sum(1 for b in blocks if b.kind == "figure"),
    })
    # 표·그림 소속과 지면 범위는 유도 경로와 같은 후처리를 쓴다 — 화면이 두 경로를
    # 같은 눈으로 비교할 수 있어야 "괜찮은 쪽"을 고를 수 있다.
    from core.structure import pipeline as pipeline_mod
    result.stats["attached"] = pipeline_mod.attach_leaves(result, blocks)
    pipeline_mod.measure_extent(result, blocks)

    if skips:
        result.warnings.append(
            f"스타일 층 건너뜀 {skips}건 (예: H1 바로 아래 H3) — 스타일이 일부에만 "
            f"붙은 문서일 수 있습니다. 유도 경로와 비교해 보세요")
    if not result.fitness_passed:
        result.warnings.append(
            f"적합도 {result.fitness_score:.0%} < T {scoring.FITNESS_T:.0%} — 스타일 "
            f"선언이 문서를 충분히 덮지 못합니다. 이 문서는 유도/형식 경로가 맞습니다")
    return result, blocks
