"""T9. 적합도 게이트 — 형식 오추출 방어 2 (SPEC §3.4).

매 문서 구조화 후 채점한다. 임계 미달이면 **결과를 확정하지 않고 격리**한다:
"이 문서는 형식 v1 과 N%만 부합. 다른 양식이거나 양식이 개정되었을 수 있음."
**조용한 실패 금지** — 형식이 안 맞는 문서를 그럴듯한 JSON 으로 내보내는 것이
이 시스템에서 가장 위험한 실패 모드다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.format_model import Format
from core.glossary import Glossary
from core.structurize import Document

DEFAULT_THRESHOLD = 0.70

# 채점 항목의 가중치 — 합이 1.0
WEIGHTS = {
    "marker_density": 0.25,      # 기대 마커가 실제로 검출됐는가
    "ordinal_continuity": 0.25,  # 번호가 연속인가 (제1조~제32조 중간이 비지 않았는가)
    "fact_coverage": 0.30,       # 용어집 fact 용어가 얼마나 잡혔는가
    "residual": 0.20,            # 형식이 설명하지 못한 잔여(기본 구역 질량)가 적은가
}

# 잔여 경고 임계 — 이 비율 이상이면 경고를 낸다. 문서 무관 상수다: 표지 몇 줄은
# 어느 문서에나 있으므로(정상 계약서 실측 1.7%) 그때마다 경고하면 소음이 되고,
# 열에 하나가 설명 밖이면 어느 doc_type 이든 마커를 놓치고 있다는 신호다.
RESIDUAL_WARN_RATIO = 0.10


@dataclass
class Fitness:
    score: float
    passed: bool
    warnings: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    def dump(self) -> dict:
        return {"score": round(self.score, 3), "passed": self.passed,
                "warnings": self.warnings, "detail": self.detail}


def _marker_density(doc: Document, fmt: Format) -> tuple[float, dict]:
    """형식이 선언한 마커 중 실제로 한 번이라도 검출된 비율."""
    declared = {m.id for m in fmt.regex_markers} | set(fmt.section_terms())
    if not declared:
        return 1.0, {}
    found = set()
    for s in doc.sections:
        kind = s.marker.get("kind")
        if kind == "regex":
            found.add(s.marker.get("id"))
        elif kind == "term":
            found.add(s.marker.get("term"))
    missing = sorted(declared - found)
    return len(found & declared) / len(declared), {"declared": sorted(declared),
                                                   "missing": missing}


def _ordinal_continuity(doc: Document) -> tuple[float, dict]:
    """번호 마커가 연속인가 — 중간이 비면 형식이 일부를 놓쳤다는 신호다."""
    seqs: dict[str, list[int]] = {}
    for s in doc.sections:
        if s.marker.get("kind") != "regex":
            continue
        no = str(s.marker.get("no") or "")
        # `'①'.isdigit()` 는 True 다(원문자도 Numeric_Type=Digit) — int() 는 터진다.
        # 아스키 숫자만 연속성 검사 대상으로 본다.
        if no.isascii() and no.isdigit():
            seqs.setdefault(s.marker["id"], []).append(int(no))
    if not seqs:
        return 1.0, {}
    scores, detail = [], {}
    for marker_id, nums in seqs.items():
        uniq = sorted(set(nums))
        span = uniq[-1] - uniq[0] + 1
        ratio = len(uniq) / span if span else 1.0
        gaps = [n for n in range(uniq[0], uniq[-1] + 1) if n not in set(uniq)]
        scores.append(ratio)
        detail[marker_id] = {"count": len(uniq), "range": [uniq[0], uniq[-1]],
                            "gaps": gaps[:20]}
    return sum(scores) / len(scores), detail


def _fact_coverage(doc: Document, glossary: Glossary) -> tuple[float, dict]:
    """용어집의 fact 용어 중 실제로 값이 잡힌 비율."""
    wanted = glossary.fact_terms()
    if not wanted:
        return 1.0, {}
    found = {f.term for f in doc.facts if not f.needs_review}
    review = sorted({f.term for f in doc.facts if f.needs_review})
    return len(found & set(wanted)) / len(wanted), {
        "expected": len(wanted), "extracted": len(found & set(wanted)),
        "missing": sorted(set(wanted) - found), "needs_review": review}


def _residual(doc: Document, total_elements: int) -> tuple[float, dict]:
    """형식이 설명하지 못한 요소(기본 구역에 담긴 것)의 비율 — 적을수록 좋다.

    격리된 투자설명서 실측 37%, 정상 계약서 1.7% — "구조를 다 반영했는가"를
    비율로 재는 지표라 문서 종류·크기와 무관하게 성립한다. 선형으로 깎는다:
    표지 몇 줄(수 %)은 거의 안 깎이고, 마커를 절반 놓친 문서는 크게 깎인다.
    """
    if total_elements <= 0:
        return 1.0, {}
    n = len(doc.residual)
    ratio = n / total_elements
    return max(0.0, 1.0 - ratio), {"residual": n, "total": total_elements,
                                   "ratio": round(ratio, 3)}


def score(doc: Document, fmt: Format, glossary: Glossary, total_elements: int,
          threshold: float = DEFAULT_THRESHOLD) -> Fitness:
    parts, detail = {}, {}
    parts["marker_density"], detail["marker_density"] = _marker_density(doc, fmt)
    parts["ordinal_continuity"], detail["ordinal_continuity"] = _ordinal_continuity(doc)
    parts["fact_coverage"], detail["fact_coverage"] = _fact_coverage(doc, glossary)
    parts["residual"], detail["residual"] = _residual(doc, total_elements)

    total = sum(parts[k] * WEIGHTS[k] for k in WEIGHTS)
    warnings: list[str] = []

    miss = detail["marker_density"].get("missing") or []
    if miss:
        warnings.append(f"형식이 선언한 마커가 검출되지 않았습니다: {', '.join(map(str, miss))}")
    for marker_id, d in detail["ordinal_continuity"].items():
        if d["gaps"]:
            warnings.append(f"'{marker_id}' 번호가 끊깁니다: {d['gaps']}")
    fc = detail["fact_coverage"]
    if fc.get("missing"):
        warnings.append(f"fact 용어를 찾지 못했습니다: {', '.join(fc['missing'])}")
    if fc.get("needs_review"):
        warnings.append(f"값 정규화 실패(판정 보류): {', '.join(fc['needs_review'])}")
    rd = detail["residual"]
    if rd.get("ratio", 0.0) >= RESIDUAL_WARN_RATIO:
        warnings.append(
            f"형식이 설명하지 못한 요소가 {rd['residual']}개({rd['ratio']:.0%})입니다 — "
            f"기본 구역에 담겼습니다(마커 미적중)")
    if doc.unmatched_headings:
        heads = doc.unmatched_headings
        preview = "; ".join(f"p.{h['page']} '{h['text'][:24]}'" for h in heads[:3])
        more = f" 외 {len(heads) - 3}개" if len(heads) > 3 else ""
        warnings.append(
            f"제목으로 보이는데 어느 마커에도 걸리지 않은 요소 {len(heads)}개 — "
            f"마커를 놓쳐 내용이 앞 구역에 붙었을 수 있습니다: {preview}{more}")

    passed = total >= threshold
    if not passed:
        warnings.insert(0,
            f"이 문서는 형식 v{fmt.format_version} 과 {total:.0%}만 부합합니다 — "
            "다른 양식이거나 양식이 개정되었을 수 있습니다 (격리)")
    return Fitness(score=total, passed=passed, warnings=warnings,
                   detail={"parts": {k: round(v, 3) for k, v in parts.items()},
                           **detail})


def apply(doc: Document, fmt: Format, glossary: Glossary, total_elements: int,
          threshold: float = DEFAULT_THRESHOLD) -> Fitness:
    """채점 결과를 Document 에 심고 돌려준다."""
    f = score(doc, fmt, glossary, total_elements, threshold)
    doc.fitness = f.dump()
    return f
