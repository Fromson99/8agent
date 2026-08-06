"""LLM 판정 — 좁혀진 범위의 증거 표를 보고 두 문서의 값을 대조한다.

## 무엇을 LLM 이 하고, 무엇을 코드가 하는가

    코드   문서 구조화 → section 으로 범위 좁히기 → 증거 표 만들기 → **증거 ID ↔ 출처 대응**
    LLM    그 표에서 값을 고르고, 두 값을 견주어 판정

출처는 LLM 이 만들지 않는다. LLM 은 `e-012` 같은 **증거 ID 로만** 근거를 가리킬 수 있고,
코드가 그 ID 를 실제 page/bbox/cell 로 되돌린다. 없는 ID 를 대면 그 행은 판정을 버리고
`NEEDS_REVIEW` 로 내린다 — 지어낸 근거가 리포트에 실릴 길이 없다.

> 주의: SPEC.md §4.1 과 AGENT1_SPEC §1 은 "판정에 LLM 금지"를 규정한다. 이 모듈은
> 그 규정을 **의도적으로 뒤집은** 구성이며(사용자 결정), 대신 출처 위조를 막는 장치를 둔다.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.glossary import normalize                     # noqa: E402
from scope import Scope, to_table                       # noqa: E402

VERDICTS = ("MATCH", "VALUE_MISMATCH", "MISSING_IN_TARGET",
            "SOURCE_EXTRACTION_FAILED", "NOT_APPLICABLE", "NEEDS_REVIEW")

SYSTEM = """당신은 두 금융 문서의 값을 대조하는 검수자다.

주어지는 것
- 비교할 용어 하나
- 정답 문서(계약서)의 좁혀진 범위에서 뽑은 증거 표
- 대상 문서(투자설명서)의 좁혀진 범위에서 뽑은 증거 표
- 표의 모든 줄에는 `e-001` 형식의 증거 ID 가 붙어 있다

해야 할 일
1. 각 표에서 그 용어에 해당하는 값을 고른다. 없으면 없다고 한다.
2. 두 값을 견주어 판정한다.
3. 고른 값마다 **반드시 증거 ID 를 댄다.** 표에 없는 ID 를 지어내지 마라.
   페이지 번호나 문구를 새로 쓰지 마라 — 근거는 오직 증거 ID 로만 가리킨다.

판정
- MATCH                     두 값이 같다. 표기 차이(`금 1억원정` ≡ `100,000,000원`,
                            `연 1.5%` ≡ `1.50%`, `24.6.3` ≡ `2024-06-03`)는 같은 것으로 본다.
- VALUE_MISMATCH            두 값이 실제로 다르다.
- MISSING_IN_TARGET         정답에는 값이 있는데 대상 범위에 없다.
- SOURCE_EXTRACTION_FAILED  정답 쪽에서 값을 찾지 못했다. 대상 문제가 아니라 시스템 경고다.
- NEEDS_REVIEW              후보가 여럿이라 하나로 정할 수 없거나, 판단이 서지 않는다.

원칙
- 애매하면 MATCH 나 VALUE_MISMATCH 로 밀어붙이지 말고 NEEDS_REVIEW 로 둔다.
- 한 표에 같은 용어의 후보가 여럿이면(클래스별 요율 등) 임의로 고르지 말고
  NEEDS_REVIEW 로 두되 후보들의 증거 ID 를 전부 적는다.
- reason 은 한 문장. 무엇과 무엇을 견주었는지 쓴다."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "term": {"type": "string"},
        "source_value": {"type": ["string", "null"]},
        "source_evidence": {"type": "array", "items": {"type": "string"}},
        "target_value": {"type": ["string", "null"]},
        "target_evidence": {"type": "array", "items": {"type": "string"}},
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "reason": {"type": "string"},
        "candidates": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["term", "source_value", "source_evidence", "target_value",
                 "target_evidence", "verdict", "reason", "candidates"],
    "additionalProperties": False,
}


@dataclass
class Judgement:
    term: str
    verdict: str
    reason: str
    source_value: Optional[str] = None
    target_value: Optional[str] = None
    source_refs: list[dict] = field(default_factory=list)
    target_refs: list[dict] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    method: str = "llm"
    row_anchor: Optional[str] = None
    anchor_verified: Optional[bool] = None

    def dump(self) -> dict:
        d = {"term": self.term, "verdict": self.verdict, "reason": self.reason,
             "method": self.method,
             "source": {"value": self.source_value, "refs": self.source_refs},
             "target": {"value": self.target_value, "refs": self.target_refs},
             "candidates": self.candidates, "warnings": self.warnings}
        if self.row_anchor:
            d["row_anchor"] = {"expected": self.row_anchor,
                               "verified": self.anchor_verified}
        return d


def _resolve(ids: list[str], scope: Scope, warnings: list[str], side: str) -> list[dict]:
    """증거 ID → 실제 출처. 표에 없는 ID 는 버리고 경고를 남긴다."""
    index = scope.by_id()
    out: list[dict] = []
    for ev_id in ids or []:
        ev = index.get(ev_id)
        if ev is None:
            warnings.append(f"{side} 근거 '{ev_id}' 는 증거 표에 없습니다 (지어낸 근거)")
            continue
        out.append({"ev_id": ev.ev_id, **ev.source(), "text": ev.text})
    return out


def _row_label(ref: dict) -> str:
    """표 행의 첫 칸 = 그 행의 라벨."""
    if ref.get("kind") != "table_row":
        return ""
    return (ref.get("text") or "").split("|")[0].strip()


def verify_row_anchor(refs: list[dict], anchor: Optional[str]) -> tuple[Optional[bool], str]:
    """LLM 이 고른 행이 규칙이 못박은 행인가 — **검증만 한다** (결정론).

    앵커로 값을 뽑지 않는 이유: 행 라벨 부분일치가 흔하고("총 보수" vs "동종유형 총 보수"
    vs "총 보수·비용"), 병합 헤더에서 열 오프셋이 밀리며, 레이아웃 박스를 표로 오인할 수
    있다. **그리고 앵커가 틀려도 조용하다** — 그럴듯한 값 하나가 나오고 신호가 없다.
    그래서 뽑기는 판단자에게 맡기고, 여기서는 고른 행이 맞는지만 대조한다.
    """
    if not anchor:
        return None, ""
    labels = [_row_label(r) for r in refs]
    labels = [l for l in labels if l]
    if not labels:
        return False, f"근거에 표 행이 없어 행 기준 '{anchor}' 을 확인할 수 없습니다"
    a = normalize(anchor)
    for label in labels:
        n = normalize(label)
        if a in n or n in a:
            return True, f"행 기준 '{anchor}' 확인됨 ('{label}')"
    return False, (f"행 기준 '{anchor}' 과 다른 행을 골랐습니다 "
                   f"(고른 행: {', '.join(labels[:3])})")


def judge(term: str, src: Scope, tgt: Scope, llm,
          note: str = "", row_anchor: Optional[str] = None) -> Judgement:
    """한 용어에 대해 두 범위를 대조한다."""
    head = f"# 비교할 용어: {term}"
    if row_anchor:
        head += (f"\n\n**행 기준: `{row_anchor}`** — 대상 문서의 표에서 이 행만 본다. "
                 "다른 행의 값을 고르지 마라.")
    if note:
        head += f"\n(참고: {note})"
    user = "\n\n".join([
        head,
        "## 정답 문서 (계약서)", to_table(src),
        "## 대상 문서 (투자설명서)", to_table(tgt),
    ])
    data = llm.structured(f"judge:{term}", SYSTEM, user, SCHEMA, effort="high")
    if not data:
        return Judgement(term=term, verdict="NEEDS_REVIEW",
                         reason="LLM 호출에 실패해 판정하지 못했습니다",
                         warnings=["llm_call_failed"])

    warnings: list[str] = []
    src_refs = _resolve(data.get("source_evidence") or [], src, warnings, "정답")
    tgt_refs = _resolve(data.get("target_evidence") or [], tgt, warnings, "대상")

    verdict = data.get("verdict", "NEEDS_REVIEW")
    if verdict not in VERDICTS:
        warnings.append(f"알 수 없는 판정 '{verdict}'")
        verdict = "NEEDS_REVIEW"

    # 근거 없는 확정 판정은 내리지 않는다 — 출처가 없으면 검증이 아니다
    if verdict in ("MATCH", "VALUE_MISMATCH") and not (src_refs and tgt_refs):
        warnings.append("양쪽 근거가 갖춰지지 않아 판정을 보류로 내렸습니다")
        verdict = "NEEDS_REVIEW"

    # 행 기준 검증 — 앵커가 있는데 다른 행을 골랐으면 확정 판정을 내리지 않는다
    verified, detail = verify_row_anchor(tgt_refs, row_anchor)
    if detail:
        warnings.append(detail)
    if verified is False and verdict in ("MATCH", "VALUE_MISMATCH"):
        warnings.append("행 기준이 확인되지 않아 판정을 보류로 내렸습니다")
        verdict = "NEEDS_REVIEW"

    return Judgement(
        term=term, verdict=verdict, reason=data.get("reason", ""),
        source_value=data.get("source_value"), target_value=data.get("target_value"),
        source_refs=src_refs, target_refs=tgt_refs,
        candidates=data.get("candidates") or [], warnings=warnings,
        row_anchor=row_anchor, anchor_verified=verified)
